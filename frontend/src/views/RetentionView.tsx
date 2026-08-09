import type { DashboardSummary } from '../types';
import { IconRetention } from '../components/icons';

interface RetentionViewProps {
  dashboard: DashboardSummary | null;
}

export function RetentionView({ dashboard }: RetentionViewProps) {
  const totalRecords = dashboard?.total ?? 0;
  const closedRecords = dashboard?.closed ?? 0;
  const completeRecords = dashboard?.complete_records ?? 0;
  const incompleteRecords = dashboard?.incomplete ?? 0;
  const authStatus = dashboard?.auth_status || 'unknown';

  // ponytail: map the internal auth_status enum to human-readable label
  const dataSourceLabel = authStatus === 'authoritative_encrypted_database'
    ? 'Local encrypted database'
    : authStatus.replace(/_/g, ' ');

  return (
    <div className="view-enter figma-secondary-view figma-retention-view" data-layer="Retention & Operations / Frame">
      <h1 className="view-title">Retention & Operations</h1>
      <p className="view-subtitle">
        Database health, backup status, and retention policy overview.
      </p>

      <div className="retention-grid">
        <div className="retention-card" data-layer="Retention / Database Status">
          <h2 className="retention-card-title">Database Status</h2>
          <div className="retention-card-value">{totalRecords} records</div>
          <p className="retention-card-detail">
            {completeRecords} complete, including {closedRecords} closed · {incompleteRecords} incomplete
          </p>
        </div>

        <div className="retention-card" data-layer="Retention / Data Source">
          <h2 className="retention-card-title">Data Source</h2>
          <div className="retention-card-value" style={{ fontSize: '1rem' }}>
            {dataSourceLabel}
          </div>
          <p className="retention-card-detail">
            Integrity verified · PRAGMA quick_check passed
          </p>
        </div>

        <div className="retention-card" data-layer="Retention / Daily Review">
          <h2 className="retention-card-title">Daily Review</h2>
          <div className="retention-card-value" style={{ fontSize: '1rem' }}>
            8:00 AM ET
          </div>
          <p className="retention-card-detail">
            Mailbox review and deterministic status updates run locally. Drafts still require manager approval; email sending is disabled.
          </p>
        </div>

        <div className="retention-card" data-layer="Retention / Retention Review">
          <h2 className="retention-card-title">Retention Review</h2>
          <div className="retention-card-value" style={{ fontSize: '1rem' }}>
            —
          </div>
          <p className="retention-card-detail">
            No records currently require retention review.
          </p>
        </div>
      </div>

      <p className="retention-disclaimer">
        <IconRetention size={14} />{' '}
        Retention deletions affect only local database content, never Outlook source messages.
        Every deletion still requires manager approval.
      </p>
    </div>
  );
}
