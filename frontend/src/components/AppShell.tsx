import type { ReactNode } from 'react';
import type { ViewName } from '../types';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';

interface AppShellProps {
  children: ReactNode;
  activeView: ViewName;
  sidebarCollapsed: boolean;
  searchQuery: string;
  mailboxRefreshing: boolean;
  mailboxRefreshMessage: string | null;
  mailboxRefreshError: string | null;
  onNavigate: (view: ViewName) => void;
  onToggleSidebar: () => void;
  onSearchChange: (q: string) => void;
  onMailboxReview: () => void;
}

const SECTION_TITLES: Record<ViewName, string> = {
  dashboard: 'Dashboard',
  records: 'Work Queue',
  interviews: 'Interviews',
  retention: 'Retention & Operations',
};

export function AppShell({
  children, activeView, sidebarCollapsed, searchQuery, mailboxRefreshing,
  mailboxRefreshMessage, mailboxRefreshError,
  onNavigate, onToggleSidebar, onSearchChange, onMailboxReview
}: AppShellProps) {
  return (
    <div className={`app-shell ${sidebarCollapsed ? 'app-shell-collapsed' : ''}`}>
      <Sidebar
        activeView={activeView}
        collapsed={sidebarCollapsed}
        onNavigate={onNavigate}
        onToggle={onToggleSidebar}
      />
      <div className="app-main">
        <TopBar
          sectionTitle={SECTION_TITLES[activeView]}
          searchQuery={searchQuery}
          onSearchChange={onSearchChange}
          onMailboxReview={onMailboxReview}
          mailboxRefreshing={mailboxRefreshing}
          mailboxRefreshMessage={mailboxRefreshMessage}
          mailboxRefreshError={mailboxRefreshError}
        />
        <main className="app-content" role="main">
          {children}
        </main>
      </div>
    </div>
  );
}
