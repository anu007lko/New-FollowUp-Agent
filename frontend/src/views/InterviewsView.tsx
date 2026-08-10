import { useState, useMemo } from 'react';
import type { RecordHeader } from '../types';
import { StatusPill } from '../components/StatusPill';
import { EmptyState } from '../components/LoadingState';
import { formatRelativeDate, isInterviewRelated } from '../utils/displayStatus';
import { getDeadlineStatus, formatExactET } from '../utils/deadlineUtils';
import { playSound } from '../utils/audio';

interface InterviewsViewProps {
  records: RecordHeader[];
  onRecordClick: (id: string) => void;
}

interface InterviewGroup {
  title: string;
  records: RecordHeader[];
}

/** Which metric filter is active. */
type MetricFilter = 'total' | 'awaitingConfirmation' | 'scheduled' | 'feedbackOverdue';

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

/**
 * Feedback Overdue metric — counts each record only once.
 *
 * A record is overdue if:
 *   1. domain_status === 'FeedbackDue' (backend verified the 48h timer expired), OR
 *   2. domain_status === 'AwaitingFeedback' AND feedback_due_at exists AND
 *      getDeadlineStatus(feedback_due_at).isOverdue === true.
 *
 * Never infers or invents missing deadlines.
 */
function isFeedbackOverdue(r: RecordHeader): boolean {
  if (r.domain_status === 'FeedbackDue') return true;
  if (r.domain_status === 'AwaitingFeedback' && r.feedback_due_at) {
    const dl = getDeadlineStatus(r.feedback_due_at);
    return dl?.isOverdue === true;
  }
  return false;
}

function countFeedbackOverdue(records: RecordHeader[]): number {
  const seen = new Set<string>();
  for (const r of records) {
    if (seen.has(r.id)) continue;
    if (isFeedbackOverdue(r)) seen.add(r.id);
  }
  return seen.size;
}

export function InterviewsView({ records, onRecordClick }: InterviewsViewProps) {
  const [activeMetric, setActiveMetric] = useState<MetricFilter>('total');

  const interviewRecords = useMemo(
    () => records.filter(r => isInterviewRelated(r.domain_status, r.interview_state)),
    [records],
  );

  // Metric card counts — derived from existing data, no backend calls
  const metrics = useMemo(() => {
    const awaitingConfirmation = interviewRecords.filter(
      r => r.domain_status === 'InterviewAwaitingConfirmation',
    ).length;
    const scheduled = interviewRecords.filter(
      r => r.domain_status === 'InterviewRequestScheduled' || r.domain_status === 'InterviewScheduled',
    ).length;
    const feedbackOverdue = countFeedbackOverdue(interviewRecords);
    return {
      total: interviewRecords.length,
      awaitingConfirmation,
      scheduled,
      feedbackOverdue,
    };
  }, [interviewRecords]);

  // Apply metric filter
  const visibleRecords = useMemo(() => {
    switch (activeMetric) {
      case 'awaitingConfirmation':
        return interviewRecords.filter(r => r.domain_status === 'InterviewAwaitingConfirmation');
      case 'scheduled':
        return interviewRecords.filter(
          r => r.domain_status === 'InterviewRequestScheduled' || r.domain_status === 'InterviewScheduled',
        );
      case 'feedbackOverdue': {
        const seen = new Set<string>();
        return interviewRecords.filter(r => {
          if (seen.has(r.id)) return false;
          if (isFeedbackOverdue(r)) { seen.add(r.id); return true; }
          return false;
        });
      }
      default:
        return interviewRecords;
    }
  }, [interviewRecords, activeMetric]);

  // Group by status bucket
  const groups: InterviewGroup[] = useMemo(() => {
    const g: InterviewGroup[] = [
      {
        title: 'Awaiting Confirmation',
        records: visibleRecords.filter(r =>
          r.domain_status === 'InterviewAwaitingConfirmation'
        ),
      },
      {
        title: 'Scheduled',
        records: visibleRecords.filter(r =>
          r.domain_status === 'InterviewRequestScheduled' ||
          r.domain_status === 'InterviewScheduled'
        ),
      },
      {
        title: 'Awaiting Feedback',
        records: visibleRecords.filter(r =>
          r.domain_status === 'AwaitingFeedback'
        ),
      },
      {
        title: 'Feedback Due',
        records: visibleRecords.filter(r =>
          r.domain_status === 'FeedbackDue'
        ),
      },
    ];

    // Also include any with interview_state but not captured above
    const groupedIds = new Set(g.flatMap(bucket => bucket.records.map(r => r.id)));
    const otherInterview = visibleRecords.filter(r => !groupedIds.has(r.id));
    if (otherInterview.length > 0) {
      g.push({ title: 'Other Interview Activity', records: otherInterview });
    }
    return g;
  }, [visibleRecords]);

  const nonEmptyGroups = groups.filter(g => g.records.length > 0);

  /** Toggle a specific metric; clicking active specific → reset to total. */
  function handleMetricClick(metric: MetricFilter) {
    playSound('click');
    if (metric === 'total') {
      setActiveMetric('total');
    } else {
      setActiveMetric(prev => prev === metric ? 'total' : metric);
    }
  }

  return (
    <div className="view-enter figma-secondary-view figma-interviews-view" data-layer="Interviews / Frame">
      <h1 className="view-title">Interviews</h1>
      <p className="view-subtitle">
        {interviewRecords.length} record{interviewRecords.length !== 1 ? 's' : ''} with active interview workflows
      </p>

      {/* Metric quick-filter buttons */}
      <div className="iv-metrics" role="group" aria-label="Interview metric filters">
        <button
          className={`iv-metric-card ${activeMetric === 'total' ? 'iv-metric-card--active' : ''}`}
          onClick={() => handleMetricClick('total')}
          aria-pressed={activeMetric === 'total'}
          type="button"
        >
          <span className="iv-metric-value">{metrics.total}</span>
          <span className="iv-metric-label">Total Active</span>
        </button>
        <button
          className={`iv-metric-card ${activeMetric === 'awaitingConfirmation' ? 'iv-metric-card--active' : ''}`}
          onClick={() => handleMetricClick('awaitingConfirmation')}
          aria-pressed={activeMetric === 'awaitingConfirmation'}
          type="button"
        >
          <span className="iv-metric-value">{metrics.awaitingConfirmation}</span>
          <span className="iv-metric-label">Awaiting Confirmation</span>
        </button>
        <button
          className={`iv-metric-card ${activeMetric === 'scheduled' ? 'iv-metric-card--active' : ''}`}
          onClick={() => handleMetricClick('scheduled')}
          aria-pressed={activeMetric === 'scheduled'}
          type="button"
        >
          <span className="iv-metric-value">{metrics.scheduled}</span>
          <span className="iv-metric-label">Scheduled</span>
        </button>
        <button
          className={`iv-metric-card iv-metric-card--overdue ${activeMetric === 'feedbackOverdue' ? 'iv-metric-card--active' : ''}`}
          onClick={() => handleMetricClick('feedbackOverdue')}
          aria-pressed={activeMetric === 'feedbackOverdue'}
          type="button"
        >
          <span className="iv-metric-value">{metrics.feedbackOverdue}</span>
          <span className="iv-metric-label">Feedback Overdue</span>
        </button>
      </div>

      {nonEmptyGroups.length === 0 ? (
        <EmptyState
          icon="📅"
          title={activeMetric === 'total' ? 'No active interviews' : `No ${activeMetric === 'awaitingConfirmation' ? 'interviews awaiting confirmation' : activeMetric === 'scheduled' ? 'scheduled interviews' : 'overdue feedback'}`}
          message={activeMetric === 'total'
            ? 'No records currently have interview-related status.'
            : 'No records match the selected metric. Click the metric again to show all.'}
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

  const candidateLabel = record.candidate_name || 'Unknown';
  const skillLabel = record.skill ? `Requirement: ${record.skill}` : undefined;
  const customerLabel = record.customer ? `Customer: ${record.customer}` : undefined;

  return (
    <button className="interview-card" onClick={() => { playSound('click'); onClick(); }} aria-label={`Interview record: ${candidateLabel}`}>
      {/* Row 1: Status pill + Job ID */}
      <div className="interview-card-row">
        <StatusPill domainStatus={record.domain_status} threadMessageCount={record.thread_message_count} size="sm" />
        {record.job_id && (
          <span className="interview-card-jobid">{record.job_id}</span>
        )}
      </div>

      {/* Row 2: Candidate name */}
      <div className="interview-card-candidate" title={record.candidate_name || undefined} aria-label={candidateLabel}>
        {candidateLabel}
      </div>

      {/* Row 3: Prominent action callout */}
      <div className="interview-card-action-row" aria-label={`Next action: ${nextAction}`}>
        <span className="interview-card-action-icon" aria-hidden="true">→</span>
        <span className="interview-card-action-text">{nextAction}</span>
        {deadlineInfo && (
          <span className={`interview-card-deadline ${deadlineInfo.className}`} role="status">
            {deadlineInfo.label}
          </span>
        )}
      </div>

      {/* Row 4: Context metadata */}
      <div className="interview-card-context">
        {record.skill && (
          <span className="interview-card-field" title={record.skill} aria-label={skillLabel}>
            <span className="interview-card-field-label">Requirement</span>
            {record.skill}
          </span>
        )}
        {record.customer && (
          <span className="interview-card-field" title={record.customer} aria-label={customerLabel}>
            <span className="interview-card-field-label">Customer</span>
            {record.customer}
          </span>
        )}
        <span className="interview-card-time" title={formatExactET(record.latest_logical_timestamp)} aria-label={`Last activity: ${formatExactET(record.latest_logical_timestamp) || formatRelativeDate(record.latest_logical_timestamp)}`}>
          {formatRelativeDate(record.latest_logical_timestamp)}
        </span>
      </div>
    </button>
  );
}
