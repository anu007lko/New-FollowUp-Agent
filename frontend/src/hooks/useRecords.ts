import { useState, useEffect, useCallback } from 'react';
import type { DashboardSummary, FullRecord } from '../types';

const API = 'http://127.0.0.1:8000/api/v1';

export interface MailboxReviewResult {
  status: 'completed' | 'already_running' | 'error' | string;
  submissions_imported: number;
  conversations_reviewed: number;
  conversations_updated?: number;
  conversation_refresh_errors?: number;
}

export function useRecords() {
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [selectedRecord, setSelectedRecord] = useState<FullRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [recordLoading, setRecordLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mailboxRefreshing, setMailboxRefreshing] = useState(false);
  const [mailboxRefreshMessage, setMailboxRefreshMessage] = useState<string | null>(null);
  const [mailboxRefreshError, setMailboxRefreshError] = useState<string | null>(null);

  const fetchDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/dashboard`);
      if (!res.ok) throw new Error('Unable to load data from local database');
      const data: DashboardSummary = await res.json();
      if (data.auth_status === 'synthetic_test_data') {
        throw new Error('Synthetic data detected — authoritative database required');
      }
      setDashboard(data);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Connection error';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  const openRecord = useCallback(async (id: string) => {
    setRecordLoading(true);
    try {
      const res = await fetch(`${API}/records/${id}`);
      if (!res.ok) throw new Error('Unable to load record');
      const data: FullRecord = await res.json();
      setSelectedRecord(data);
      return data;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to load record';
      setError(msg);
      return undefined;
    } finally {
      setRecordLoading(false);
    }
  }, []);

  const closeRecord = useCallback(() => {
    setSelectedRecord(null);
  }, []);

  const runMailboxReview = useCallback(async () => {
    if (mailboxRefreshing) return;
    setMailboxRefreshing(true);
    setMailboxRefreshMessage('Reviewing Outlook mailbox…');
    setMailboxRefreshError(null);
    try {
      const tokenResponse = await fetch(`${API}/session/csrf-token`, { method: 'POST' });
      if (!tokenResponse.ok) throw new Error('Unable to start secure mailbox review');
      const { csrf_token: csrfToken } = await tokenResponse.json();

      const reviewResponse = await fetch(`${API}/daily-review/run`, {
        method: 'POST',
        headers: { 'x-csrf-token': csrfToken },
      });
      const result = await reviewResponse.json().catch(() => ({})) as Partial<MailboxReviewResult> & { detail?: string };
      if (!reviewResponse.ok) {
        throw new Error(result.detail || 'Mailbox review failed');
      }
      if (result.status === 'error') {
        throw new Error('Mailbox review could not access Outlook. Your existing data was not changed.');
      }
      if (result.status === 'already_running') {
        setMailboxRefreshMessage('A mailbox review is already running. Reloading the latest local data…');
      } else {
        const updated = result.conversations_updated ?? 0;
        const imported = result.submissions_imported ?? 0;
        const errors = result.conversation_refresh_errors ?? 0;
        setMailboxRefreshMessage(
          errors > 0
            ? `Mailbox reviewed with ${errors} conversation refresh warning${errors === 1 ? '' : 's'}.`
            : `Mailbox updated · ${imported} new · ${updated} conversation${updated === 1 ? '' : 's'} changed`
        );
      }

      await fetchDashboard();
      if (selectedRecord?.id) await openRecord(selectedRecord.id);
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'Mailbox review failed';
      setMailboxRefreshError(message);
      setMailboxRefreshMessage(null);
    } finally {
      setMailboxRefreshing(false);
    }
  }, [fetchDashboard, mailboxRefreshing, openRecord, selectedRecord?.id]);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  return {
    dashboard,
    selectedRecord,
    loading,
    recordLoading,
    error,
    mailboxRefreshing,
    mailboxRefreshMessage,
    mailboxRefreshError,
    fetchDashboard,
    runMailboxReview,
    openRecord,
    closeRecord,
  };
}
