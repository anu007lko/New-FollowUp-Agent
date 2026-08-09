import { IconSearch, IconRefresh } from './icons';

interface TopBarProps {
  sectionTitle: string;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  onMailboxReview: () => void;
  mailboxRefreshing: boolean;
  mailboxRefreshMessage: string | null;
  mailboxRefreshError: string | null;
}

export function TopBar({
  sectionTitle, searchQuery, onSearchChange, onMailboxReview, mailboxRefreshing,
  mailboxRefreshMessage, mailboxRefreshError,
}: TopBarProps) {
  const isToday = sectionTitle === 'Dashboard';
  const today = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
    weekday: 'long',
  }).formatToParts(new Date());
  const dayNumber = today.find(part => part.type === 'day')?.value;
  const datePart = `${today.find(part => part.type === 'month')?.value} ${today.find(part => part.type === 'day')?.value}, ${today.find(part => part.type === 'year')?.value}`;
  const weekday = today.find(part => part.type === 'weekday')?.value;

  return (
    <header className={`topbar ${isToday ? 'figma-topbar' : ''}`} role="banner" data-layer="Header / Utility Bar">
      {isToday ? (
        <div className="figma-date" data-layer="Date / Current Day"><span aria-hidden="true">{dayNumber}</span>{datePart}<b>·</b>{weekday}</div>
      ) : (
        <span className="topbar-section-title">{sectionTitle}</span>
      )}

      <div className={`topbar-search ${isToday ? 'figma-dashboard-search' : ''}`}>
        <span className="topbar-search-icon"><IconSearch size={15} /></span>
        <input
          type="search"
          className="topbar-search-input"
          placeholder="Jump to candidate, Job ID, customer…"
          value={searchQuery}
          onChange={e => onSearchChange(e.target.value)}
          aria-label="Search records"
        />
      </div>

      <div className="topbar-right" data-layer="Header / Controls">
        <div className={`topbar-status figma-local-status ${mailboxRefreshError ? 'topbar-status-error' : ''}`} role="status" aria-live="polite" data-layer="Status / Local Only">
          <span className={`topbar-status-dot ${mailboxRefreshError ? 'topbar-status-dot-warn' : 'topbar-status-dot-ok'}`} />
          <span>{mailboxRefreshError || mailboxRefreshMessage || 'Local only'}</span>
          <span className="sr-only">Daily review 8:00 AM ET</span>
        </div>
        <button
          className="btn btn-secondary btn-sm topbar-review-button"
          data-layer="Action / Refresh"
          onClick={onMailboxReview}
          disabled={mailboxRefreshing}
          aria-label="Review mailbox now"
          title="Import new submissions and refresh all tracked Outlook conversations"
        >
          <IconRefresh size={16} className={mailboxRefreshing ? 'icon-spin' : undefined} />
          <span>{mailboxRefreshing ? 'Refreshing…' : isToday ? 'Refresh' : 'Review mailbox now'}</span>
        </button>
      </div>
    </header>
  );
}
