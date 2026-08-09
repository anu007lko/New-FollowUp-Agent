// Single authoritative display-status mapping.
// All components must use this utility — never duplicate status logic.

export interface DisplayStatus {
  label: string;
  colorVar: string;    // CSS custom property name, e.g. '--status-review'
  className: string;   // CSS class for pill styling
  description: string; // One-line explanation for metric cards
  icon: string;        // Key for icon context (not used for rendering directly)
}

const STATUS_MAP: Record<string, DisplayStatus> = {
  AwaitingResponse:              { label: 'Awaiting Response', colorVar: '--status-awaiting',   className: 'status-awaiting',    description: 'Waiting for external reply',             icon: 'clock' },
  InterviewAwaitingConfirmation: { label: 'Interview Awaiting Confirmation', colorVar: '--status-interview', className: 'status-interview', description: 'Interview needs manager confirmation',   icon: 'calendar' },
  NewSubmission:                 { label: 'New Submission',    colorVar: '--status-review',     className: 'status-review',      description: 'New submission needs review',             icon: 'mail' },
  NeedsReview:                   { label: 'Needs Review',      colorVar: '--status-review',     className: 'status-review',      description: 'Requires manager review and decision',   icon: 'eye' },
  AwaitingFeedback:              { label: 'Awaiting Feedback', colorVar: '--status-awaiting',   className: 'status-awaiting',    description: 'Feedback expected from client or team',   icon: 'clock' },
  PendingFollowUp:               { label: 'Follow-up Due',     colorVar: '--status-followup',   className: 'status-followup',    description: 'Follow-up is overdue or due soon',       icon: 'alert' },
  FeedbackDue:                   { label: 'Feedback Due',      colorVar: '--status-feedback',   className: 'status-feedback',    description: 'Feedback deadline approaching or passed', icon: 'alert' },
  ManagerActionRequired:         { label: 'Action Required',   colorVar: '--status-action',     className: 'status-action',      description: 'Manager decision is needed',             icon: 'alert' },
  InEvaluation:                  { label: 'In Evaluation',     colorVar: '--status-evaluation', className: 'status-evaluation',  description: 'Currently under evaluation',             icon: 'search' },
  InterviewRequestScheduled:     { label: 'Interview',         colorVar: '--status-interview',  className: 'status-interview',   description: 'Interview scheduled or requested',       icon: 'calendar' },
  Closed:                        { label: 'Closed',            colorVar: '--status-closed',     className: 'status-closed',      description: 'Record closed and archived',             icon: 'check' },
  ClientRejected:                { label: 'Rejected',          colorVar: '--status-closed',     className: 'status-closed',      description: 'Client rejected the candidate',          icon: 'close' },
  PositionClosed:                { label: 'Position Closed',   colorVar: '--status-closed',     className: 'status-closed',      description: 'Position is no longer open',             icon: 'close' },
};

const INCOMPLETE: DisplayStatus = {
  label: 'Incomplete', colorVar: '--status-incomplete', className: 'status-incomplete',
  description: 'Missing conversation data', icon: 'warning'
};

const FALLBACK: DisplayStatus = {
  label: 'Unknown', colorVar: '--status-closed', className: 'status-closed',
  description: 'Unrecognized status', icon: 'help'
};

/**
 * Returns the display status for a record.
 * @param domainStatus - The raw domain_status from the backend
 * @param threadMessageCount - Number of thread messages (0 = legacy placeholder)
 */
export function getDisplayStatus(domainStatus: string, threadMessageCount?: number): DisplayStatus {
  // Legacy placeholders: NewSubmission with no messages
  if (domainStatus === 'NewSubmission' && threadMessageCount !== undefined && threadMessageCount === 0) {
    return INCOMPLETE;
  }
  return STATUS_MAP[domainStatus] || FALLBACK;
}

/** Human-readable label only */
export function getDisplayLabel(domainStatus: string, threadMessageCount?: number): string {
  return getDisplayStatus(domainStatus, threadMessageCount).label;
}

/** Check if a record has interview-related status */
export function isInterviewRelated(domainStatus: string, interviewState?: string): boolean {
  return domainStatus === 'InterviewRequestScheduled'
    || domainStatus === 'InterviewScheduled'
    || domainStatus === 'InterviewAwaitingConfirmation'
    || domainStatus === 'AwaitingFeedback'
    || domainStatus === 'FeedbackDue'
    || (interviewState !== undefined && interviewState !== null && interviewState !== '' && interviewState !== 'None' && interviewState !== 'none');
}

/** Format a timestamp for display */
export function formatTimestamp(iso?: string): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '—';
    return d.toLocaleString('en-US', {
      month: 'short', day: 'numeric',
      hour: 'numeric', minute: '2-digit', hour12: true,
      timeZone: 'America/New_York'
    });
  } catch { return '—'; }
}

/** Format a relative date */
export function formatRelativeDate(iso?: string): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffH = Math.floor(diffMs / 3600000);
    const diffD = Math.floor(diffMs / 86400000);
    if (diffH < 1) return 'Just now';
    if (diffH < 24) return `${diffH}h ago`;
    if (diffD < 7) return `${diffD}d ago`;
    return formatTimestamp(iso);
  } catch { return '—'; }
}

/** Get greeting based on local time */
export function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}
