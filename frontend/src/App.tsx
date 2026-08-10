import { useState, useRef, useCallback, useEffect } from 'react';
import { AppShell } from './components/AppShell';
import { LoadingState, ErrorState } from './components/LoadingState';
import { DashboardView } from './views/DashboardView';
import { RecordsView } from './views/RecordsView';
import { RecordWorkspace } from './views/RecordWorkspace';
import { InterviewsView } from './views/InterviewsView';
import { RetentionView } from './views/RetentionView';
import { useRecords } from './hooks/useRecords';
import type { ViewName } from './types';
import './App.css';

const SIDEBAR_KEY = 'fua-sidebar-collapsed';

function App() {
  const [activeView, setActiveView] = useState<ViewName>('dashboard');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try { return localStorage.getItem(SIDEBAR_KEY) === '1'; }
    catch { return false; }
  });
  const [globalSearch, setGlobalSearch] = useState('');
  const lastClickedIdRef = useRef<string | null>(null);

  const {
    dashboard, selectedRecord, loading, recordLoading, error,
    mailboxRefreshing, mailboxRefreshMessage, mailboxRefreshError,
    fetchDashboard, runMailboxReview, openRecord, closeRecord, refreshAllData,
  } = useRecords();

  // Persist sidebar preference
  useEffect(() => {
    try { localStorage.setItem(SIDEBAR_KEY, sidebarCollapsed ? '1' : '0'); }
    catch { /* ponytail: localStorage unavailable is fine */ }
  }, [sidebarCollapsed]);

  // Return focus to selected row after panel close (#18, #20)
  const handleClosePanel = useCallback(() => {
    closeRecord();
    requestAnimationFrame(() => {
      if (lastClickedIdRef.current) {
        const row = document.querySelector(
          `[data-record-id="${lastClickedIdRef.current}"]`
        ) as HTMLElement | null;
        row?.focus();
      }
    });
  }, [closeRecord]);

  const handleNavigate = (view: ViewName) => {
    setActiveView(view);
    closeRecord();
  };

  const handleRecordClick = (id: string) => {
    lastClickedIdRef.current = id;
    openRecord(id);
    if (activeView === 'dashboard') {
      setActiveView('records');
    }
  };

  const handleSearchChange = (q: string) => {
    setGlobalSearch(q);
    if (q && activeView === 'dashboard') {
      setActiveView('records');
    }
  };

  let content;
  if (error) {
    content = <ErrorState message={error} onRetry={fetchDashboard} />;
  } else if (loading && !dashboard) {
    content = <LoadingState variant="dashboard" />;
  } else if (dashboard) {
    switch (activeView) {
      case 'dashboard':
        content = (
          <DashboardView
            dashboard={dashboard}
            onRecordClick={handleRecordClick}
            onNavigate={handleNavigate}
          />
        );
        break;
      case 'records':
        content = (
          <RecordsView
            records={dashboard.records}
            onRecordClick={handleRecordClick}
            selectedRecordId={selectedRecord?.id}
            globalSearch={globalSearch}
          />
        );
        break;
      case 'interviews':
        content = (
          <InterviewsView
            records={dashboard.records}
            onRecordClick={handleRecordClick}
          />
        );
        break;
      case 'retention':
        content = (
          <RetentionView
            dashboard={dashboard}
          />
        );
        break;
    }
  }

  return (
    <AppShell
      activeView={activeView}
      sidebarCollapsed={sidebarCollapsed}
      searchQuery={globalSearch}
      mailboxRefreshing={mailboxRefreshing}
      mailboxRefreshMessage={mailboxRefreshMessage}
      mailboxRefreshError={mailboxRefreshError}
      onNavigate={handleNavigate}
      onToggleSidebar={() => setSidebarCollapsed(c => !c)}
      onSearchChange={handleSearchChange}
      onMailboxReview={runMailboxReview}
    >
      {content}
      {selectedRecord !== null && (
        <RecordWorkspace
          record={selectedRecord}
          loading={recordLoading}
          onClose={handleClosePanel}
          onRefreshRecord={(recordId) => refreshAllData(recordId)}
        />
      )}
    </AppShell>
  );
}

export default App;
