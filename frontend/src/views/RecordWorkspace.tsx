import { useState, useEffect } from 'react';
import type { FullRecord, TimelineEntry, LinkedInterviewSuggestion, LinkedConversation, ConfigStatus } from '../types';
import { StatusPill } from '../components/StatusPill';
import { LoadingState } from '../components/LoadingState';
import { ManagerActionBar } from '../components/ManagerActionBar';
import { ManagerActionModals } from '../components/ManagerActionModals';
import { IconBack, IconClose, IconWarning, IconChevronRight } from '../components/icons';
import { formatTimestamp } from '../utils/displayStatus';
import { getTimelineInfo, isAutomaticReply, collectParticipants, formatDueStatus } from '../utils/timelineClassifier';
import { playSound } from '../utils/audio';

interface RecordWorkspaceProps {
  record: FullRecord | null;
  loading: boolean;
  initialActionModal?: string | null;
  onClose: () => void;
  onRefreshRecord: (recordId: string) => Promise<FullRecord | void>;
}

type PanelTab = 'overview' | 'conversation' | 'notes' | 'details';

export function RecordWorkspace({ record, loading, initialActionModal, onClose, onRefreshRecord }: RecordWorkspaceProps) {
  const [activeTab, setActiveTab] = useState<PanelTab>('overview');
  const [expandedEntries, setExpandedEntries] = useState<Set<string>>(new Set());
  const [newestFirst, setNewestFirst] = useState(true);
  const [activeModal, setActiveModal] = useState<string | null>(initialActionModal || null);

  useEffect(() => {
    if (initialActionModal) {
      setActiveModal(initialActionModal);
    }
  }, [initialActionModal, record?.id]);
  const [selectedSuggestion, setSelectedSuggestion] = useState<LinkedInterviewSuggestion | null>(null);
  const [selectedLinked, setSelectedLinked] = useState<LinkedConversation | null>(null);
  const [conflictAcknowledged, setConflictAcknowledged] = useState(false);
  const [draftCreationAvailable, setDraftCreationAvailable] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Collapsed detail sections
  const [showParticipants, setShowParticipants] = useState(false);
  const [showIdentifiers, setShowIdentifiers] = useState(false);
  const [showAudit, setShowAudit] = useState(false);
  const [showRetention, setShowRetention] = useState(false);
  const [showEvidence, setShowEvidence] = useState(false);

  // Escape key closes panel
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !activeModal) onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose, activeModal]);

  // Reset tab when record changes
  useEffect(() => {
    setActiveTab('overview');
    setConflictAcknowledged(false);
    setRefreshMessage(null);
  }, [record?.id]);

  useEffect(() => {
    let active = true;
    fetch('/api/v1/config/status')
      .then(response => response.ok ? response.json() : Promise.reject())
      .then((status: ConfigStatus) => {
        if (active) setDraftCreationAvailable(status.draft_creation_available === true && status.mail_send_prohibited === true);
      })
      .catch(() => {
        if (active) setDraftCreationAvailable(false);
      });
    return () => { active = false; };
  }, []);

  if (loading && !record) {
    return (
      <>
        <div className="panel-overlay" onClick={onClose} />
        <aside className="record-panel panel-enter" role="complementary" aria-label="Record details loading">
          <LoadingState variant="record" />
        </aside>
      </>
    );
  }

  if (!record) return null;

  const handleRefreshThread = async () => {
    if (refreshing || !record) return;
    const targetRecordId = record.id;
    setRefreshing(true);
    setRefreshMessage(null);

    try {
      const csrfRes = await fetch('/api/v1/session/csrf-token', { method: 'POST' });
      if (!csrfRes.ok) {
        setRefreshMessage({ type: 'error', text: 'Could not refresh the thread. Please try again.' });
        return;
      }
      const csrfData = await csrfRes.json();
      const csrfToken = csrfData?.csrf_token;
      if (!csrfToken) {
        setRefreshMessage({ type: 'error', text: 'Could not refresh the thread. Please try again.' });
        return;
      }

      const res = await fetch(`/api/v1/records/${targetRecordId}/refresh`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify({ record_version: record.record_version }),
      });

      if (res.status === 200) {
        playSound('refresh');
        await onRefreshRecord(targetRecordId);
        setRefreshMessage({ type: 'success', text: 'Thread refreshed' });
      } else if (res.status === 404) {
        setRefreshMessage({ type: 'error', text: 'This record is no longer available.' });
      } else if (res.status === 409) {
        await onRefreshRecord(targetRecordId);
        setRefreshMessage({ type: 'error', text: 'This record changed elsewhere. The latest state has been loaded; please review and try again.' });
      } else if (res.status === 503) {
        setRefreshMessage({ type: 'error', text: 'Thread refresh is currently disabled.' });
      } else {
        setRefreshMessage({ type: 'error', text: 'Could not refresh the thread. Please try again.' });
      }
    } catch {
      setRefreshMessage({ type: 'error', text: 'Could not refresh the thread. Please try again.' });
    } finally {
      setRefreshing(false);
    }
  };

  const toggleEntry = (id: string) => {
    setExpandedEntries(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Deduplicate timeline entries by graph_immutable_id
  const uniqueTimeline = record.timeline.filter((entry, idx, arr) => {
    if (!entry.graph_immutable_id) return true;
    return arr.findIndex(e => e.graph_immutable_id === entry.graph_immutable_id) === idx;
  });

  const participants = collectParticipants(uniqueTimeline);
  const attachmentCount = record.attachment_count;
  const isClosed = record.domain_status === 'Closed';
  const isIncomplete = uniqueTimeline.length === 0;

  // Separate real messages from system notes
  const realMessages = uniqueTimeline.filter(e => !e.is_system_note);
  const systemNotes = uniqueTimeline.filter(e => e.is_system_note);

  // Determine newest message by actual timestamp, not array order
  const newestMessageEntry = realMessages.length > 0
    ? [...realMessages].sort((a, b) => {
        const ta = new Date(a.timestamp || 0).getTime();
        const tb = new Date(b.timestamp || 0).getTime();
        return tb - ta;
      })[0]
    : null;
  const newestInfo = newestMessageEntry ? getTimelineInfo(newestMessageEntry, record) : null;

  // Sorted messages for conversation tab
  const sortedMessages = newestFirst ? [...realMessages].reverse() : realMessages;

  const tabs: { key: PanelTab; label: string }[] = [
    { key: 'overview', label: 'Overview' },
    { key: 'conversation', label: `Conversation${realMessages.length > 0 ? ` (${realMessages.length})` : ''}` },
    { key: 'notes', label: 'Notes' },
    { key: 'details', label: 'Details' },
  ];

  // Recommended next action text
  const nextAction = getRecommendedAction(record);

  return (
    <>
      <div className="panel-overlay" onClick={onClose} aria-hidden="true" data-layer="Record Workspace / Overlay" />
      <aside className="record-panel panel-enter" role="complementary" aria-label="Record workspace" data-layer="Record Workspace / Panel">
        {/* Header */}
        <div className="panel-header" data-layer="Record Workspace / Header">
          <div className="panel-header-actions">
            <button className="panel-back" onClick={() => { playSound('click'); onClose(); }} aria-label="Back to records">
              <IconBack size={16} /> Back
            </button>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                className="panel-refresh-btn"
                onClick={handleRefreshThread}
                disabled={refreshing}
                aria-label="Refresh Thread"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  fontSize: '0.8125rem',
                  padding: '4px 10px',
                  borderRadius: 'var(--radius-sm, 4px)',
                  border: '1px solid var(--border-default)',
                  background: 'var(--bg-secondary, #1e293b)',
                  color: 'var(--text-primary, #f8fafc)',
                  cursor: refreshing ? 'not-allowed' : 'pointer',
                  opacity: refreshing ? 0.6 : 1,
                }}
              >
                {refreshing ? 'Refreshing...' : 'Refresh Thread'}
              </button>
              <button className="panel-close-btn" onClick={() => { playSound('click'); onClose(); }} aria-label="Close panel" title="Close">
                <IconClose size={14} />
              </button>
            </div>
          </div>
          <div className="panel-header-info">
            <div className="panel-header-top">
              <h2 className="panel-title">{record.candidate_name || 'Unknown Candidate'}</h2>
              <StatusPill domainStatus={record.domain_status} threadMessageCount={uniqueTimeline.length} />
            </div>
            <div className="panel-header-meta">
              {record.skill && <span className="panel-meta-item">{record.skill}</span>}
              {record.customer && <span className="panel-meta-item">{record.customer}</span>}
              {record.location && <span className="panel-meta-item">{record.location}</span>}
            </div>
            <div className="panel-header-ids">
              {record.job_id && <span className="panel-id">Job {record.job_id}</span>}
              {record.ep_reference && <span className="panel-id">EP {record.ep_reference}</span>}
              <span className="panel-id">Updated {formatTimestamp(record.latest_logical_timestamp || record.received_at)}</span>
              {record.source_content_warning && !conflictAcknowledged && (
                <span className="panel-conflict-badge">
                  <IconWarning size={12} /> Conflict
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="panel-tabs" role="tablist" data-layer="Record Workspace / Tabs">
          {tabs.map(tab => (
            <button
              key={tab.key}
              className={`panel-tab ${activeTab === tab.key ? 'panel-tab-active' : ''}`}
              role="tab"
              aria-selected={activeTab === tab.key}
              onClick={() => { playSound('click'); setActiveTab(tab.key); }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Body — only this scrolls */}
        <div className="panel-body" role="tabpanel">
          {/* Refresh feedback notice */}
          {refreshMessage && (
            <div
              className={`panel-notice ${refreshMessage.type === 'success' ? 'panel-notice-info' : 'panel-notice-warn'}`}
              style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
            >
              <span>{refreshMessage.text}</span>
              <button
                onClick={() => setRefreshMessage(null)}
                style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: '0.75rem', padding: '0 4px' }}
                aria-label="Dismiss notice"
              >
                ✕
              </button>
            </div>
          )}

          {/* Notices (shown on all tabs) */}
          {record.is_operational_record_only && (
            <div className="panel-notice panel-notice-info">
              Operational record — email content purged per retention policy. Metadata and audit history retained.
            </div>
          )}
          {isIncomplete && (
            <div className="panel-notice panel-notice-warn">
              Incomplete placeholder — no message data available for this record.
            </div>
          )}

          {/* === OVERVIEW TAB === */}
          {activeTab === 'overview' && (
            <>
              {/* Source conflict warning */}
              {record.source_content_warning && !conflictAcknowledged && (
                <div className="panel-notice panel-notice-warn panel-notice-flex">
                  <div>
                    <strong>Source Content Conflict:</strong> {record.source_content_warning}
                  </div>
                  <button
                    className="btn btn-sm btn-ghost"
                    onClick={() => setConflictAcknowledged(true)}
                    aria-label="Acknowledge conflict"
                  >
                    Dismiss
                  </button>
                </div>
              )}

              {/* Next action callout */}
              {nextAction && (
                <div className="panel-action-callout">
                  <div className="panel-action-callout-label">Recommended action</div>
                  <div className="panel-action-callout-text">{nextAction}</div>
                </div>
              )}

              {/* Latest Message Preview */}
              <section className="panel-section">
                <h3 className="panel-section-title">Latest Update</h3>
                <LatestMessagePreview
                  record={record}
                  newestEntry={newestMessageEntry}
                  newestInfo={newestInfo}
                />

                {/* Timers */}
                {record.interview_updated_at && (
                  <div className="panel-status-timer">
                    Interview Confirmed: {formatTimestamp(record.interview_updated_at)}
                  </div>
                )}
                {record.feedback_due_at && (
                  <div className="panel-status-timer">
                    Feedback Due: {formatTimestamp(record.feedback_due_at)} ({formatDueStatus(record.feedback_due_at)})
                  </div>
                )}
                {isClosed && record.close_reason && (
                  <div className="panel-status-closed">
                    Closed: {record.close_reason}
                    {record.close_note ? ` — ${record.close_note}` : ''}
                    {record.closed_at && <span className="panel-status-closed-at">{formatTimestamp(record.closed_at)}</span>}
                  </div>
                )}

                {/* View conversation link */}
                {realMessages.length > 0 && (
                  <button
                    className="btn btn-ghost btn-sm panel-view-conversation"
                    onClick={() => setActiveTab('conversation')}
                    aria-label="View full conversation"
                  >
                    View conversation →
                  </button>
                )}

                {/* Detected Interview Schedule Box */}
                {(record.interview_date || record.structured_evidence?.interview_date || record.confidence_label || record.structured_evidence?.confidence_label) && (
                  <div
                    className="panel-interview-details-box"
                    style={{
                      background: 'rgba(30, 41, 59, 0.6)',
                      border: '1px solid rgba(56, 189, 248, 0.3)',
                      borderRadius: '8px',
                      padding: '12px 16px',
                      margin: '12px 0',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#38bdf8' }}>Detected Interview Details</span>
                      {(record.confidence_label || record.structured_evidence?.confidence_label) && (
                        <span
                          className="confidence-badge"
                          style={{
                            fontSize: '0.75rem',
                            padding: '2px 8px',
                            borderRadius: '12px',
                            fontWeight: 600,
                            background: (record.confidence_label || record.structured_evidence?.confidence_label || '').includes('conflict')
                              ? 'rgba(239, 68, 68, 0.2)'
                              : (record.confidence_label || record.structured_evidence?.confidence_label || '').includes('Confirmed')
                              ? 'rgba(16, 185, 129, 0.2)'
                              : 'rgba(245, 158, 11, 0.2)',
                            color: (record.confidence_label || record.structured_evidence?.confidence_label || '').includes('conflict')
                              ? '#fca5a5'
                              : (record.confidence_label || record.structured_evidence?.confidence_label || '').includes('Confirmed')
                              ? '#6ee7b7'
                              : '#fcd34d',
                            border: '1px solid currentColor',
                          }}
                        >
                          {record.confidence_label || record.structured_evidence?.confidence_label}
                        </span>
                      )}
                    </div>
                    {(record.interview_date || record.structured_evidence?.interview_date || record.interview_time || record.structured_evidence?.interview_time) && (
                      <div style={{ fontSize: '0.9rem', color: '#f8fafc', marginBottom: '4px' }}>
                        📅 <strong>Scheduled Slot:</strong> {record.interview_date || record.structured_evidence?.interview_date || 'Date TBD'} at {record.interview_time || record.structured_evidence?.interview_time || 'Time TBD'} {record.interview_timezone || record.structured_evidence?.timezone || ''}
                      </div>
                    )}
                    {(record.timezone_source || record.structured_evidence?.timezone_source) && (
                      <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                        Timezone Source: {(record.timezone_source || record.structured_evidence?.timezone_source) === 'message_text' ? 'Detected from message' : 'Resolved via sender metadata'}
                      </div>
                    )}
                  </div>
                )}

                {/* Current Status / Action Required — disclosure card */}
                {record.structured_evidence && (() => {
                  const ds = record.domain_status;
                  let cardLabel = 'Current Status: ' + ds;
                  let cardType: 'action' | 'status' = 'status';
                  let cardIcon = 'ℹ';
                  let cardReason = record.structured_evidence.reason_code || '';

                  if (ds === 'PendingFollowUp') {
                    cardLabel = 'Action Required: Follow Up'; cardType = 'action'; cardIcon = '⚡';
                    cardReason = cardReason || 'Follow-up timer reached · Review before drafting.';
                  } else if (ds === 'InterviewAwaitingConfirmation') {
                    cardLabel = 'Action Required: Confirm Interview'; cardType = 'action'; cardIcon = '⚡';
                    cardReason = cardReason || 'Interview event detected · Confirm the latest outcome.';
                  } else if (ds === 'InterviewRequestScheduled' || ds === 'InterviewScheduled') {
                    cardLabel = 'Current Status: Interview Scheduled'; cardType = 'status'; cardIcon = 'ℹ';
                    cardReason = cardReason || 'Invite found · Monitor the interview workflow.';
                  } else if (ds === 'NeedsReview' || ds === 'NewSubmission') {
                    cardLabel = 'Action Required: Set Outcome'; cardType = 'action'; cardIcon = '⚡';
                    cardReason = cardReason || 'Uncertain response · Manager review required.';
                  } else if (ds === 'FeedbackDue' || ds === 'AwaitingFeedback') {
                    cardLabel = 'Action Required: Record Feedback'; cardType = 'action'; cardIcon = '⚡';
                    cardReason = cardReason || 'Feedback window reached · Record the outcome.';
                  } else if (ds === 'ManagerActionRequired') {
                    cardLabel = 'Action Required: Manager Review'; cardType = 'action'; cardIcon = '⚡';
                    cardReason = cardReason || 'Client response detected · Review before closing.';
                  }

                  return (
                    <div className={`panel-evidence-card ${cardType === 'action' ? 'panel-evidence-card-action' : 'panel-evidence-card-status'}`}>
                      <button
                        className="panel-evidence-toggle"
                        onClick={() => setShowEvidence(!showEvidence)}
                        aria-expanded={showEvidence}
                      >
                        <span className="panel-evidence-toggle-label">
                          <span className={`panel-evidence-icon ${cardType === 'action' ? 'panel-evidence-icon-action' : 'panel-evidence-icon-status'}`}>{cardIcon}</span>
                          <span className="panel-evidence-title-group">
                            <span className="panel-evidence-title">{cardLabel}</span>
                            <span className="panel-evidence-reason">{cardReason}</span>
                          </span>
                        </span>
                        <span className={`collapse-chevron ${showEvidence ? 'collapse-chevron-open' : ''}`}>
                          <IconChevronRight size={14} />
                        </span>
                      </button>
                      {showEvidence && (
                        <div className="panel-evidence-content">
                          <div className="panel-evidence-row">
                            <span className="panel-evidence-label">Category</span>
                            <span className="panel-evidence-value">{record.structured_evidence.category}</span>
                          </div>
                          <div className="panel-evidence-row">
                            <span className="panel-evidence-label">Workflow Status</span>
                            <span className="panel-evidence-value">{record.structured_evidence.workflow_status}</span>
                          </div>
                          <div className="panel-evidence-row">
                            <span className="panel-evidence-label">Reason</span>
                            <span className="panel-evidence-value">{record.structured_evidence.reason_code}</span>
                          </div>
                          {record.structured_evidence.confidence_label && (
                            <div className="panel-evidence-row">
                              <span className="panel-evidence-label">Evidence Confidence</span>
                              <span className="panel-evidence-value">{record.structured_evidence.confidence_label}</span>
                            </div>
                          )}
                          {record.structured_evidence.interview_date && (
                            <div className="panel-evidence-row">
                              <span className="panel-evidence-label">Detected Date/Time</span>
                              <span className="panel-evidence-value">
                                {record.structured_evidence.interview_date} {record.structured_evidence.interview_time || ''} {record.structured_evidence.timezone || ''}
                              </span>
                            </div>
                          )}
                          <div className="panel-evidence-row">
                            <span className="panel-evidence-label">Messages Evaluated</span>
                            <span className="panel-evidence-value">{record.structured_evidence.logical_messages_evaluated}</span>
                          </div>
                          {record.structured_evidence.timer_anchor_timestamp && (
                            <div className="panel-evidence-row">
                              <span className="panel-evidence-label">Timer Anchor</span>
                              <span className="panel-evidence-value">{formatTimestamp(record.structured_evidence.timer_anchor_timestamp)}</span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })()}
              </section>

              {/* Interview Suggestions */}
              {record.interview_suggestions && record.interview_suggestions.length > 0 && (
                <section className="panel-section">
                  <h3 className="panel-section-title">Related Interview Conversation</h3>
                  {record.interview_suggestions.map((sugg, idx) => (
                    <div key={sugg.suggestion_id || sugg.conversation_id || idx} className="panel-interview-suggestion">
                      <div className="panel-interview-suggestion-title">
                        Separate interview invitation detected
                      </div>
                      <div className="panel-interview-suggestion-detail">
                        <strong>Subject:</strong> {sugg.interview_subject || 'Interview Invitation'}
                        {sugg.interview_received_at && <span> ({formatTimestamp(sugg.interview_received_at)})</span>}
                      </div>
                      {(() => {
                        const lastMsg = sugg.thread_messages?.[sugg.thread_messages.length - 1];
                        const sender = sugg.latest_interview_message_sender || lastMsg?.from?.emailAddress?.address || (lastMsg as any)?.sender;
                        const excerpt = sugg.latest_interview_message_excerpt || lastMsg?.bodyPreview || (lastMsg as any)?.body_preview;
                        return (
                          <>
                            {sender && <div className="panel-interview-suggestion-detail"><strong>From:</strong> {sender}</div>}
                            {excerpt && <div className="panel-interview-excerpt">"{excerpt}"</div>}
                          </>
                        );
                      })()}
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => { setSelectedSuggestion(sugg); setActiveModal('link-interview'); }}
                      >
                        Review & Link
                      </button>
                    </div>
                  ))}
                </section>
              )}

              {/* Linked Conversations */}
              {record.linked_conversations && record.linked_conversations.length > 0 && (
                <section className="panel-section">
                  <h3 className="panel-section-title">
                    Linked Interviews
                    <span className="panel-section-count">{record.linked_conversations.length}</span>
                  </h3>
                  {record.linked_conversations.map((lc, i) => (
                    <div key={i} className="panel-linked-card">
                      <div>
                        <div className="panel-linked-title">{lc.subject || 'Interview Thread'}</div>
                        <div className="panel-linked-meta">Linked by {lc.linked_by} · {formatTimestamp(lc.linked_at)}</div>
                      </div>
                      <button
                        className="btn btn-sm btn-ghost"
                        style={{ color: 'var(--status-followup)' }}
                        onClick={() => { setSelectedLinked(lc); setActiveModal('unlink-interview'); }}
                      >
                        Unlink
                      </button>
                    </div>
                  ))}
                </section>
              )}
            </>
          )}

          {/* === CONVERSATION TAB === */}
          {activeTab === 'conversation' && (
            <>
              {isIncomplete ? (
                <EmptyState icon="—" title="No conversation" message="This record has no message data." />
              ) : (
                <>
                  <div className="timeline-chronology-toggle">
                    <button
                      className={`timeline-chronology-btn ${newestFirst ? 'timeline-chronology-btn-active' : ''}`}
                      onClick={() => setNewestFirst(true)}
                    >
                      Newest first
                    </button>
                    <button
                      className={`timeline-chronology-btn ${!newestFirst ? 'timeline-chronology-btn-active' : ''}`}
                      onClick={() => setNewestFirst(false)}
                    >
                      Chronological
                    </button>
                  </div>

                  <div className="timeline">
                    {sortedMessages.map(entry => (
                      <TimelineItem
                        key={entry.entry_id}
                        entry={entry}
                        record={record}
                        expanded={expandedEntries.has(entry.entry_id)}
                        onToggle={() => toggleEntry(entry.entry_id)}
                      />
                    ))}
                  </div>

                  {/* System events collapsed */}
                  {systemNotes.length > 0 && (
                    <section className="panel-section" style={{ marginTop: 'var(--sp-4)' }}>
                      <button
                        className="panel-collapse-toggle"
                        onClick={() => setShowAudit(!showAudit)}
                        aria-expanded={showAudit}
                      >
                        <span>System Events ({systemNotes.length})</span>
                        <span className={`collapse-chevron ${showAudit ? 'collapse-chevron-open' : ''}`}>
                          <IconChevronRight size={14} />
                        </span>
                      </button>
                      {showAudit && (
                        <div className="panel-collapse-content">
                          <div className="timeline">
                            {systemNotes.map(entry => (
                              <TimelineItem
                                key={entry.entry_id}
                                entry={entry}
                                record={record}
                                expanded={expandedEntries.has(entry.entry_id)}
                                onToggle={() => toggleEntry(entry.entry_id)}
                              />
                            ))}
                          </div>
                        </div>
                      )}
                    </section>
                  )}
                </>
              )}
            </>
          )}

          {/* === NOTES TAB === */}
          {activeTab === 'notes' && (
            <>
              {record.manager_notes ? (
                <div className="panel-note-card">
                  <div className="panel-note-meta">
                    <span>Manager</span>
                  </div>
                  <div className="panel-note-text">{record.manager_notes}</div>
                </div>
              ) : (
                <EmptyState icon="📝" title="No notes yet" message="Add a note to track decisions or context for this record." />
              )}
              {!isIncomplete && (
                <button
                  className="btn btn-sm"
                  style={{ marginTop: 'var(--sp-3)' }}
                  onClick={() => setActiveModal('note')}
                >
                  Add Note
                </button>
              )}
            </>
          )}

          {/* === DETAILS TAB === */}
          {activeTab === 'details' && (
            <>
              {/* Email Participants */}
              {participants.length > 0 && (
                <section className="panel-section">
                  <button
                    className="panel-collapse-toggle"
                    onClick={() => setShowParticipants(!showParticipants)}
                    aria-expanded={showParticipants}
                  >
                    <span>Email Participants ({participants.length})</span>
                    <span className={`collapse-chevron ${showParticipants ? 'collapse-chevron-open' : ''}`}>
                      <IconChevronRight size={14} />
                    </span>
                  </button>
                  {showParticipants && (
                    <div className="panel-collapse-content">
                      {participants.map((p, i) => (
                        <div key={i} className="panel-participant">
                          <span className="panel-participant-role">{p.role}</span>
                          <span className="panel-participant-addr">{p.address}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              )}

              {/* Attachments */}
              {attachmentCount > 0 && (
                <section className="panel-section">
                  <h3 className="panel-section-title">Attachments</h3>
                  <div className="panel-attachments">
                    <span className="panel-attachment-count">
                      {attachmentCount} attachment{attachmentCount !== 1 ? 's' : ''}
                    </span>
                  </div>
                </section>
              )}

              {/* Classification Evidence */}
              {record.structured_evidence && (
                <section className="panel-section">
                  <button
                    className="panel-collapse-toggle"
                    onClick={() => setShowEvidence(!showEvidence)}
                    aria-expanded={showEvidence}
                  >
                    <span>Classification Evidence</span>
                    <span className={`collapse-chevron ${showEvidence ? 'collapse-chevron-open' : ''}`}>
                      <IconChevronRight size={14} />
                    </span>
                  </button>
                  {showEvidence && (
                    <div className="panel-collapse-content">
                      <div className="panel-detail-row">
                        <span className="panel-detail-label">Category</span>
                        <span className="panel-detail-value">{record.structured_evidence.category}</span>
                      </div>
                      <div className="panel-detail-row">
                        <span className="panel-detail-label">Workflow Status</span>
                        <span className="panel-detail-value">{record.structured_evidence.workflow_status}</span>
                      </div>
                      <div className="panel-detail-row">
                        <span className="panel-detail-label">Reason Code</span>
                        <span className="panel-detail-value">{record.structured_evidence.reason_code}</span>
                      </div>
                      <div className="panel-detail-row">
                        <span className="panel-detail-label">Messages Evaluated</span>
                        <span className="panel-detail-value">{record.structured_evidence.logical_messages_evaluated}</span>
                      </div>
                      {record.structured_evidence.timer_anchor_timestamp && (
                        <div className="panel-detail-row">
                          <span className="panel-detail-label">Timer Anchor</span>
                          <span className="panel-detail-value">{formatTimestamp(record.structured_evidence.timer_anchor_timestamp)}</span>
                        </div>
                      )}
                    </div>
                  )}
                </section>
              )}

              {/* Identifiers */}
              <section className="panel-section">
                <button
                  className="panel-collapse-toggle"
                  onClick={() => setShowIdentifiers(!showIdentifiers)}
                  aria-expanded={showIdentifiers}
                >
                  <span>Record Identifiers</span>
                  <span className={`collapse-chevron ${showIdentifiers ? 'collapse-chevron-open' : ''}`}>
                    <IconChevronRight size={14} />
                  </span>
                </button>
                {showIdentifiers && (
                  <div className="panel-collapse-content">
                    {record.job_id && (
                      <div className="panel-detail-row">
                        <span className="panel-detail-label">Job ID</span>
                        <span className="panel-detail-value mono">{record.job_id}</span>
                      </div>
                    )}
                    {record.ep_reference && (
                      <div className="panel-detail-row">
                        <span className="panel-detail-label">EP Reference</span>
                        <span className="panel-detail-value mono">{record.ep_reference}</span>
                      </div>
                    )}
                    <div className="panel-detail-row">
                      <span className="panel-detail-label">Received</span>
                      <span className="panel-detail-value">{formatTimestamp(record.received_at)}</span>
                    </div>
                    <div className="panel-detail-row">
                      <span className="panel-detail-label">Record Created</span>
                      <span className="panel-detail-value">{formatTimestamp(record.created_at)}</span>
                    </div>
                    {record.interview_state && record.interview_state !== 'None' && (
                      <div className="panel-detail-row">
                        <span className="panel-detail-label">Interview State</span>
                        <span className="panel-detail-value">{record.interview_state}</span>
                      </div>
                    )}
                    {/* graph_immutable_id and conversation_id intentionally omitted */}
                  </div>
                )}
              </section>

              {/* Retention */}
              {(record.retention_expired !== undefined || record.expires_at) && (
                <section className="panel-section">
                  <button
                    className="panel-collapse-toggle"
                    onClick={() => setShowRetention(!showRetention)}
                    aria-expanded={showRetention}
                  >
                    <span>Retention Information</span>
                    <span className={`collapse-chevron ${showRetention ? 'collapse-chevron-open' : ''}`}>
                      <IconChevronRight size={14} />
                    </span>
                  </button>
                  {showRetention && (
                    <div className="panel-collapse-content">
                      {record.expires_at && (
                        <div className="panel-detail-row">
                          <span className="panel-detail-label">Expires</span>
                          <span className="panel-detail-value">{formatTimestamp(record.expires_at)}</span>
                        </div>
                      )}
                      <div className="panel-detail-row">
                        <span className="panel-detail-label">Retention Expired</span>
                        <span className="panel-detail-value">{record.retention_expired ? 'Yes' : 'No'}</span>
                      </div>
                    </div>
                  )}
                </section>
              )}

              {/* Audit History */}
              {(record.system_notes || record.manager_notes) && (
                <section className="panel-section">
                  <button
                    className="panel-collapse-toggle"
                    onClick={() => setShowAudit(!showAudit)}
                    aria-expanded={showAudit}
                  >
                    <span>Audit History</span>
                    <span className={`collapse-chevron ${showAudit ? 'collapse-chevron-open' : ''}`}>
                      <IconChevronRight size={14} />
                    </span>
                  </button>
                  {showAudit && (
                    <div className="panel-collapse-content">
                      {record.system_notes && (
                        <div className="panel-notes">
                          <h4 className="panel-notes-title">System Notes</h4>
                          <p className="panel-notes-body">{record.system_notes}</p>
                        </div>
                      )}
                      {record.manager_notes && (
                        <div className="panel-notes">
                          <h4 className="panel-notes-title">Manager Notes</h4>
                          <p className="panel-notes-body">{record.manager_notes}</p>
                        </div>
                      )}
                    </div>
                  )}
                </section>
              )}
            </>
          )}
        </div>

        {/* Sticky Manager Action Bar */}
        <ManagerActionBar
          record={record}
          onOpenModal={actionType => setActiveModal(actionType)}
          draftCreationAvailable={draftCreationAvailable}
        />

        {/* Modals */}
        <ManagerActionModals
          activeModal={activeModal}
          record={record}
          selectedSuggestion={selectedSuggestion}
          selectedLinked={selectedLinked}
          onCloseModal={() => {
            setActiveModal(null);
            setSelectedSuggestion(null);
            setSelectedLinked(null);
          }}
          onSuccessAction={(endpoint, payloadData) => {
            if (endpoint === 'outcome-decision' && payloadData?.outcome_category) {
              const cat = payloadData.outcome_category;
              if (cat === 'Rejection' || cat === 'Client Rejected') {
                setRefreshMessage({ type: 'success', text: 'Rejection recorded. Close this record to complete the workflow.' });
              } else if (cat === 'Position Closed') {
                setRefreshMessage({ type: 'success', text: 'Position closure recorded. Close this record to complete the workflow.' });
              }
            }
            onRefreshRecord(record.id);
          }}
          onRefreshRecord={() => onRefreshRecord(record.id)}
        />
      </aside>
    </>
  );
}

// --- Helpers ---

function EmptyState({ icon, title, message }: { icon: string; title: string; message: string }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">{icon}</div>
      <h3 className="empty-state-title">{title}</h3>
      <p className="empty-state-message">{message}</p>
    </div>
  );
}

const BODY_TRUNCATE = 280;

/** Safely truncate legacy body previews at quoted-reply boundaries. */
function cleanupLegacyBodyPreview(raw: string): string {
  if (!raw) return '';
  const boundaryRegex = /(?:^|\r?\n)(?:_{5,}\r?\n|-----Original Message-----\r?\n)?From:\s/i;
  const match = raw.match(boundaryRegex);
  
  let cleaned = raw;
  if (match && match.index !== undefined) {
    cleaned = raw.substring(0, match.index);
  }
  
  return cleaned.trim();
}

/** Determine message direction from timeline classification. */
function getMessageDirection(info: { className: string; label: string }): 'sent' | 'received' | null {
  if (info.className === 'timeline-sent' || info.className === 'timeline-followup') return 'sent';
  if (info.className === 'timeline-inbound' || info.className === 'timeline-submission') return 'received';
  return null;
}

/** Format sender for display: prefer the name part before @, fallback to full address. */
function formatSenderDisplay(sender: string): string {
  if (!sender) return '';
  // If it's just an email, use the local part capitalised
  const atIdx = sender.indexOf('@');
  if (atIdx > 0 && !sender.includes(' ')) {
    return sender.slice(0, atIdx).replace(/[._-]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }
  return sender;
}

function LatestMessagePreview({ record, newestEntry, newestInfo }: {
  record: FullRecord;
  newestEntry: TimelineEntry | null;
  newestInfo: { className: string; label: string } | null;
}) {
  // Case 1: We have a timeline entry with a body_preview (legacy or unique)
  if (newestEntry && newestEntry.body_preview) {
    const direction = newestInfo ? getMessageDirection(newestInfo) : null;
    const cleanedBody = cleanupLegacyBodyPreview(newestEntry.body_preview);
    const truncated = cleanedBody.length > BODY_TRUNCATE
      ? cleanedBody.slice(0, BODY_TRUNCATE) + '…'
      : cleanedBody;

    return (
      <div className="panel-status-card" data-testid="overview-preview">
        <div className="panel-status-meta">
          {direction && (
            <span className={`panel-direction-badge panel-direction-badge--${direction}`}>
              {direction === 'sent' ? '↑ Sent' : '↓ Received'}
            </span>
          )}
          {newestInfo && <span className="panel-status-direction">{newestInfo.label}</span>}
          {newestEntry.sender && (
            <span className="panel-status-sender">{formatSenderDisplay(newestEntry.sender)}</span>
          )}
          {newestEntry.timestamp && <span>{formatTimestamp(newestEntry.timestamp)}</span>}
        </div>
        <div className="panel-status-main">
          {cleanedBody ? truncated : <span className="timeline-no-content">Full message content was not stored locally.</span>}
        </div>
      </div>
    );
  }

  // Case 2: No timeline body, but record.latest_update exists — truncate headers as fallback
  if (record.latest_update) {
    const cleaned = cleanupLegacyBodyPreview(record.latest_update);
    if (cleaned) {
      return (
        <div className="panel-status-card panel-status-card--fallback" data-testid="overview-preview-fallback">
          <div className="panel-status-meta">
            {record.latest_sender && <span>{record.latest_sender}</span>}
            {record.latest_logical_timestamp && <span>{formatTimestamp(record.latest_logical_timestamp)}</span>}
          </div>
          <div className="panel-status-main">
            {cleaned.length > BODY_TRUNCATE ? cleaned.slice(0, BODY_TRUNCATE) + '…' : cleaned}
          </div>
        </div>
      );
    }
  }

  // Case 3: Only metadata remains
  return (
    <div className="panel-status-card panel-status-card--empty" data-testid="overview-preview-empty">
      <div className="panel-status-main">
        Full message content was not stored locally.
      </div>
    </div>
  );
}

function TimelineItem({ entry, record, expanded, onToggle }: {
  entry: TimelineEntry; record: FullRecord; expanded: boolean; onToggle: () => void
}) {
  const info = getTimelineInfo(entry, record);
  const direction = getMessageDirection(info);
  const rawBody = entry.body_preview || '';
  const body = cleanupLegacyBodyPreview(rawBody);
  const needsTruncate = body.length > BODY_TRUNCATE;
  const displayBody = expanded || !needsTruncate ? body : body.slice(0, BODY_TRUNCATE) + '…';

  return (
    <div className={`timeline-entry ${info.className}`} data-testid="timeline-message">
      <div className="timeline-entry-header">
        {direction && (
          <span className={`timeline-direction-badge timeline-direction-badge--${direction}`} aria-label={direction === 'sent' ? 'Sent message' : 'Received message'}>
            {direction === 'sent' ? '↑' : '↓'}
          </span>
        )}
        <span className="timeline-entry-label">{info.label}</span>
        <span className="timeline-entry-sender" title={entry.sender}>{formatSenderDisplay(entry.sender)}</span>
        <span className="timeline-entry-time">{formatTimestamp(entry.timestamp)}</span>
      </div>
      {body ? (
        <div className="timeline-entry-body">
          <p>{displayBody}</p>
          {needsTruncate && (
            <button className="timeline-toggle" onClick={onToggle} aria-expanded={expanded}>
              {expanded ? 'Show less' : 'Show more'}
            </button>
          )}
        </div>
      ) : (
        <div className="timeline-entry-body timeline-entry-body--empty">
          <p className="timeline-no-content">Full message content was not stored locally.</p>
        </div>
      )}
    </div>
  );
}

function getRecommendedAction(record: FullRecord): string | null {
  const ds = record.domain_status;
  if (ds === 'PendingFollowUp') return 'This submission is due for follow-up. Send a follow-up or close if no longer relevant.';
  if (ds === 'ManagerActionRequired') {
    const outcomeCat = record.structured_evidence?.category || (record as any).manager_outcome_category;
    const hasTimelineOutcome = record.timeline?.some(e =>
      e.event_type === 'MANAGER_OUTCOME_DECISION' &&
      (e.body_preview?.includes('Rejection') || e.body_preview?.includes('Position Closed') || e.body_preview?.includes('Client Rejected'))
    );
    const isClosedOutcome = outcomeCat === 'Rejection' || outcomeCat === 'Position Closed' || outcomeCat === 'Client Rejected' || hasTimelineOutcome;
    if (isClosedOutcome) {
      return 'Manager decision recorded — close this record to complete the workflow.';
    }
    return 'A manager decision is required — review the outcome and take action.';
  }
  if (ds === 'NeedsReview' || ds === 'NewSubmission') return 'Review this submission and set an outcome category.';
  if (ds === 'InterviewAwaitingConfirmation') return 'Confirm the interview status — completed, rescheduled, or cancelled.';
  if (ds === 'FeedbackDue') return 'Feedback is overdue. Record or request feedback from the hiring team.';
  if (ds === 'AwaitingFeedback') return 'Feedback is expected. Follow up if the deadline is approaching.';
  if (ds === 'Closed') return 'This record is closed. Reopen if follow-up activity resumes.';
  return null;
}

// Exported for testing
export { getTimelineInfo, isAutomaticReply };
