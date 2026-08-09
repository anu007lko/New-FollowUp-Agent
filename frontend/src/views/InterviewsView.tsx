import type { RecordHeader } from '../types';
import { StatusPill } from '../components/StatusPill';
import { EmptyState } from '../components/LoadingState';
import { formatRelativeDate, isInterviewRelated } from '../utils/displayStatus';
import { getDeadlineStatus, formatDeadlineDate, formatExactET } from '../utils/deadlineUtils';

interface InterviewsViewProps {
  records: RecordHeader[];
  onRecordClick: (id: string) => void;
}

interface InterviewGroup {
  title: string;
  records: RecordHeader[];
}

/** Map interview-related status to recommended next action. */
function getNextAction(r: RecordHeader): string {
  switch (r.domain_status) {
    case 'InterviewAwaitingConfirmation': return 'Confirm interview details';
    case 'InterviewRequestScheduled':
    case 'InterviewScheduled': return 'Monitor for updates';
    case 'AwaitingFeedback': return 'Follow up for feedback';
    case 'FeedbackDue': return 'Collect overdue feedback';
    default: return 'Review record';
  }
}

export function InterviewsView({ records, onRecordClick }: InterviewsViewProps) {
  const interviewRecords = records.filter(r => isInterviewRelated(r.domain_status, r.interview_state));

  // Group by status bucket
  const groups: InterviewGroup[] = [
    {
      title: 'Awaiting Confirmation',
      records: interviewRecords.filter(r =>
        r.domain_status === 'InterviewAwaitingConfirmation'
      ),
    },
    {
      title: 'Scheduled',
      records: interviewRecords.filter(r =>
        r.domain_status === 'InterviewRequestScheduled' ||
        r.domain_status === 'InterviewScheduled'
      ),
    },
    {
      title: 'Awaiting Feedback',
      records: interviewRecords.filter(r =>
        r.domain_status === 'AwaitingFeedback'
      ),
    },
    {
      title: 'Feedback Due',
      records: interviewRecords.filter(r =>
        r.domain_status === 'FeedbackDue'
      ),
    },
  ];

  // Also include any with interview_state but not captured above
  const groupedIds = new Set(groups.flatMap(g => g.records.map(r => r.id)));
  const otherInterview = interviewRecords.filter(r => !groupedIds.has(r.id));
  if (otherInterview.length > 0) {
    groups.push({ title: 'Other Interview Activity', records: otherInterview });
  }

  const nonEmptyGroups = groups.filter(g => g.records.length > 0);

  return (
    <div className="view-enter figma-secondary-view figma-interviews-view" data-layer="Interviews / Frame">
      <h1 className="view-title">Interviews</h1>
      <p className="view-subtitle">
        {interviewRecords.length} record{interviewRecords.length !== 1 ? 's' : ''} with active interview workflows
      </p>

      {nonEmptyGroups.length === 0 ? (
        <EmptyState
          icon="📅"
          title="No active interviews"
          message="No records currently have interview-related status."
        />
      ) : (
        <div className="interview-groups">
          {nonEmptyGroups.map(group => (
            <section key={group.title} className="interview-group" aria-label={group.title} data-layer={`Interviews / ${group.title}`}>
              <div className="interview-group-header">
                <h2 className="interview-group-title">{group.title}</h2>
                <span className="interview-group-count">{group.records.length}</span>
              </div>
              {group.records.map(r => (
                <InterviewCard key={r.id} record={r} onClick={() => onRecordClick(r.id)} />
              ))}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

function InterviewCard({ record, onClick }: { record: RecordHeader; onClick: () => void }) {
  const deadlineInfo = getDeadlineStatus(record.feedback_due_at);
  const nextAction = getNextAction(record);

  return (
    <button className="interview-card" onClick={onClick}>
      <div className="interview-card-row">
        <StatusPill domainStatus={record.domain_status} threadMessageCount={record.thread_message_count} size="sm" />
        <span className="interview-card-name" title={record.candidate_name || undefined}>
          {record.candidate_name || 'Unknown'}
        </span>
      </div>

      <div className="interview-card-meta">
        {record.skill && (
          <span className="interview-card-field" title={record.skill}>
            <span className="interview-card-field-label">Requirement</span>
            {record.skill}
          </span>
        )}
        {record.customer && (
          <span className="interview-card-field" title={record.customer}>
            <span className="interview-card-field-label">Customer</span>
            {record.customer}
          </span>
        )}
      </div>

      <div className="interview-card-meta">
        {record.interview_updated_at && (
          <span className="interview-card-field" title={formatExactET(record.interview_updated_at)}>
            <span className="interview-card-field-label">Last update</span>
            {formatRelativeDate(record.interview_updated_at)}
          </span>
        )}
        {record.feedback_due_at && (
          <span className="interview-card-field" title={formatExactET(record.feedback_due_at)}>
            <span className="interview-card-field-label">Feedback due</span>
            {formatDeadlineDate(record.feedback_due_at)}
          </span>
        )}
        {deadlineInfo && (
          <span className={`interview-card-deadline ${deadlineInfo.className}`}>
            {deadlineInfo.label}
          </span>
        )}
      </div>

      <div className="interview-card-footer">
        <span className="interview-card-action">→ {nextAction}</span>
        <span className="interview-card-time" title={formatExactET(record.latest_logical_timestamp)}>
          {formatRelativeDate(record.latest_logical_timestamp)}
        </span>
      </div>
    </button>
  );
}
