/**
 * Deadline utilities — pure functions for formatting authoritative timestamps.
 * Never calculates deadlines from display events or notes.
 */

interface DeadlineStatus {
  label: string;
  isOverdue: boolean;
  className: string;
}

/** Format a deadline timestamp with remaining/overdue time. */
export function getDeadlineStatus(iso?: string): DeadlineStatus | null {
  if (!iso) return null;
  try {
    const due = new Date(iso);
    if (isNaN(due.getTime())) return null;
    const now = new Date();
    const diffMs = due.getTime() - now.getTime();
    const diffH = Math.round(diffMs / 3600000);
    const diffD = Math.round(diffMs / 86400000);

    if (diffMs < 0) {
      const overH = Math.abs(diffH);
      const overD = Math.abs(diffD);
      return {
        label: overD > 1 ? `Overdue by ${overD} days` : `Overdue by ${overH}h`,
        isOverdue: true,
        className: 'deadline-overdue',
      };
    }

    if (diffH < 1) return { label: 'Due now', isOverdue: false, className: 'deadline-urgent' };
    if (diffH < 24) return { label: `${diffH}h remaining`, isOverdue: false, className: 'deadline-soon' };
    return { label: `${diffD}d remaining`, isOverdue: false, className: 'deadline-ok' };
  } catch {
    return null;
  }
}

/** Format an ISO timestamp for display as a deadline label. */
export function formatDeadlineDate(iso?: string): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '—';
    return d.toLocaleString('en-US', {
      month: 'short', day: 'numeric',
      hour: 'numeric', minute: '2-digit', hour12: true,
      timeZone: 'America/New_York',
    });
  } catch {
    return '—';
  }
}

/** Format an ISO timestamp as an exact ET string for tooltip use. */
export function formatExactET(iso?: string): string | undefined {
  if (!iso) return undefined;
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return undefined;
    return d.toLocaleString('en-US', {
      weekday: 'short', month: 'short', day: 'numeric',
      year: 'numeric', hour: 'numeric', minute: '2-digit',
      second: '2-digit', hour12: true,
      timeZone: 'America/New_York',
    }) + ' ET';
  } catch {
    return undefined;
  }
}
