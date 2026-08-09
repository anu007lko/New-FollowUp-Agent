import type { DashboardSummary, ViewName, RecordHeader } from '../types';
import { getGreeting, formatRelativeDate } from '../utils/displayStatus';
import { formatExactET } from '../utils/deadlineUtils';

interface DashboardViewProps {
  dashboard: DashboardSummary;
  onRecordClick: (id: string) => void;
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
  };
  if (status === 'InterviewAwaitingConfirmation') return {
    eyebrow: 'INTERVIEW ACTIVITY',
    action: 'needs confirmation.',
    evidence: 'Interview activity was detected and needs a manager-confirmed next step.',
    reason: 'Interview event detected · Confirm the latest outcome.',
  };
  if (status === 'InterviewRequestScheduled') return {
    eyebrow: 'INTERVIEW SCHEDULED',
    action: 'has an upcoming interview.',
    evidence: 'A future interview date was detected in the conversation.',
    reason: 'Invite found · Monitor the interview workflow.',
  };
  if (status === 'NeedsReview') return {
    eyebrow: 'NEEDS REVIEW',
    action: 'needs your decision.',
    evidence: 'The latest client response could not be resolved safely by deterministic rules.',
    reason: 'Uncertain response · Manager review required.',
  };
  return {
    eyebrow: 'CLIENT RESPONSE',
    action: 'needs a decision.',
    evidence: 'A meaningful client response was detected in the latest conversation.',
    reason: 'Client response detected · Review before closing.',
  };
}

export function DashboardView({ dashboard, onRecordClick, onNavigate }: DashboardViewProps) {
  const incompleteCount = dashboard.incomplete ?? dashboard.records.filter(
    record => record.thread_message_count === 0
  ).length;

  const attentionRecords = [...dashboard.records]
    .filter(record => record.domain_status in priorityOrder)
    .sort((left, right) => {
      const priorityDifference = (priorityOrder[left.domain_status] ?? 99) - (priorityOrder[right.domain_status] ?? 99);
      if (priorityDifference !== 0) return priorityDifference;
      return (right.latest_logical_timestamp || right.received_at).localeCompare(
        left.latest_logical_timestamp || left.received_at
      );
    });

  const focusRecord: RecordHeader | undefined = attentionRecords[0] || dashboard.records[0];
  const focus = focusLanguage(focusRecord?.domain_status || 'NeedsReview');
  const invitePending = dashboard.interview_awaiting_confirmation + (dashboard.interview_request_scheduled || 0);
  const focusReceived = focusRecord?.received_at;
  const focusUpdated = focusRecord?.latest_logical_timestamp || focusReceived;

  const laterToday = [
    {
      key: 'follow-up',
      label: 'Follow-up due',
      detail: `${dashboard.pending_follow_up} conversations`,
      time: 'Now',
      tone: 'red',
      icon: '◷',
      view: 'records' as ViewName,
    },
    {
      key: 'invite',
      label: 'Invite pending',
      detail: `${invitePending} candidates`,
      time: 'Today',
      tone: 'blue',
      icon: '✉',
      view: 'interviews' as ViewName,
    },
    {
      key: 'review',
      label: 'Needs review',
      detail: `${dashboard.needs_review} conversations`,
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

            <button className="figma-why-card" onClick={() => onRecordClick(focusRecord.id)}>
              <span className="figma-why-icon">?</span>
              <span><strong>Why this status?</strong><small>{focus.reason}</small></span>
            </button>

            <button className="figma-review-action" onClick={() => onRecordClick(focusRecord.id)}>
              <span className="figma-eye" aria-hidden="true">◉</span>
              <span>Review conversation</span>
              <span className="figma-arrow" aria-hidden="true">→</span>
            </button>
          </section>
        ) : (
          <section className="figma-focus-card figma-focus-empty">
            <span className="figma-focus-eyebrow">ALL CLEAR</span>
            <h2>No conversation needs your attention.</h2>
            <p className="figma-focus-evidence">Your active queue is clear.</p>
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
                <button key={item.key} className={`figma-later-item ${item.tone}`} onClick={() => onNavigate(item.view)}>
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
