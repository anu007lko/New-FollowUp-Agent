import { useState, useEffect, useRef } from 'react';
import { IconSearch, IconRefresh } from './icons';
import { isMuted, setMuted, playSound } from '../utils/audio';

interface TopBarProps {
  sectionTitle: string;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  onMailboxReview: () => void;
  mailboxRefreshing: boolean;
  mailboxRefreshMessage: string | null;
  mailboxRefreshError: string | null;
}

/** Views that render their own section header — suppress the topbar duplicate. */
const VIEWS_WITH_OWN_HEADER = ['Work Queue', 'Interviews'];

/** Platform-appropriate modifier key label. */
const MOD_LABEL =
  typeof navigator !== 'undefined' && /Mac|iPhone|iPad|iPod/i.test(navigator.platform ?? navigator.userAgent)
    ? 'Cmd'
    : 'Ctrl';

export function TopBar({
  sectionTitle, searchQuery, onSearchChange, onMailboxReview, mailboxRefreshing,
  mailboxRefreshMessage, mailboxRefreshError,
}: TopBarProps) {
  const isToday = sectionTitle === 'Dashboard';
  const hideTitle = VIEWS_WITH_OWN_HEADER.includes(sectionTitle);

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

  const searchRef = useRef<HTMLInputElement>(null);

  // Cmd+K / Ctrl+K → focus global search
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName;
      const editable =
        tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' ||
        (e.target as HTMLElement)?.isContentEditable;
      if (editable) return;

      const isMod = /Mac|iPhone|iPad|iPod/i.test(navigator.platform ?? navigator.userAgent)
        ? e.metaKey
        : e.ctrlKey;

      if (isMod && e.key === 'k') {
        const el = searchRef.current;
        if (el) {
          e.preventDefault();
          el.focus();
        }
      }
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <header className={`topbar ${isToday ? 'figma-topbar' : ''}`} role="banner" data-layer="Header / Utility Bar">
      {isToday ? (
        <div className="figma-date" data-layer="Date / Current Day"><span aria-hidden="true">{dayNumber}</span>{datePart}<b>·</b>{weekday}</div>
      ) : hideTitle ? null : (
        <span className="topbar-section-title">{sectionTitle}</span>
      )}

      <div className={`topbar-search ${isToday ? 'figma-dashboard-search' : ''}`}>
        <span className="topbar-search-icon"><IconSearch size={15} /></span>
        <input
          ref={searchRef}
          type="search"
          className="topbar-search-input"
          placeholder="Jump to candidate, Job ID, customer…"
          value={searchQuery}
          onChange={e => onSearchChange(e.target.value)}
          aria-label="Search records"
        />
        <kbd className="topbar-kbd-hint" aria-hidden="true">{MOD_LABEL} K</kbd>
      </div>

      <div className="topbar-right" data-layer="Header / Controls">
        <div className={`topbar-status figma-local-status ${mailboxRefreshError ? 'topbar-status-error' : ''}`} role="status" aria-live="polite" data-layer="Status / Local Only">
          <span className={`topbar-status-dot ${mailboxRefreshError ? 'topbar-status-dot-warn' : 'topbar-status-dot-ok'}`} />
          <span>{mailboxRefreshError || mailboxRefreshMessage || 'Local only'}</span>
          <span className="sr-only">Daily review 8:00 AM ET</span>
        </div>
        <SoundToggleButton />
        <button
          className="btn btn-secondary btn-sm topbar-review-button"
          data-layer="Action / Refresh"
          onClick={() => { playSound('refresh'); onMailboxReview(); }}
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

function SoundToggleButton() {
  const [muted, setMutedState] = useState(isMuted());

  const toggleSound = () => {
    const next = !muted;
    setMuted(next);
    setMutedState(next);
    if (!next) {
      playSound('click');
    }
  };

  const label = muted ? 'Enable interface sounds' : 'Mute interface sounds';

  return (
    <button
      type="button"
      className="btn btn-secondary btn-sm topbar-sound-toggle"
      onClick={toggleSound}
      aria-label={label}
      title={label}
      style={{ padding: '6px 10px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}
    >
      {muted ? (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M11 5L6 9H2v6h4l5 4V5z" />
          <line x1="23" y1="9" x2="17" y2="15" />
          <line x1="17" y1="9" x2="23" y2="15" />
        </svg>
      ) : (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
          <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07" />
        </svg>
      )}
    </button>
  );
}
