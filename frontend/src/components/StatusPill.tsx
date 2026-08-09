import { getDisplayStatus } from '../utils/displayStatus';

interface StatusPillProps {
  domainStatus: string;
  threadMessageCount?: number;
  size?: 'sm' | 'md';
}

export function StatusPill({ domainStatus, threadMessageCount, size = 'md' }: StatusPillProps) {
  const ds = getDisplayStatus(domainStatus, threadMessageCount);
  return (
    <span
      className={`status-pill ${ds.className} ${size === 'sm' ? 'status-pill-sm' : ''}`}
      role="status"
      aria-label={ds.label}
    >
      <span className="status-pill-dot" aria-hidden="true" />
      {ds.label}
    </span>
  );
}
