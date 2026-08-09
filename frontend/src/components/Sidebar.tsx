import type { ViewName } from '../types';
import { IconDashboard, IconQueue, IconInterview, IconRetention, IconExpand, IconCollapse } from './icons';

interface SidebarProps {
  activeView: ViewName;
  collapsed: boolean;
  onNavigate: (view: ViewName) => void;
  onToggle: () => void;
}

const NAV_ITEMS: { view: ViewName; label: string; Icon: typeof IconDashboard }[] = [
  { view: 'dashboard',  label: 'Today',              Icon: IconDashboard },
  { view: 'records',    label: 'Work Queue',          Icon: IconQueue },
  { view: 'interviews', label: 'Interviews',          Icon: IconInterview },
];

export function Sidebar({ activeView, collapsed, onNavigate, onToggle }: SidebarProps) {
  return (
    <aside className={`sidebar ${collapsed ? 'sidebar-collapsed' : ''}`} aria-label="Main navigation" data-layer="Navigation / Sidebar">
      <div className="sidebar-header" data-layer="Brand / Header">
        <div className="sidebar-brand" data-layer="Brand / Mark">
          <div className="sidebar-mark" aria-hidden="true" />
          {!collapsed && <span className="sidebar-title">Follow‑Up</span>}
        </div>
        <button
          className="sidebar-toggle"
          onClick={onToggle}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <IconExpand size={16} /> : <IconCollapse size={16} />}
        </button>
      </div>

      <nav className="sidebar-nav" data-layer="Navigation / Primary">
        {NAV_ITEMS.map(item => (
          <button
            key={item.view}
            className={`sidebar-item ${activeView === item.view ? 'sidebar-item-active' : ''}`}
            onClick={() => onNavigate(item.view)}
            aria-current={activeView === item.view ? 'page' : undefined}
            title={collapsed ? item.label : undefined}
            aria-label={collapsed ? item.label : undefined}
          >
            <span className="sidebar-icon"><item.Icon size={18} /></span>
            {!collapsed && <span className="sidebar-label">{item.label}</span>}
          </button>
        ))}
      </nav>

      <div className="sidebar-footer" data-layer="Navigation / Footer">
        {!collapsed ? (
          <>
            <div className="figma-outlook-card" data-layer="Status / Outlook Drafts">
              <span className="figma-outlook-icon">O</span>
              <p>Drafts open<br />in Outlook.</p>
              <small>You send<br />manually.</small>
            </div>
            <button
              className={`sidebar-ops-link ${activeView === 'retention' ? 'active' : ''}`}
              onClick={() => onNavigate('retention')}
            >
              <IconRetention size={15} />
              Retention & operations
            </button>
            <div className="figma-prism" aria-hidden="true" data-layer="Decoration / Prism" />
            <span className="sr-only">Ready for daily review · Local actions available · Email sending disabled</span>
          </>
        ) : (
          <div title="Ready for daily review" style={{ textAlign: 'center' }}>
            <span className="sidebar-health-dot" />
          </div>
        )}
      </div>
    </aside>
  );
}
