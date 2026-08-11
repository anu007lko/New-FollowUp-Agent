// Single authoritative display-status mapping.
// Visual token map keyed by backend DisplayTone and DTOs.

export interface DisplayStatus {
  label: string;
  colorVar: string;    // CSS custom property name
  className: string;   // CSS class for pill styling
  description: string; // Explanation
  icon: string;
}

const TONE_MAP: Record<string, { colorVar: string; className: string; icon: string }> = {
  review:    { colorVar: '--status-review',    className: 'status-review',    icon: 'eye' },
  tracking:  { colorVar: '--status-tracking',  className: 'status-tracking',  icon: 'clock' },
  action:    { colorVar: '--status-action',    className: 'status-action',    icon: 'alert' },
  interview: { colorVar: '--status-interview', className: 'status-interview', icon: 'calendar' },
  awaiting:  { colorVar: '--status-awaiting',  className: 'status-awaiting',  icon: 'clock' },
  feedback:  { colorVar: '--status-feedback',  className: 'status-feedback',  icon: 'alert' },
  closed:    { colorVar: '--status-closed',    className: 'status-closed',    icon: 'check' },
};

const LEGACY_STATUS_MAP: Record<string, DisplayStatus> = {
  NeedsReview:                   { label: 'Needs Review',      colorVar: '--status-review',     className: 'status-review',      description: 'Requires manager review', icon: 'eye' },
  Tracking:                      { label: 'Tracking',          colorVar: '--status-tracking',   className: 'status-tracking',    description: 'Active tracking',        icon: 'clock' },
  ActionRequired:                { label: 'Action Required',   colorVar: '--status-action',     className: 'status-action',      description: 'Manager action needed',   icon: 'alert' },
  InterviewScheduled:            { label: 'Interview Scheduled', colorVar: '--status-interview', className: 'status-interview', description: 'Interview scheduled',    icon: 'calendar' },
  FeedbackPending:               { label: 'Feedback Pending',  colorVar: '--status-awaiting',   className: 'status-awaiting',    description: 'Awaiting feedback',      icon: 'clock' },
  FeedbackDue:                   { label: 'Feedback Due',      colorVar: '--status-feedback',   className: 'status-feedback',    description: 'Feedback overdue',       icon: 'alert' },
  Closed:                        { label: 'Closed',            colorVar: '--status-closed',     className: 'status-closed',      description: 'Record closed',          icon: 'check' },
  // Backward compatibility aliases
  AwaitingResponse:              { label: 'Tracking',          colorVar: '--status-tracking',   className: 'status-tracking',    description: 'Active tracking',        icon: 'clock' },
  InterviewAwaitingConfirmation: { label: 'Interview Scheduled', colorVar: '--status-interview', className: 'status-interview', description: 'Interview scheduled',    icon: 'calendar' },
  NewSubmission:                 { label: 'Needs Review',      colorVar: '--status-review',     className: 'status-review',      description: 'Requires manager review', icon: 'mail' },
  AwaitingFeedback:              { label: 'Feedback Pending',  colorVar: '--status-awaiting',   className: 'status-awaiting',    description: 'Awaiting feedback',      icon: 'clock' },
  PendingFollowUp:               { label: 'Action Required',   colorVar: '--status-action',     className: 'status-action',      description: 'Action required',        icon: 'alert' },
  ManagerActionRequired:         { label: 'Action Required',   colorVar: '--status-action',     className: 'status-action',      description: 'Action required',        icon: 'alert' },
  InEvaluation:                  { label: 'Tracking',          colorVar: '--status-tracking',   className: 'status-tracking',    description: 'Active tracking',        icon: 'search' },
  InterviewRequestScheduled:     { label: 'Interview Scheduled', colorVar: '--status-interview', className: 'status-interview', description: 'Interview scheduled',    icon: 'calendar' },
  DuplicateSubmission:           { label: 'Duplicate Submission', colorVar: '--status-closed',  className: 'status-closed',      description: 'Duplicate submission',   icon: 'close' },
  ClientRejected:                { label: 'Client Rejected',   colorVar: '--status-closed',     className: 'status-closed',      description: 'Client rejected',        icon: 'close' },
  PositionClosed:                { label: 'Position Closed',   colorVar: '--status-closed',     className: 'status-closed',      description: 'Position closed',        icon: 'close' },
};

const FALLBACK: DisplayStatus = {
  label: 'Needs Review', colorVar: '--status-review', className: 'status-review',
  description: 'Requires manager review', icon: 'help'
};

/**
 * Returns the display status for a record. Uses backend-supplied display metadata if available.
 */
export function getDisplayStatus(
  domainStatus: string,
  _threadMessageCount?: number,
  category?: string,
  tone?: string,
  backendLabel?: string
): DisplayStatus {
  if (backendLabel && tone && TONE_MAP[tone]) {
    const t = TONE_MAP[tone];
    return {
      label: backendLabel,
      colorVar: t.colorVar,
      className: t.className,
      description: backendLabel,
      icon: t.icon
    };
  }

  if (_threadMessageCount === 0 && (domainStatus === 'NewSubmission' || domainStatus === 'NeedsReview')) {
    return { label: 'Incomplete', colorVar: '--status-review', className: 'status-review', description: 'Incomplete record', icon: 'help' };
  }

  if (category === 'Duplicate Submission' || category === 'Duplicate submission entry') {
    return { label: 'Duplicate Submission', colorVar: '--status-closed', className: 'status-closed', description: 'Duplicate submission', icon: 'close' };
  }
  if (category === 'Client Rejected') {
    return { label: 'Client Rejected', colorVar: '--status-closed', className: 'status-closed', description: 'Client rejected', icon: 'close' };
  }
  if (category === 'Position Closed') {
    return { label: 'Position Closed', colorVar: '--status-closed', className: 'status-closed', description: 'Position closed', icon: 'close' };
  }

  return LEGACY_STATUS_MAP[domainStatus] || FALLBACK;
}

/** Human-readable label only */
export function getDisplayLabel(domainStatus: string, _threadMessageCount?: number, category?: string, tone?: string, backendLabel?: string): string {
  return getDisplayStatus(domainStatus, _threadMessageCount, category, tone, backendLabel).label;
}

/** Check if a record has interview-related status */
export function isInterviewRelated(domainStatus: string, interviewState?: string): boolean {
  return domainStatus === 'InterviewRequestScheduled'
    || domainStatus === 'InterviewScheduled'
    || domainStatus === 'InterviewAwaitingConfirmation'
    || domainStatus === 'AwaitingFeedback'
    || domainStatus === 'FeedbackPending'
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
