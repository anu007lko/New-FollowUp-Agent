import { useState, useMemo, useCallback } from 'react';
import type { RecordHeader } from '../types';
import { StatusPill } from '../components/StatusPill';
import { EmptyState } from '../components/LoadingState';
import { IconSearch, IconWarning } from '../components/icons';
import { getDisplayStatus, formatTimestamp } from '../utils/displayStatus';
import { formatExactET } from '../utils/deadlineUtils';

interface RecordsViewProps {
  records: RecordHeader[];
  onRecordClick: (id: string) => void;
  selectedRecordId?: string | null;
  initialStatusFilter?: string;
  globalSearch?: string;
}

type SortField = 'latest_logical_timestamp' | 'candidate_name' | 'customer' | 'job_id' | 'domain_status';
type SortDir = 'asc' | 'desc';

const PAGE_SIZE = 20;

export function RecordsView({ records, onRecordClick, selectedRecordId, initialStatusFilter, globalSearch }: RecordsViewProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState(initialStatusFilter || 'all');
  const [completenessFilter, setCompletenessFilter] = useState<'all' | 'complete' | 'incomplete'>('all');
  const [sortField, setSortField] = useState<SortField>('latest_logical_timestamp');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [page, setPage] = useState(1);

  const effectiveSearch = globalSearch || searchQuery;

  const filtered = useMemo(() => {
    let result = [...records];

    if (effectiveSearch) {
      const q = effectiveSearch.toLowerCase();
      result = result.filter(r =>
        (r.candidate_name || '').toLowerCase().includes(q) ||
        (r.job_id || '').toLowerCase().includes(q) ||
        (r.ep_reference || '').toLowerCase().includes(q) ||
        (r.skill || '').toLowerCase().includes(q) ||
        (r.customer || '').toLowerCase().includes(q) ||
        (r.location || '').toLowerCase().includes(q)
      );
    }

    if (statusFilter !== 'all') {
      result = result.filter(r => {
        const ds = getDisplayStatus(r.domain_status, r.thread_message_count);
        return ds.label === statusFilter;
      });
    }

    if (completenessFilter === 'complete') {
      result = result.filter(r => (r.thread_message_count ?? 0) > 0);
    } else if (completenessFilter === 'incomplete') {
      result = result.filter(r => (r.thread_message_count ?? 0) === 0);
    }

    result.sort((a, b) => {
      let aVal: string = '';
      let bVal: string = '';
      switch (sortField) {
        case 'latest_logical_timestamp':
          aVal = a.latest_logical_timestamp || a.received_at || '';
          bVal = b.latest_logical_timestamp || b.received_at || '';
          break;
        case 'candidate_name':
          aVal = (a.candidate_name || '').toLowerCase();
          bVal = (b.candidate_name || '').toLowerCase();
          break;
        case 'customer':
          aVal = (a.customer || '').toLowerCase();
          bVal = (b.customer || '').toLowerCase();
          break;
        case 'job_id':
          aVal = a.job_id || '';
          bVal = b.job_id || '';
          break;
        case 'domain_status':
          aVal = getDisplayStatus(a.domain_status, a.thread_message_count).label;
          bVal = getDisplayStatus(b.domain_status, b.thread_message_count).label;
          break;
      }
      const cmp = aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
      return sortDir === 'asc' ? cmp : -cmp;
    });

    return result;
  }, [records, effectiveSearch, statusFilter, completenessFilter, sortField, sortDir]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const paginated = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);
  const showStart = (safePage - 1) * PAGE_SIZE + 1;
  const showEnd = Math.min(safePage * PAGE_SIZE, filtered.length);

  const hasFilters = effectiveSearch !== '' || statusFilter !== 'all' || completenessFilter !== 'all';

  const clearFilters = useCallback(() => {
    setSearchQuery('');
    setStatusFilter('all');
    setCompletenessFilter('all');
    setPage(1);
  }, []);

  const handleSort = useCallback((field: SortField) => {
    if (field === sortField) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
    setPage(1);
  }, [sortField]);

  const sortIcon = (field: SortField) => {
    if (field !== sortField) return '';
    return sortDir === 'asc' ? ' ↑' : ' ↓';
  };

  const statusOptions = useMemo(() => {
    const labels = new Set<string>();
    records.forEach(r => {
      labels.add(getDisplayStatus(r.domain_status, r.thread_message_count).label);
    });
    return Array.from(labels).sort();
  }, [records]);

  return (
    <div className="view-enter records-view" data-layer="Work Queue / Frame">
      {/* Toolbar */}
      <div className="records-toolbar" role="toolbar" aria-label="Record filters" data-layer="Work Queue / Filters">
        <div className="records-toolbar-left">
          <div className="records-search-wrap">
            <span className="records-search-icon"><IconSearch size={14} /></span>
            <input
              type="search"
              className="records-search"
              placeholder="Filter queue by name, Job ID, customer…"
              value={searchQuery}
              onChange={e => { setSearchQuery(e.target.value); setPage(1); }}
              aria-label="Filter records"
            />
          </div>

          <select
            className="records-select"
            value={statusFilter}
            onChange={e => { setStatusFilter(e.target.value); setPage(1); }}
            aria-label="Filter by status"
          >
            <option value="all">All Statuses</option>
            {statusOptions.map(s => <option key={s} value={s}>{s}</option>)}
          </select>

          <select
            className="records-select"
            value={completenessFilter}
            onChange={e => { setCompletenessFilter(e.target.value as 'all' | 'complete' | 'incomplete'); setPage(1); }}
            aria-label="Filter by completeness"
          >
            <option value="all">All Records</option>
            <option value="complete">Complete</option>
            <option value="incomplete">Incomplete</option>
          </select>

          {hasFilters && (
            <button className="btn btn-ghost btn-sm" onClick={clearFilters}>
              ✕ Clear filters
            </button>
          )}
        </div>

        <div className="records-toolbar-right">
          <span className="records-count">
            {filtered.length === 0 ? 'No records' : `Showing ${showStart}–${showEnd} of ${filtered.length}`}
          </span>
        </div>
      </div>

      {/* Table */}
      {filtered.length === 0 ? (
        <EmptyState
          icon="⌕"
          title="No matching records"
          message={hasFilters ? 'Try adjusting your filters or search query.' : 'No records found.'}
        />
      ) : (
        <>
          <div className="records-table-wrap" role="region" aria-label="Records table" data-layer="Work Queue / Conversation Table">
            <table className="records-table">
              <thead>
                <tr>
                  <th className="col-status">
                    <button className="th-sort" onClick={() => handleSort('domain_status')}>
                      Status{sortIcon('domain_status')}
                    </button>
                  </th>
                  <th className="col-candidate">
                    <button className="th-sort" onClick={() => handleSort('candidate_name')}>
                      Candidate{sortIcon('candidate_name')}
                    </button>
                  </th>
                  <th className="col-requirement">Requirement</th>
                  <th className="col-customer hide-narrow">
                    <button className="th-sort" onClick={() => handleSort('customer')}>
                      Customer{sortIcon('customer')}
                    </button>
                  </th>
                  <th className="col-jobid hide-narrow">
                    <button className="th-sort" onClick={() => handleSort('job_id')}>
                      Job ID{sortIcon('job_id')}
                    </button>
                  </th>
                  <th className="col-location hide-tablet">Location</th>
                  <th className="col-updated">
                    <button className="th-sort" onClick={() => handleSort('latest_logical_timestamp')}>
                      Last Update{sortIcon('latest_logical_timestamp')}
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody>
                {paginated.map(r => (
                  <tr
                    key={r.id}
                    className={`records-row ${selectedRecordId === r.id ? 'records-row-selected' : ''}`}
                    data-record-id={r.id}
                    onClick={() => onRecordClick(r.id)}
                    onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onRecordClick(r.id); } }}
                    tabIndex={0}
                    role="row"
                    aria-label={`Record: ${r.candidate_name || 'Unknown'}`}
                  >
                    <td className="col-status">
                      <StatusPill domainStatus={r.domain_status} threadMessageCount={r.thread_message_count} size="sm" />
                    </td>
                    <td className="col-candidate cell-primary" title={r.candidate_name || undefined}>{r.candidate_name || '—'}</td>
                    <td className="col-requirement cell-secondary" title={r.skill || undefined}>{r.skill || '—'}</td>
                    <td className="col-customer cell-secondary hide-narrow" title={r.customer || undefined}>{r.customer || '—'}</td>
                    <td className="col-jobid cell-mono hide-narrow">
                      {r.job_id || '—'}
                      {r.source_content_warning && (
                        <span className="cell-warning-icon" title="Source content conflict — Job IDs differ between subject and body">
                          <IconWarning size={13} />
                        </span>
                      )}
                    </td>
                    <td className="col-location cell-secondary hide-tablet" title={r.location || undefined}>{r.location || '—'}</td>
                    <td className="col-updated cell-dim" title={formatExactET(r.latest_logical_timestamp || r.received_at)}>{formatTimestamp(r.latest_logical_timestamp || r.received_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <nav className="records-pagination" aria-label="Pagination">
            <button
              className="btn btn-ghost btn-sm"
              disabled={safePage <= 1}
              onClick={() => setPage(p => Math.max(1, p - 1))}
              aria-label="Previous page"
            >
              ← Previous
            </button>
            <span className="pagination-info">
              Page {safePage} of {totalPages}
            </span>
            <button
              className="btn btn-ghost btn-sm"
              disabled={safePage >= totalPages}
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              aria-label="Next page"
            >
              Next →
            </button>
          </nav>
        </>
      )}
    </div>
  );
}
