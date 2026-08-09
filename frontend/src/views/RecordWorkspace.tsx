import { useState, useEffect } from 'react';
import type { FullRecord, TimelineEntry, LinkedInterviewSuggestion, LinkedConversation, ConfigStatus } from '../types';
import { StatusPill } from '../components/StatusPill';
import { LoadingState } from '../components/LoadingState';
import { ManagerActionBar } from '../components/ManagerActionBar';
import { ManagerActionModals } from '../components/ManagerActionModals';
import { IconBack, IconClose, IconWarning, IconChevronRight } from '../components/icons';
import { formatTimestamp } from '../utils/displayStatus';
import { getTimelineInfo, isAutomaticReply, collectParticipants, formatDueStatus } from '../utils/timelineClassifier';

interface RecordWorkspaceProps {
  record: FullRecord | null;
  loading: boolean;
  onClose: () => void;
  onRefreshRecord?: () => Promise<FullRecord | void>;
}

type PanelTab = 'overview' | 'conversation' | 'notes' | 'details';

export function RecordWorkspace({ record, loading, onClose, onRefreshRecord }: RecordWorkspaceProps) {
  const [activeTab, setActiveTab] = useState<PanelTab>('overview');
  const [expandedEntries, setExpandedEntries] = useState<Set<string>>(new Set());
  const [newestFirst, setNewestFirst] = useState(true);
  const [activeModal, setActiveModal] = useState<string | null>(null);
  const [selectedSuggestion, setSelectedSuggestion] = useState<LinkedInterviewSuggestion | null>(null);
  const [selectedLinked, setSelectedLinked] = useState<LinkedConversation | null>(null);
  const [conflictAcknowledged, setConflictAcknowledged] = useState(false);
  const [draftCreationAvailable, setDraftCreationAvailable] = useState(false);

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
  const latestMessageEntry = realMessages.length > 0 ? realMessages[realMessages.length - 1] : null;
  const latestInfo = latestMessageEntry ? getTimelineInfo(latestMessageEntry, record) : null;

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
            <button className="panel-back" onClick={onClose} aria-label="Back to records">
              <IconBack size={16} /> Back
            </button>
            <button className="panel-close-btn" onClick={onClose} aria-label="Close panel" title="Close">
              <IconClose size={14} />
            </button>
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
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Body — only this scrolls */}
        <div className="panel-body" role="tabpanel">
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

              {/* Latest Update */}
              <section className="panel-section">
                <h3 className="panel-section-title">Latest Update</h3>
                <div className="panel-status-card">
                  <div className="panel-status-main">
                    {record.latest_update || 'No updates available'}
                  </div>
                  <div className="panel-status-meta">
                    {latestInfo && <span className="panel-status-direction">{latestInfo.label}</span>}
                    {record.latest_sender && <span>{record.latest_sender}</span>}
                    {record.latest_logical_timestamp && <span>{formatTimestamp(record.latest_logical_timestamp)}</span>}
                  </div>
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
                </div>

                {/* Why this status — disclosure card */}
                {record.structured_evidence && (
                  <div className="panel-evidence-card">
                    <button
                      className="panel-evidence-toggle"
                      onClick={() => setShowEvidence(!showEvidence)}
                      aria-expanded={showEvidence}
                    >
                      <span>Why this status?</span>
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
                )}
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
          onSuccessAction={() => {
            if (onRefreshRecord) onRefreshRecord();
          }}
          onRefreshRecord={onRefreshRecord}
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

function TimelineItem({ entry, record, expanded, onToggle }: {
  entry: TimelineEntry; record: FullRecord; expanded: boolean; onToggle: () => void
}) {
  const info = getTimelineInfo(entry, record);
  const body = entry.body_preview || '';
  const needsTruncate = body.length > BODY_TRUNCATE;
  const displayBody = expanded || !needsTruncate ? body : body.slice(0, BODY_TRUNCATE) + '…';

  return (
    <div className={`timeline-entry ${info.className}`}>
      <div className="timeline-entry-header">
        <span className="timeline-entry-label">{info.label}</span>
        <span className="timeline-entry-sender">{entry.sender}</span>
        <span className="timeline-entry-time">{formatTimestamp(entry.timestamp)}</span>
      </div>
      {body && (
        <div className="timeline-entry-body">
          <p>{displayBody}</p>
          {needsTruncate && (
            <button className="timeline-toggle" onClick={onToggle}>
              {expanded ? 'Show less' : 'Show more'}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function getRecommendedAction(record: FullRecord): string | null {
  const ds = record.domain_status;
  if (ds === 'PendingFollowUp') return 'This submission is due for follow-up. Send a follow-up or close if no longer relevant.';
  if (ds === 'ManagerActionRequired') return 'A manager decision is required — review the outcome and take action.';
  if (ds === 'NeedsReview' || ds === 'NewSubmission') return 'Review this submission and set an outcome category.';
  if (ds === 'InterviewAwaitingConfirmation') return 'Confirm the interview status — completed, rescheduled, or cancelled.';
  if (ds === 'FeedbackDue') return 'Feedback is overdue. Record or request feedback from the hiring team.';
  if (ds === 'AwaitingFeedback') return 'Feedback is expected. Follow up if the deadline is approaching.';
  if (ds === 'Closed') return 'This record is closed. Reopen if follow-up activity resumes.';
  return null;
}

// Exported for testing
export { getTimelineInfo, isAutomaticReply };
