import type { ViewName } from '../types';
import { IconDashboard, IconQueue, IconInterview, IconRetention, IconExpand, IconCollapse } from './icons';
import { playSound } from '../utils/audio';
import { SidebarBrandFooter } from './SidebarBrandFooter';

interface SidebarProps {
  activeView: ViewName;
  collapsed: boolean;
  onNavigate: (view: ViewName) => void;
  onToggle: () => void;
}

const NAV_ITEMS: { view: ViewName; label: string; Icon: typeof IconDashboard }[] = [
  { view: 'dashboard',  label: 'Today',                  Icon: IconDashboard },
  { view: 'records',    label: 'Work Queue',              Icon: IconQueue },
  { view: 'interviews', label: 'Interviews',              Icon: IconInterview },
  { view: 'retention',  label: 'Retention & Operations',  Icon: IconRetention },
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
          onClick={() => { playSound('click'); onToggle(); }}
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
            onClick={() => { playSound('click'); onNavigate(item.view); }}
            aria-current={activeView === item.view ? 'page' : undefined}
            title={collapsed ? item.label : undefined}
            aria-label={collapsed ? item.label : undefined}
          >
            <span className="sidebar-icon"><item.Icon size={18} /></span>
            {!collapsed && <span className="sidebar-label">{item.label}</span>}
          </button>
        ))}
      </nav>

      <SidebarBrandFooter collapsed={collapsed} />
    </aside>
  );
}
