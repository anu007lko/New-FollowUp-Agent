import { useState, useEffect } from 'react';
import type { DashboardSummary, ViewName, RecordHeader } from '../types';
import { getGreeting, formatRelativeDate } from '../utils/displayStatus';
import { formatExactET } from '../utils/deadlineUtils';
import { getSkippedRecordIds, skipRecord, clearSkippedRecords } from '../utils/skipManager';
import { OverflowMenu } from '../components/OverflowMenu';
import { playSound } from '../utils/audio';

interface DashboardViewProps {
  dashboard: DashboardSummary;
  onRecordClick: (id: string) => void;
  onActionModal?: (recordId: string, actionType: string, recordVersion?: number) => void;
  onNavigate: (view: ViewName) => void;
}

const priorityOrder: Record<string, number> = {
  ManagerActionRequired: 0,
  FeedbackDue: 1,
  PendingFollowUp: 2,
  InterviewAwaitingConfirmation: 3,
  NeedsReview: 4,
};

function focusLanguage(status: string) {
  if (status === 'PendingFollowUp') return {
    eyebrow: 'FOLLOW-UP DUE',
    action: 'needs a follow-up.',
    evidence: 'No meaningful client response was found after the approved follow-up window.',
    reason: 'Follow-up timer reached · Review before drafting.',
    statusLabel: 'Action Required: Follow Up',
    statusType: 'action' as const,
  };
  if (status === 'InterviewAwaitingConfirmation') return {
    eyebrow: 'INTERVIEW ACTIVITY',
    action: 'needs confirmation.',
    evidence: 'Interview activity was detected and needs a manager-confirmed next step.',
    reason: 'Interview event detected · Confirm the latest outcome.',
    statusLabel: 'Action Required: Confirm Interview',
    statusType: 'action' as const,
  };
  if (status === 'InterviewRequestScheduled' || status === 'InterviewScheduled') return {
    eyebrow: 'INTERVIEW SCHEDULED',
    action: 'has an upcoming interview.',
    evidence: 'A future interview date was detected in the conversation.',
    reason: 'Invite found · Monitor the interview workflow.',
    statusLabel: 'Current Status: Interview Scheduled',
    statusType: 'status' as const,
  };
  if (status === 'NeedsReview') return {
    eyebrow: 'NEEDS REVIEW',
    action: 'needs your decision.',
    evidence: 'The latest client response could not be resolved safely by deterministic rules.',
    reason: 'Uncertain response · Manager review required.',
    statusLabel: 'Action Required: Set Outcome',
    statusType: 'action' as const,
  };
  if (status === 'FeedbackDue' || status === 'AwaitingFeedback') return {
    eyebrow: 'FEEDBACK DUE',
    action: 'needs feedback recorded.',
    evidence: 'Feedback on a requirement is due and needs a manager update.',
    reason: 'Feedback window reached · Record the outcome.',
    statusLabel: 'Action Required: Record Feedback',
    statusType: 'action' as const,
  };
  if (status === 'ManagerActionRequired') return {
    eyebrow: 'CLIENT RESPONSE',
    action: 'needs a decision.',
    evidence: 'A meaningful client response was detected in the latest conversation.',
    reason: 'Client response detected · Review before closing.',
    statusLabel: 'Action Required: Manager Review',
    statusType: 'action' as const,
  };
  return {
    eyebrow: 'CLIENT RESPONSE',
    action: 'needs a decision.',
    evidence: 'A meaningful client response was detected in the latest conversation.',
    reason: 'Client response detected · Review before closing.',
    statusLabel: 'Current Status: Awaiting Response',
    statusType: 'status' as const,
  };
}

export function DashboardView({ dashboard, onRecordClick, onActionModal, onNavigate }: DashboardViewProps) {
  const [skippedSet, setSkippedSet] = useState<Set<string>>(() => getSkippedRecordIds());
  const [skipNotice, setSkipNotice] = useState<string | null>(null);

  useEffect(() => {
    setSkippedSet(getSkippedRecordIds());
  }, [dashboard]);

  const incompleteCount = dashboard.incomplete ?? dashboard.records.filter(
    record => record.thread_message_count === 0
  ).length;

  const attentionRecords = [...dashboard.records]
    .filter(record => (record.domain_status in priorityOrder) && !skippedSet.has(record.id))
    .sort((left, right) => {
      const priorityDifference = (priorityOrder[left.domain_status] ?? 99) - (priorityOrder[right.domain_status] ?? 99);
      if (priorityDifference !== 0) return priorityDifference;
      return (right.latest_logical_timestamp || right.received_at).localeCompare(
        left.latest_logical_timestamp || left.received_at
      );
    });

  const focusRecord: RecordHeader | undefined = attentionRecords[0] || dashboard.records.find(r => !skippedSet.has(r.id));
  const focus = focusLanguage(focusRecord?.domain_status || 'NeedsReview');
  const invitePending = dashboard.interview_awaiting_confirmation + (dashboard.interview_request_scheduled || 0);
  const focusReceived = focusRecord?.received_at;
  const focusUpdated = focusRecord?.latest_logical_timestamp || focusReceived;

  const handleSkip = (recordId: string) => {
    playSound('select');
    skipRecord(recordId);
    setSkippedSet(getSkippedRecordIds());
    setSkipNotice('Skipped until tomorrow morning');
    setTimeout(() => {
      setSkipNotice(null);
    }, 4000);
  };

  const handleResetSkipped = () => {
    playSound('select');
    clearSkippedRecords();
    setSkippedSet(new Set());
    setSkipNotice(null);
  };

  const activeTodayRecords = dashboard.records.filter(r => !skippedSet.has(r.id));
  const skippedRecords = dashboard.records.filter(r => skippedSet.has(r.id));

  const skippedFollowUps = skippedRecords.filter(r => r.domain_status === 'PendingFollowUp').length;
  const skippedInvites = skippedRecords.filter(r => r.domain_status === 'InterviewAwaitingConfirmation' || r.domain_status === 'InterviewRequestScheduled').length;
  const skippedReviews = skippedRecords.filter(r => r.domain_status === 'NeedsReview' || r.domain_status === 'ManagerActionRequired' || r.domain_status === 'FeedbackDue').length;

  const followUpCount = dashboard.records.length > 0
    ? activeTodayRecords.filter(r => r.domain_status === 'PendingFollowUp').length
    : Math.max(0, dashboard.pending_follow_up - skippedFollowUps);

  const inviteCount = dashboard.records.length > 0
    ? activeTodayRecords.filter(r => r.domain_status === 'InterviewAwaitingConfirmation' || r.domain_status === 'InterviewRequestScheduled').length
    : Math.max(0, invitePending - skippedInvites);

  const reviewCount = dashboard.records.length > 0
    ? activeTodayRecords.filter(r => r.domain_status === 'NeedsReview' || r.domain_status === 'ManagerActionRequired' || r.domain_status === 'FeedbackDue').length
    : Math.max(0, dashboard.needs_review - skippedReviews);

  const laterToday = [
    {
      key: 'follow-up',
      label: 'Follow-up due',
      detail: `${followUpCount} ${followUpCount === 1 ? 'conversation' : 'conversations'}`,
      time: 'Now',
      tone: 'red',
      icon: '◷',
      view: 'records' as ViewName,
    },
    {
      key: 'invite',
      label: 'Invite pending',
      detail: `${inviteCount} ${inviteCount === 1 ? 'candidate' : 'candidates'}`,
      time: 'Today',
      tone: 'blue',
      icon: '✉',
      view: 'interviews' as ViewName,
    },
    {
      key: 'review',
      label: 'Needs review',
      detail: `${reviewCount} ${reviewCount === 1 ? 'conversation' : 'conversations'}`,
      time: 'Today',
      tone: 'violet',
      icon: '▤',
      view: 'records' as ViewName,
    },
  ];

  return (
    <div className="view-enter figma-dashboard" data-layer="Today / Dashboard Frame">
      <header className="figma-welcome" aria-label="Welcome" data-layer="Welcome / Editorial Header">
        <h1>{getGreeting()}, Tarun</h1>
        <p>A quieter way to stay on top of your active conversations.</p>
        <span className="sr-only">
          {dashboard.complete_records} complete, including {dashboard.closed} closed · {incompleteCount} incomplete
        </span>
      </header>

      <main className="figma-workspace" data-layer="Dashboard / Decision Workspace">
        {focusRecord ? (
          <section className="figma-focus-card" aria-label="Focus conversation" data-layer="Focus / Client Response Card">
            <span className="figma-focus-eyebrow">{focus.eyebrow}</span>
            <h2>{focusRecord.candidate_name || 'This conversation'}<br />{focus.action}</h2>
            <p className="figma-focus-evidence">{focus.evidence}</p>

            <div className="figma-focus-context">
              <i />
              <span>{focusRecord.skill || 'Requirement unavailable'}</span>
              <b>·</b>
              <span>{focusRecord.customer || 'Client unavailable'}</span>
              <b>·</b>
              <span>{formatRelativeDate(focusUpdated)}</span>
            </div>

            <button className={`figma-why-card ${focus.statusType === 'action' ? 'figma-why-card-action' : 'figma-why-card-status'}`} onClick={() => { playSound('click'); onRecordClick(focusRecord.id); }}>
              <span className="figma-why-icon">{focus.statusType === 'action' ? '⚡' : 'ℹ'}</span>
              <span><strong>{focus.statusLabel}</strong><small>{focus.reason}</small></span>
            </button>

            <div className="figma-focus-actions" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button className="figma-review-action" onClick={() => { playSound('click'); onRecordClick(focusRecord.id); }}>
                <span className="figma-eye" aria-hidden="true">◉</span>
                <span>Review conversation</span>
                <span className="figma-arrow" aria-hidden="true">→</span>
              </button>
              <button
                type="button"
                className="figma-skip-action"
                onClick={() => handleSkip(focusRecord.id)}
                title="Skip until tomorrow morning"
              >
                <span>Skip for later</span>
              </button>
              {(() => {
                const allowed = (focusRecord as any).workflow?.allowed_actions || [];
                const focusItems = allowed.length > 0 ? allowed.map((a: any) => ({
                  label: a.label,
                  danger: a.style === 'danger',
                  onClick: () => {
                    playSound('click');
                    if (a.execution_kind === 'navigation' && a.action_id === 'VIEW_CONVERSATION') {
                      onRecordClick(focusRecord.id);
                    } else if (onActionModal) {
                      onActionModal(focusRecord.id, a.action_id, focusRecord.record_version);
                    } else {
                      onRecordClick(focusRecord.id);
                    }
                  }
                })) : [{ label: 'No actions available', disabled: true, onClick: () => {} }];

                return <OverflowMenu items={focusItems} />;
              })()}
            </div>
            {skipNotice && (
              <div className="figma-skip-notice" role="status">
                <span>✓ {skipNotice}</span>
              </div>
            )}
          </section>
        ) : (
          <section className="figma-focus-card figma-focus-empty">
            <span className="figma-focus-eyebrow">{skippedSet.size > 0 ? 'ALL SKIPPED' : 'ALL CLEAR'}</span>
            <h2>{skippedSet.size > 0 ? 'All pending tasks skipped until tomorrow.' : 'No conversation needs your attention.'}</h2>
            <p className="figma-focus-evidence">
              {skippedSet.size > 0
                ? `${skippedSet.size} conversation${skippedSet.size === 1 ? '' : 's'} skipped until tomorrow 9:00 AM.`
                : 'Your active queue is clear.'}
            </p>
            {skippedSet.size > 0 && (
              <button
                type="button"
                className="btn-secondary figma-reset-skipped-btn"
                onClick={handleResetSkipped}
              >
                Reset skipped items
              </button>
            )}
          </section>
        )}

        <aside className="figma-right-rail" aria-label="Conversation and upcoming work" data-layer="Right Rail / Glass Panel">
          <section className="figma-conversation-card" data-layer="Conversation / Timeline">
            <h2>Conversation</h2>
            <ol className="figma-conversation-path">
              <li className="complete">
                <span className="figma-path-icon">✓</span>
                <div><strong>Submission</strong><small>{focusReceived ? formatExactET(focusReceived) : 'Not available'}</small></div>
              </li>
              <li className="current">
                <span className="figma-path-icon">•••</span>
                <div><strong>Client response</strong><small>{focusUpdated ? formatExactET(focusUpdated) : 'Waiting'}</small><em>Needs your decision</em></div>
              </li>
              <li>
                <span className="figma-path-icon">⚖</span>
                <div><strong>Your decision</strong><small>Pending</small></div>
              </li>
            </ol>
          </section>

          <section className="figma-later-card" data-layer="Later Today / Action Stack">
            <h2>Later today</h2>
            <div className="figma-later-list">
              {laterToday.map(item => (
                <button key={item.key} className={`figma-later-item ${item.tone}`} onClick={() => { playSound('click'); onNavigate(item.view); }}>
                  <span className="figma-later-icon">{item.icon}</span>
                  <span><strong>{item.label}</strong><small>{item.detail}</small></span>
                  <time>{item.time}</time>
                  <b aria-hidden="true">›</b>
                </button>
              ))}
            </div>
          </section>
        </aside>
      </main>
    </div>
  );
}
