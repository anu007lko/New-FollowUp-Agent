// Inline SVG icon components — zero external dependencies.
// All icons are 16px or 20px, with aria-hidden="true" by default.

interface IconProps {
  size?: number;
  className?: string;
}

const defaults = (p: IconProps) => ({
  width: p.size || 18,
  height: p.size || 18,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.75,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true as const,
  className: p.className || '',
});

export function IconDashboard(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="4" rx="1" />
      <rect x="3" y="14" width="7" height="4" rx="1" />
      <rect x="14" y="11" width="7" height="7" rx="1" />
    </svg>
  );
}

export function IconQueue(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <line x1="8" y1="6" x2="21" y2="6" />
      <line x1="8" y1="12" x2="21" y2="12" />
      <line x1="8" y1="18" x2="21" y2="18" />
      <line x1="3" y1="6" x2="3.01" y2="6" />
      <line x1="3" y1="12" x2="3.01" y2="12" />
      <line x1="3" y1="18" x2="3.01" y2="18" />
    </svg>
  );
}

export function IconInterview(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <line x1="16" y1="2" x2="16" y2="6" />
      <line x1="8" y1="2" x2="8" y2="6" />
      <line x1="3" y1="10" x2="21" y2="10" />
      <path d="M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01" />
    </svg>
  );
}

export function IconRetention(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}

export function IconSearch(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

export function IconRefresh(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <polyline points="23 4 23 10 17 10" />
      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
    </svg>
  );
}

export function IconChevronDown(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

export function IconChevronRight(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

export function IconChevronLeft(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <polyline points="15 18 9 12 15 6" />
    </svg>
  );
}

export function IconClose(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

export function IconBack(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <line x1="19" y1="12" x2="5" y2="12" />
      <polyline points="12 19 5 12 12 5" />
    </svg>
  );
}

export function IconWarning(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}

export function IconCheck(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

export function IconClock(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

export function IconMail(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
      <polyline points="22 6 12 13 2 6" />
    </svg>
  );
}

export function IconNote(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <polyline points="10 9 9 9 8 9" />
    </svg>
  );
}

export function IconMoreHorizontal(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
      <circle cx="19" cy="12" r="1" fill="currentColor" stroke="none" />
      <circle cx="5" cy="12" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function IconFilter(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
    </svg>
  );
}

export function IconSortDesc(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <path d="M11 5h10M11 9h7M11 13h4M3 17l3 3 3-3M6 18V4" />
    </svg>
  );
}

export function IconSortAsc(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <path d="M11 5h4M11 9h7M11 13h10M3 17l3-3 3 3M6 18V4" />
    </svg>
  );
}

export function IconCollapse(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <line x1="9" y1="3" x2="9" y2="21" />
      <path d="M14 9l3 3-3 3" />
    </svg>
  );
}

export function IconExpand(p: IconProps = {}) {
  return (
    <svg {...defaults(p)}>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <line x1="9" y1="3" x2="9" y2="21" />
      <path d="M16 9l-3 3 3 3" />
    </svg>
  );
}

export function IconArrowUp(p: IconProps = {}) {
  return (
    <svg {...defaults(p)} viewBox="0 0 16 16">
      <path d="M8 3v10M4 7l4-4 4 4" />
    </svg>
  );
}

export function IconArrowDown(p: IconProps = {}) {
  return (
    <svg {...defaults(p)} viewBox="0 0 16 16">
      <path d="M8 13V3M4 9l4 4 4-4" />
    </svg>
  );
}

export function IconDot(p: IconProps = {}) {
  const s = p.size || 8;
  return (
    <svg width={s} height={s} viewBox="0 0 8 8" aria-hidden className={p.className || ''}>
      <circle cx="4" cy="4" r="3" fill="currentColor" />
    </svg>
  );
}
