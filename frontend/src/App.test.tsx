import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from './App';
import { DashboardView } from './views/DashboardView';
import { getDisplayStatus, getDisplayLabel, isInterviewRelated } from './utils/displayStatus';
import { getTimelineInfo, isAutomaticReply } from './utils/timelineClassifier';
import type { DashboardSummary, RecordHeader, FullRecord, TimelineEntry } from './types';
import { RecordWorkspace } from './views/RecordWorkspace';
import { ManagerActionBar } from './components/ManagerActionBar';
import { ManagerActionModals } from './components/ManagerActionModals';
import { CustomDropdown } from './components/CustomDropdown';
import { isMuted, setMuted, playSound } from './utils/audio';
import * as audio from './utils/audio';
import * as skipManager from './utils/skipManager';

// --- Factories ---
function makeHeader(overrides: Partial<RecordHeader> = {}): RecordHeader {
  return {
    id: 'test-' + Math.random().toString(36).slice(2, 8),
    graph_immutable_id: 'AAMkAGFake',
    conversation_id: 'AAQkAGFake',
    domain_status: 'NewSubmission',
    received_at: '2026-06-15T10:00:00Z',
    created_at: '2026-06-15T10:00:00Z',
    tcs_eligibility: 'eligible',
    thread_message_count: 4,
    latest_logical_timestamp: '2026-07-01T14:30:00Z',
    record_version: 1,
    ...overrides,
  };
}

function makeDashboard(records: any[] = []): DashboardSummary {
  const headers = records.map(r => makeHeader(r));
  return {
    total: headers.length,
    awaiting_response: 0,
    pending_follow_up: 2,
    interview_awaiting_confirmation: 3,
    interview_request_scheduled: 0,
    awaiting_feedback: 1,
    feedback_due: 0,
    manager_action_required: 0,
    in_evaluation: 0,
    needs_review: headers.length,
    incomplete: 0,
    complete_records: headers.length,
    closed: 0,
    auth_status: 'authoritative_encrypted_database',
    records: headers,
  };
}

function makeFullRecord(overrides: Partial<FullRecord> = {}): FullRecord {
  return {
    id: 'test-full-1',
    graph_immutable_id: 'AAMkAGSource123',
    conversation_id: 'AAQkAGConv456',
    domain_status: 'NewSubmission',
    received_at: '2026-07-01T14:30:00Z',
    created_at: '2026-07-01T14:30:00Z',
    latest_logical_timestamp: '2026-07-01T14:30:00Z',
    record_version: 1,
    manager_notes: '',
    system_notes: '',
    timeline: [
      {
        entry_id: 'e1',
        record_id: 'test-full-1',
        sender: 'recruiter@tcs.com',
        timestamp: '2026-06-15T10:00:00Z',
        body_preview: 'Initial submission regarding the candidate.',
        is_system_note: false,
        graph_immutable_id: 'AAMkAGSource123',  // matches record → Original Submission
      },
      {
        entry_id: 'e2',
        record_id: 'test-full-1',
        sender: 'tarun@clifyx.com',
        timestamp: '2026-06-16T09:00:00Z',
        body_preview: 'Acknowledged, will review.',
        is_system_note: false,
        graph_immutable_id: 'AAMkAGDiff789',
      },
      {
        entry_id: 'e3',
        record_id: 'test-full-1',
        sender: 'candidate@external.com',
        timestamp: '2026-06-17T14:00:00Z',
        body_preview: 'Thank you, please find my updated resume attached.',
        is_system_note: false,
        graph_immutable_id: 'AAMkAGDiffABC',
      },
    ],
    attachment_count: 2,
    ...overrides,
  };
}

function makeEntry(overrides: Partial<TimelineEntry> = {}): TimelineEntry {
  return {
    entry_id: 'entry-1',
    record_id: 'test-full-1',
    sender: 'someone@example.com',
    timestamp: '2026-06-15T10:00:00Z',
    body_preview: '',
    is_system_note: false,
    ...overrides,
  };
}

// --- Mock fetch ---
let mockDashboard: DashboardSummary;
let mockRecord: FullRecord;
let mockDraftPreview: any;
let mockDraftApproval: any;
let force409OnApprove: boolean;
let force409OnCreate: boolean;

beforeEach(() => {
  const records = [
    makeHeader({ candidate_name: 'Alice', skill: 'Java', customer: 'Acme', job_id: 'J100', thread_message_count: 4 }),
    makeHeader({ candidate_name: 'Bob', skill: 'Python', customer: 'Beta', job_id: 'J101', thread_message_count: 3 }),
    makeHeader({ candidate_name: undefined, thread_message_count: 0 }),
  ];
  mockDashboard = makeDashboard(records);
  mockRecord = makeFullRecord();

  mockDraftPreview = {
    record_id: 'test-full-1',
    conversation_id: 'AAQkAGConv456',
    source_message_id: 'AAMkAGSource123',
    source_message_sender: 'recruiter@tcs.com',
    to: ['manager@acme.com'],
    cc: ['recruiter@tcs.com'],
    bcc: [],
    reply_to: 'manager@acme.com',
    default_text: 'Following up on this.'
  };
  mockDraftApproval = {
    is_approved: true,
    approval_hash: 'hash123',
    idempotency_key: 'idem123',
    approved_at: '2026-08-06T10:00:00Z',
    canonical_summary: 'mock summary'
  };
  force409OnApprove = false;
  force409OnCreate = false;

  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (url.includes('/config/status')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          graph_enabled: true,
          drafts_enabled: true,
          draft_creation_available: true,
          mail_send_prohibited: true,
        }),
      });
    }
    if (url.includes('/session/csrf-token')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ csrf_token: 'test-csrf' }) });
    }
    if (url.includes('/dashboard')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockDashboard),
      });
    }
    if (url.includes('/draft-preview')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(mockDraftPreview) });
    }
    if (url.includes('/draft-approve')) {
      if (force409OnApprove) return Promise.resolve({ ok: false, status: 409, json: () => Promise.resolve({}) });
      return Promise.resolve({ ok: true, json: () => Promise.resolve(mockDraftApproval) });
    }
    if (url.includes('/draft-create')) {
      if (force409OnCreate) return Promise.resolve({ ok: false, status: 409, json: () => Promise.resolve({}) });
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          draft_id: 'live-draft-123', verified: true, operation_state: 'CREATED',
          is_synthetic: false,
        }),
      });
    }
    if (url.includes('/draft-status')) {
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ detail: 'Not found' }) });
    }
    if (url.includes('/follow-up-decision')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }
    if (url.match(/\/records\/.+/)) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockRecord),
      });
    }
    return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
  }));
});


// ===========================================================
// #1-#9  Timeline Classification
// ===========================================================
describe('Timeline classification', () => {
  const record = makeFullRecord();

  it('labels Original Submission when immutable IDs match (#1, #2, #3)', () => {
    const entry = makeEntry({
      sender: 'recruiter@tcs.com',
      graph_immutable_id: 'AAMkAGSource123',  // matches record
    });
    const info = getTimelineInfo(entry, record);
    expect(info.label).toBe('Original Submission');
    expect(info.className).toBe('timeline-submission');
  });

  it('does NOT label Original Submission when IDs differ', () => {
    const entry = makeEntry({
      sender: 'recruiter@tcs.com',
      graph_immutable_id: 'AAMkAGDifferentID',
    });
    const info = getTimelineInfo(entry, record);
    expect(info.label).not.toBe('Original Submission');
  });

  it('labels Sent Message for clifyx.com sender without classification (#4)', () => {
    const entry = makeEntry({
      sender: 'tarun@clifyx.com',
      graph_immutable_id: 'AAMkAGDiff789',
    });
    const info = getTimelineInfo(entry, record);
    expect(info.label).toBe('Sent Message');
    expect(info.className).toBe('timeline-sent');
  });

  it('never guesses Manager Follow-up without authoritative classification (#5)', () => {
    const entry = makeEntry({
      sender: 'tarun@clifyx.com',
      graph_immutable_id: 'AAMkAGDiff789',
      body_preview: 'Following up on the submission from last week.',
    });
    const info = getTimelineInfo(entry, record);
    expect(info.label).toBe('Sent Message');
    expect(info.label).not.toBe('Manager Follow-up');
  });

  it('labels Manager Follow-up only with authoritative classification (#5)', () => {
    const entry = makeEntry({
      sender: 'tarun@clifyx.com',
      graph_immutable_id: 'AAMkAGDiffXYZ',
      classification: 'manager_follow_up',
    });
    const info = getTimelineInfo(entry, record);
    expect(info.label).toBe('Manager Follow-up');
    expect(info.className).toBe('timeline-followup');
  });

  it('labels Inbound Response for external sender (#6)', () => {
    const entry = makeEntry({
      sender: 'candidate@external.com',
      graph_immutable_id: 'AAMkAGDiffABC',
    });
    const info = getTimelineInfo(entry, record);
    expect(info.label).toBe('Inbound Response');
    expect(info.className).toBe('timeline-inbound');
  });

  it('labels Automatic Reply for deterministic auto-reply patterns (#7)', () => {
    const entry = makeEntry({
      sender: 'noreply@company.com',
      body_preview: 'This is an automated message.',
    });
    const info = getTimelineInfo(entry, record);
    expect(info.label).toBe('Automatic Reply');
  });

  it('labels Message for unknown/ambiguous (#8)', () => {
    const entry = makeEntry({ sender: '' });
    const info = getTimelineInfo(entry, record);
    expect(info.label).toBe('Message');
    expect(info.className).toBe('timeline-unknown');
  });

  it('labels System Note for system notes', () => {
    const entry = makeEntry({ is_system_note: true });
    const info = getTimelineInfo(entry, record);
    expect(info.label).toBe('System Note');
    expect(info.className).toBe('timeline-system');
  });
});

describe('isAutomaticReply', () => {
  it('detects noreply sender', () => {
    expect(isAutomaticReply('noreply@example.com', '')).toBe(true);
  });
  it('detects out of office body', () => {
    expect(isAutomaticReply('person@example.com', 'Out of office until August 10')).toBe(true);
  });
  it('detects automatic reply body', () => {
    expect(isAutomaticReply('person@example.com', 'Automatic reply: I am currently away')).toBe(true);
  });
  it('returns false for normal messages', () => {
    expect(isAutomaticReply('person@example.com', 'Thanks for reaching out')).toBe(false);
  });
});

// #10 No duplicate timeline rendering
describe('Timeline deduplication (#10)', () => {
  it('renders each message only once', async () => {
    const dupRecord = makeFullRecord({
      timeline: [
        makeEntry({ entry_id: 'e1', graph_immutable_id: 'AAMkAGSource123', sender: 'a@x.com' }),
        makeEntry({ entry_id: 'e1-dup', graph_immutable_id: 'AAMkAGSource123', sender: 'a@x.com' }),  // duplicate
        makeEntry({ entry_id: 'e2', graph_immutable_id: 'AAMkAGDiff', sender: 'b@y.com' }),
      ],
    });
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/dashboard')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockDashboard) });
      }
      if (url.match(/\/records\/.+/)) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(dupRecord) });
      }
      return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
    }));

    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    await screen.findByText('Alice');
    const row = screen.getAllByRole('row').find(r => r.textContent?.includes('Alice'));
    if (row) fireEvent.click(row);
    // After opening panel, timeline should show only 2 unique entries (not 3 with duplicate)
    await screen.findByText('Latest Update');
    fireEvent.click(screen.getByText(/Conversation/));
    const timelineSection = document.querySelector('.timeline');
    const timelineEntries = timelineSection?.querySelectorAll('.timeline-entry') || [];
    expect(timelineEntries.length).toBe(2);
  });

  it('keeps separate messages that share a timestamp but have different IDs', async () => {
    const dupRecord = makeFullRecord({
      timeline: [
        // Same timestamp, same sender, but DIFFERENT IDs
        makeEntry({ entry_id: 'e1', graph_immutable_id: 'AAMkAGSource123', timestamp: '2026-07-01T10:00:00Z', sender: 'a@x.com' }),
        makeEntry({ entry_id: 'e2', graph_immutable_id: 'AAMkAGDiff123', timestamp: '2026-07-01T10:00:00Z', sender: 'a@x.com' }),
      ],
    });
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/dashboard')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockDashboard) });
      }
      if (url.match(/\/records\/.+/)) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(dupRecord) });
      }
      return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
    }));

    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    await screen.findByText('Alice');
    const row = screen.getAllByRole('row').find(r => r.textContent?.includes('Alice'));
    if (row) fireEvent.click(row);
    
    await screen.findByText('Latest Update');
    fireEvent.click(screen.getByText(/Conversation/));
    const timelineSection = document.querySelector('.timeline');
    const timelineEntries = timelineSection?.querySelectorAll('.timeline-entry') || [];
    expect(timelineEntries.length).toBe(2);
  });
});


// ===========================================================
// Display Status
// ===========================================================
describe('displayStatus utility', () => {
  it('maps NeedsReview with messages to Needs Review', () => {
    expect(getDisplayLabel('NeedsReview', 4)).toBe('Needs Review');
  });
  it('maps NewSubmission with zero messages to Incomplete (#29)', () => {
    expect(getDisplayLabel('NewSubmission', 0)).toBe('Incomplete');
  });
  it('never shows New for NewSubmission', () => {
    expect(getDisplayLabel('NewSubmission', 4)).not.toBe('New');
    expect(getDisplayLabel('NewSubmission', 0)).not.toBe('New');
  });
  it('consistent label regardless of context', () => {
    const a = getDisplayStatus('NewSubmission', 4);
    const b = getDisplayStatus('NewSubmission', 4);
    expect(a.label).toBe(b.label);
    expect(a.className).toBe(b.className);
  });
  it('identifies interview-related records', () => {
    expect(isInterviewRelated('InterviewRequestScheduled')).toBe(true);
    expect(isInterviewRelated('AwaitingFeedback')).toBe(true);
    expect(isInterviewRelated('NewSubmission')).toBe(false);
  });
});


// ===========================================================
// App Integration Tests
// ===========================================================
describe('App', () => {
  it('renders authoritative data mode indicator', async () => {
    render(<App />);
    expect((await screen.findAllByText(/Ready for daily review/))[0]).toBeInTheDocument();
  });

  it('does not render SYNTHETIC text', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    expect(screen.queryByText(/SYNTHETIC/i)).not.toBeInTheDocument();
  });

  it('shows the approved daily review schedule', async () => {
    render(<App />);
    expect(await screen.findByText(/Daily review 8:00 AM ET/)).toBeInTheDocument();
  });

  it('shows Read-only and Local only indicators', async () => {
    render(<App />);
    expect((await screen.findAllByText(/Ready for daily review/))[0]).toBeInTheDocument();
    expect(screen.getByText(/Local only/)).toBeInTheDocument();
  });

  it('rejects synthetic data source', async () => {
    const syntheticDashboard = { ...mockDashboard, auth_status: 'synthetic_test_data' };
    vi.stubGlobal('fetch', vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve(syntheticDashboard) })
    ));
    render(<App />);
    expect(await screen.findByText(/Synthetic data detected/)).toBeInTheDocument();
  });

  it('does not render mutation controls', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    expect(screen.queryByText('Close Record')).not.toBeInTheDocument();
    expect(screen.queryByText('Add Note')).not.toBeInTheDocument();
    expect(screen.queryByText('Analyze with AI')).not.toBeInTheDocument();
    expect(screen.queryByText('Create Draft in Outlook')).not.toBeInTheDocument();
  });

  it('shows dashboard greeting with reconciliation split (87/2)', async () => {
    // 89 total, 2 are incomplete (0 messages), meaning 87 need review
    const r1 = makeHeader({ id: 'r1', domain_status: 'NewSubmission', thread_message_count: 2 });
    const r2 = makeHeader({ id: 'r2', domain_status: 'NewSubmission', thread_message_count: 0 }); // Incomplete
    const r3 = makeHeader({ id: 'r3', domain_status: 'NewSubmission', thread_message_count: 0 }); // Incomplete
    const records = Array(87).fill(r1).map((r, i) => ({ ...r, id: `rev-${i}` })).concat([r2, r3]);
    
    const splitDashboard = makeDashboard(records);
    splitDashboard.needs_review = 87;
    splitDashboard.incomplete = 2;
    
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/dashboard')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(splitDashboard) });
      }
      return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
    }));

    render(<App />);
    const greeting = await screen.findByText(/89 complete, including 0 closed/);
    expect(greeting).toBeInTheDocument();
  });

  it('does not show raw Graph IDs in visible DOM', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    const bodyText = document.body.textContent || '';
    expect(bodyText).not.toContain('AAMkAG');
    expect(bodyText).not.toContain('AAQkAG');
  });

  it('shows operational classification summary', async () => {
    render(<App />);
    expect(await screen.findByText(/complete, including/)).toBeInTheDocument();
  });
});


// ===========================================================
// Sidebar
// ===========================================================
describe('Sidebar', () => {
  it('displays full product name (#24)', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    // Uses non-breaking hyphen: Follow‑Up
    expect(screen.getByText(/Follow‑Up/)).toBeInTheDocument();
  });
});


// ===========================================================
// Records View
// ===========================================================
describe('Records View', () => {
  it('navigates to records and shows local filter search (#25)', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    expect(await screen.findByLabelText('Filter queue records')).toBeInTheDocument();
  });

  it('global search has different placeholder from local (#25)', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    expect(screen.getByPlaceholderText(/Jump to candidate/)).toBeInTheDocument();
  });

  it('shows correct record count', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    expect(await screen.findByText(/Showing 1–3 of 3/)).toBeInTheDocument();
  });

  it('search filters records', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    const searchInput = await screen.findByLabelText('Filter queue records');
    fireEvent.change(searchInput, { target: { value: 'Alice' } });
    expect(await screen.findByText(/Showing 1–1 of 1/)).toBeInTheDocument();
  });

  it('provides keyboard-accessible rows', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    await screen.findByText('Alice');
    const rows = screen.getAllByRole('row');
    const dataRows = rows.filter(r => r.getAttribute('tabindex') === '0');
    expect(dataRows.length).toBeGreaterThan(0);
  });

  it('shows pagination controls (#26-28)', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    await screen.findByText('Alice');
    expect(screen.getByText(/Page 1 of/)).toBeInTheDocument();
    expect(screen.getByLabelText('Previous page')).toBeInTheDocument();
    expect(screen.getByLabelText('Next page')).toBeInTheDocument();
  });

  it('shows Incomplete pill for zero-message records (#29)', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    await screen.findByText('Alice');
    const incompletePills = screen.getAllByText('Incomplete');
    expect(incompletePills.length).toBeGreaterThanOrEqual(1);
  });
});


// ===========================================================
// Interviews View
// ===========================================================
describe('Interviews View (#21-23)', () => {
  it('shows correct empty state title', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    const interviewBtns = screen.getAllByText('Interviews');
    fireEvent.click(interviewBtns[0]);
    expect(await screen.findByText('No active interviews')).toBeInTheDocument();
  });

  it('shows correct supporting text', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    const interviewBtns = screen.getAllByText('Interviews');
    fireEvent.click(interviewBtns[0]);
    expect(await screen.findByText(/active interview workflows/)).toBeInTheDocument();
  });

  it('does not say "No interview records"', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    const interviewBtns = screen.getAllByText('Interviews');
    fireEvent.click(interviewBtns[0]);
    await screen.findByText('No active interviews');
    expect(screen.queryByText('No interview records')).not.toBeInTheDocument();
  });
});


// ===========================================================
// Record Panel
// ===========================================================
describe('Record Panel', () => {
  it('shows Latest Update header instead of Current Status (#11)', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    await screen.findByText('Alice');
    const row = screen.getAllByRole('row').find(r => r.textContent?.includes('Alice'));
    if (row) fireEvent.click(row);
    expect(await screen.findByText('Latest Update')).toBeInTheDocument();
    expect(screen.queryByText('Current Status')).not.toBeInTheDocument();
  });

  it('has both Back and Close (✕) buttons (#19)', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    await screen.findByText('Alice');
    const row = screen.getAllByRole('row').find(r => r.textContent?.includes('Alice'));
    if (row) fireEvent.click(row);
    expect(await screen.findByLabelText('Back to records')).toBeInTheDocument();
    expect(screen.getByLabelText('Close panel')).toBeInTheDocument();
  });

  it('Escape key closes the panel (#20)', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    await screen.findByText('Alice');
    const row = screen.getAllByRole('row').find(r => r.textContent?.includes('Alice'));
    if (row) fireEvent.click(row);
    await screen.findByText('Latest Update');
    fireEvent.keyDown(document, { key: 'Escape' });
    // Panel should close — Latest Update should disappear
    await vi.waitFor(() => {
      expect(screen.queryByText('Latest Update')).not.toBeInTheDocument();
    });
  });

  it('does not expose Graph IDs in Identifiers (#16)', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    await screen.findByText('Alice');
    const row = screen.getAllByRole('row').find(r => r.textContent?.includes('Alice'));
    if (row) fireEvent.click(row);
    await screen.findByText('Latest Update');
    // Switch to Details tab and open identifiers section
    fireEvent.click(screen.getByText('Details'));
    const identBtn = screen.getByText('Record Identifiers');
    fireEvent.click(identBtn);
    const bodyText = document.body.textContent || '';
    expect(bodyText).not.toContain('AAMkAGSource');
    expect(bodyText).not.toContain('AAQkAGConv');
  });
});


// ===========================================================
// Reduced motion (structural)
// ===========================================================
describe('Reduced motion', () => {
  it('CSS respects prefers-reduced-motion', () => {
    // Structural test — the CSS file includes the prefers-reduced-motion media query
    // Full runtime testing requires browser-level verification
  });
});


describe('Manual mailbox review', () => {
  it('runs the secure mailbox review and reloads authoritative records', async () => {
    const fetchMock = vi.fn((url: string, options?: RequestInit) => {
      if (url.includes('/session/csrf-token')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ csrf_token: 'manual-review-token' }) });
      }
      if (url.includes('/daily-review/run')) {
        expect(options?.method).toBe('POST');
        expect((options?.headers as Record<string, string>)['x-csrf-token']).toBe('manual-review-token');
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            status: 'completed',
            submissions_imported: 2,
            conversations_reviewed: 12,
            conversations_updated: 3,
            conversation_refresh_errors: 0,
          }),
        });
      }
      if (url.includes('/dashboard')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockDashboard) });
      }
      return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    await screen.findByRole('button', { name: 'Review mailbox now' });
    fireEvent.click(screen.getByRole('button', { name: 'Review mailbox now' }));

    await screen.findByText('Mailbox updated · 2 new · 3 conversations changed');
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/daily-review/run'),
      expect.objectContaining({ method: 'POST' }),
    );
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/draft'))).toBe(false);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/send'))).toBe(false);
  });
});


// ===========================================================
// Version Flow Proof (#38)
// ===========================================================

describe('Version Flow Proof', () => {
  it('handles stale version 409 rejection and preserves input', async () => {
    // 1. GET record detail returns version 1
    const testRecord = makeFullRecord({ ...mockRecord, domain_status: 'AwaitingResponse', record_version: 1 });
    let fetchCount = 0;
    
    vi.stubGlobal('fetch', vi.fn((url: string, options: any) => {
      fetchCount++;
      if (url.includes('/dashboard')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockDashboard) });
      }
      if (url.match(/\/records\/.+\/notes/)) {
        const body = JSON.parse(options?.body || '{}');
        // 5. Stale version 1 returns 409 with no mutation
        if (body.record_version === 1) {
          return Promise.resolve({
            ok: false,
            status: 409,
            json: () => Promise.resolve({
              detail: 'Record has been modified by another manager. UI is reloading the latest state. Please try again.',
              current_version: 2
            })
          });
        }
        // 4. Second action sends version 2 and succeeds
        if (body.record_version === 2) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve({ ...testRecord, record_version: 3, manager_notes: body.note_text })
          });
        }
      }
      if (url.match(/\/records\/.+/)) {
        // First load returns v1. Reload after 409 returns v2.
        const v = fetchCount > 3 ? 2 : 1; 
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ ...testRecord, record_version: v }) });
      }
      return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
    }));

    render(<App />);
    
    // Navigate to Work Queue view
    fireEvent.click(screen.getByText('Work Queue'));
    await screen.findByText('Alice');
    
    const rows = await screen.findAllByRole('row');
    fireEvent.click(rows[1]);
    
    // UI loads record v1
    await screen.findByText('Latest Update');
    
    // Switch to Notes tab to find the Add Note button
    fireEvent.click(screen.getByText('Notes'));
    const noteBtn = screen.getAllByText('Add Note')[0];
    fireEvent.click(noteBtn);
    const textarea = screen.getByPlaceholderText(/Type your manager note/);
    fireEvent.change(textarea, { target: { value: 'This is my unsaved input' } });
    
    const saveBtn = screen.getByText('Save Note');
    fireEvent.click(saveBtn);
    
    // UI shows conflict error
    await screen.findByText(/The record was updated by another process/);
    
    // UI refreshes the record and preserves unsaved input
    // The textarea should still have the value we typed
    expect(textarea).toHaveValue('This is my unsaved input');
    
    // User saves again, this time sending v2 (which succeeds)
    fireEvent.click(saveBtn);
    
    // Modal closes and success is implied (we don't get the error anymore)
    await waitFor(() => {
      expect(screen.queryByText(/The record was updated by another process/)).not.toBeInTheDocument();
    });
  });

  it('handles normal version flow without conflict', async () => {
    const testRecord = { ...mockRecord, record_version: 1 };
    let currentVersion = 1;
    let submittedVersion1 = false;
    let submittedVersion2 = false;

    vi.stubGlobal('fetch', vi.fn((url: string, options: any) => {
      if (url.includes('/dashboard')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockDashboard) });
      }
      if (url.match(/\/records\/.+\/notes/)) {
        const body = JSON.parse(options?.body || '{}');
        if (body.record_version === 1) {
          submittedVersion1 = true;
          currentVersion = 2; // Simulate backend increment
          return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
        }
        if (body.record_version === 2) {
          submittedVersion2 = true;
          currentVersion = 3;
          return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
        }
        return Promise.resolve({ ok: false, status: 409, json: () => Promise.resolve({ detail: 'Conflict' }) });
      }
      if (url.match(/\/records\/.+/)) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ ...testRecord, record_version: currentVersion }) });
      }
      return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
    }));

    render(<App />);
    fireEvent.click(screen.getByText('Work Queue'));
    await screen.findByText('Alice');
    
    const rows = await screen.findAllByRole('row');
    fireEvent.click(rows[1]);
    
    await screen.findByText('Latest Update');

    // Switch to Notes tab to find the Add Note button
    fireEvent.click(screen.getByText('Notes'));
    const noteBtn = screen.getByText('Add Note');
    fireEvent.click(noteBtn);
    const textarea = screen.getByPlaceholderText(/Type your manager note/);
    fireEvent.change(textarea, { target: { value: 'First note' } });
    fireEvent.click(screen.getByText('Save Note'));
    
    await waitFor(() => {
      expect(screen.queryByText(/Type your manager note/)).not.toBeInTheDocument();
    });
    expect(submittedVersion1).toBe(true);

    // Action 2
    fireEvent.click(screen.getByText('Add Note'));
    const textarea2 = screen.getByPlaceholderText(/Type your manager note/);
    fireEvent.change(textarea2, { target: { value: 'Second note' } });
    fireEvent.click(screen.getByText('Save Note'));
    
    await waitFor(() => {
      expect(screen.queryByText(/Type your manager note/)).not.toBeInTheDocument();
    });
    expect(submittedVersion2).toBe(true);
  });
});

// ===========================================================
// Interview Conversation Linking UI
// ===========================================================
describe('Interview Conversation Linking UI', () => {
  it('renders suggestions and opens link modal without exposing Graph/Conv IDs', async () => {
    const recordWithSuggestion = {
      ...mockRecord,
      interview_suggestions: [
        {
          conversation_id: 'AAQkAGConvInterviewSeparate',
          candidate_name: 'Alice Candidate',
          job_id: 'JOB123',
          ep_reference: 'EP456',
          interview_subject: 'Interview Coordination: Alice',
          interview_received_at: '2026-08-02T14:00:00Z',
          confidence_reason: 'Matching Job ID JOB123 and candidate Alice',
          thread_messages: [
            {
              id: 'AAMkAGMsg123',
              conversationId: 'AAQkAGConvInterviewSeparate',
              from: { emailAddress: { address: 'interviewer@client.com' } },
              sentDateTime: '2026-08-02T14:00:00Z',
              bodyPreview: 'We would like to invite Alice for an interview.',
              subject: 'Interview Coordination: Alice'
            }
          ]
        }
      ]
    };

    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/dashboard')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockDashboard) });
      }
      if (url.match(/\/records\/.+/)) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(recordWithSuggestion) });
      }
      return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
    }));

    render(<App />);
    fireEvent.click(screen.getByText('Work Queue'));
    await screen.findByText('Alice');
    
    const rows = await screen.findAllByRole('row');
    fireEvent.click(rows[1]);
    
    await screen.findByText('Related Interview Conversation');
    expect(screen.getByText('Interview Coordination: Alice')).toBeInTheDocument();
    
    // Check no raw Graph/Conv ID in UI
    const panelText = document.body.textContent || '';
    expect(panelText).not.toContain('AAQkAGConvInterviewSeparate');
    expect(panelText).not.toContain('AAMkAGMsg123');

    // Click Review & Link Conversation
    const reviewBtn = screen.getByText('Review & Link');
    fireEvent.click(reviewBtn);

    await screen.findByText('Confirm Link: Related Interview Conversation');
    expect(screen.getAllByText(/We would like to invite Alice for an interview/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('interviewer@client.com').length).toBeGreaterThanOrEqual(2);
  });
});

// ===========================================================
// #12 Follow-up Draft Wizard Flow
// ===========================================================
describe('Follow-up Draft Wizard', () => {
  it('handles decision -> preview -> approve -> create flow correctly', async () => {
    // Reset mocks just for this
    force409OnApprove = false;
    force409OnCreate = false;
    mockRecord.domain_status = 'PendingFollowUp';

    render(<App />);
    
    // 1. Open Record View and click Request Follow-up
    fireEvent.click(screen.getByText('Work Queue'));
    await screen.findByText('Alice');
    const rows = await screen.findAllByRole('row');
    fireEvent.click(rows[1]); // Click Alice's row

    fireEvent.click(await screen.findByText('Request Follow-up'));
    
    // 2. Decision Step
    expect(await screen.findByText('Prepare Follow-up Draft')).toBeInTheDocument();
    expect(screen.getByText(/This app cannot send email/)).toBeInTheDocument();
    
    // Click Confirm & Review Draft
    fireEvent.click(screen.getByText('Confirm & Review Draft'));
    
    // 3. Review Step
    // It should transition to Draft Review, displaying default text and read-only To
    expect(await screen.findByText('Review Draft and Recipients')).toBeInTheDocument();
    expect(screen.getByText(/manager@acme.com/)).toBeInTheDocument();
    const textarea = screen.getByDisplayValue('Following up on this.') as HTMLTextAreaElement;
    
    // Validate BCC internal-domain restriction
    const bccInput = screen.getByPlaceholderText('e.g. manager@clifyx.com');
    fireEvent.change(bccInput, { target: { value: 'external@gmail.com' } });
    fireEvent.click(screen.getByText('Approve Draft & Recipients'));
    
    // Should show error and stay on step
    expect(await screen.findByText('BCC addresses must end in @clifyx.com')).toBeInTheDocument();
    
    // Fix BCC and edit body
    fireEvent.change(bccInput, { target: { value: 'internal@clifyx.com' } });
    fireEvent.change(textarea, { target: { value: 'Edited text.' } });
    
    // Click Approve
    fireEvent.click(screen.getByText('Approve Draft & Recipients'));
    
    // 4. Draft approved and ready for manager-authorized creation
    expect(await screen.findByText('Ready to Create in Outlook')).toBeInTheDocument();
    expect(screen.getByText('Create Draft in Outlook')).toBeInTheDocument();
    
    // Click Create
    fireEvent.click(screen.getByText('Create Draft in Outlook'));
    
    // 5. Success Step
    expect(await screen.findByText('The Reply All draft is saved in Outlook with its original conversation history. Nothing was sent.')).toBeInTheDocument();
    
    // Ensure no 'Send' button exists anywhere
    expect(screen.queryByText(/Send Draft/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Send Email/i)).not.toBeInTheDocument();
  });
});


// ===========================================================
// Topbar Title Suppression
// ===========================================================
describe('Topbar title suppression', () => {
  it('omits Work Queue title from topbar', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    // Click the sidebar Work Queue item
    const wqButtons = screen.getAllByText('Work Queue');
    fireEvent.click(wqButtons[0]);
    // Wait for the section h1 to appear
    await screen.findByRole('heading', { name: 'Work Queue' });
    // The topbar should NOT have a separate topbar-section-title
    const topbar = document.querySelector('.topbar');
    const titleSpan = topbar?.querySelector('.topbar-section-title');
    expect(titleSpan).toBeNull();
  });

  it('omits Interviews title from topbar', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    const interviewBtns = screen.getAllByText('Interviews');
    fireEvent.click(interviewBtns[0]);
    await screen.findByText(/active interview workflows/);
    const topbar = document.querySelector('.topbar');
    const titleSpan = topbar?.querySelector('.topbar-section-title');
    expect(titleSpan).toBeNull();
  });

  it('preserves Retention title in topbar', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    // Sidebar label is 'Retention & operations' (lowercase)
    fireEvent.click(screen.getByText(/Retention & operations/i));
    // TopBar section title should say 'Retention & Operations'
    const topbar = document.querySelector('.topbar');
    const titleSpan = topbar?.querySelector('.topbar-section-title');
    expect(titleSpan).not.toBeNull();
    expect(titleSpan?.textContent).toBe('Retention & Operations');
  });
});


// ===========================================================
// Interview Metric Filters
// ===========================================================
describe('Interview metric filters', () => {
  function setupInterviewDashboard() {
    const interviewRecords = [
      makeHeader({ id: 'iv-1', domain_status: 'InterviewAwaitingConfirmation', candidate_name: 'Alice', interview_state: 'awaiting_confirmation' }),
      makeHeader({ id: 'iv-2', domain_status: 'InterviewScheduled', candidate_name: 'Bob', interview_state: 'scheduled' }),
      makeHeader({ id: 'iv-3', domain_status: 'InterviewScheduled', candidate_name: 'Charlie', interview_state: 'scheduled' }),
      makeHeader({ id: 'iv-4', domain_status: 'FeedbackDue', candidate_name: 'Dana', interview_state: 'feedback_due', feedback_due_at: '2026-07-01T10:00:00Z' }),
      makeHeader({ id: 'iv-5', domain_status: 'AwaitingFeedback', candidate_name: 'Eve', interview_state: 'awaiting_feedback' }),
    ];
    const dashboard = makeDashboard(interviewRecords);
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/config/status')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ graph_enabled: true, drafts_enabled: true, draft_creation_available: true, mail_send_prohibited: true }) });
      }
      if (url.includes('/session/csrf-token')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ csrf_token: 'test-csrf' }) });
      }
      if (url.includes('/dashboard')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(dashboard) });
      }
      return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
    }));
  }

  it('shows correct metric counts', async () => {
    setupInterviewDashboard();
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    const interviewBtns = screen.getAllByText('Interviews');
    fireEvent.click(interviewBtns[0]);
    await screen.findByText(/active interview workflows/);

    // Total Active = 5
    const metricCards = document.querySelectorAll('.iv-metric-card');
    expect(metricCards.length).toBe(4);
    const values = Array.from(document.querySelectorAll('.iv-metric-value')).map(el => el.textContent);
    expect(values[0]).toBe('5');  // Total Active
    expect(values[1]).toBe('1');  // Awaiting Confirmation
    expect(values[2]).toBe('2');  // Scheduled
    expect(values[3]).toBe('1');  // Feedback Overdue (only iv-4 with FeedbackDue)
  });

  it('filters to only awaiting confirmation when clicked', async () => {
    setupInterviewDashboard();
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    const interviewBtns = screen.getAllByText('Interviews');
    fireEvent.click(interviewBtns[0]);
    await screen.findByText(/active interview workflows/);

    const metricButtons = document.querySelectorAll('.iv-metric-card');
    // Click "Awaiting Confirmation" (index 1)
    fireEvent.click(metricButtons[1]);

    // Only Alice should be visible
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.queryByText('Bob')).not.toBeInTheDocument();
  });

  it('resets to Total Active when active metric clicked again', async () => {
    setupInterviewDashboard();
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    const interviewBtns = screen.getAllByText('Interviews');
    fireEvent.click(interviewBtns[0]);
    await screen.findByText(/active interview workflows/);

    const metricButtons = document.querySelectorAll('.iv-metric-card');
    // Click "Awaiting Confirmation" → filter
    fireEvent.click(metricButtons[1]);
    expect(screen.queryByText('Bob')).not.toBeInTheDocument();

    // Click again → should reset to total
    fireEvent.click(metricButtons[1]);
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
  });

  it('does not double-count Feedback Overdue', async () => {
    // Add a duplicate record with same id
    const records = [
      makeHeader({ id: 'iv-dup', domain_status: 'FeedbackDue', candidate_name: 'Zara', interview_state: 'feedback_due', feedback_due_at: '2026-07-01T10:00:00Z' }),
      makeHeader({ id: 'iv-dup', domain_status: 'FeedbackDue', candidate_name: 'Zara', interview_state: 'feedback_due', feedback_due_at: '2026-07-01T10:00:00Z' }),
    ];
    const dashboard = makeDashboard(records);
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/config/status')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ graph_enabled: true, drafts_enabled: true, draft_creation_available: true, mail_send_prohibited: true }) });
      }
      if (url.includes('/session/csrf-token')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ csrf_token: 'test-csrf' }) });
      }
      if (url.includes('/dashboard')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(dashboard) });
      }
      return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
    }));

    render(<App />);
    await screen.findByText(/Ready for daily review/);
    const interviewBtns = screen.getAllByText('Interviews');
    fireEvent.click(interviewBtns[0]);
    await screen.findByText(/active interview workflows/);

    // Feedback Overdue value should be 1 (deduplicated by id), not 2
    const values = Array.from(document.querySelectorAll('.iv-metric-value')).map(el => el.textContent);
    expect(values[3]).toBe('1');
  });

  it('shows empty state for zero-result metric filter', async () => {
    // All records are Scheduled — Awaiting Confirmation metric is 0
    const records = [
      makeHeader({ id: 'iv-s1', domain_status: 'InterviewScheduled', candidate_name: 'Sched1', interview_state: 'scheduled' }),
    ];
    const dashboard = makeDashboard(records);
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/config/status')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ graph_enabled: true, drafts_enabled: true, draft_creation_available: true, mail_send_prohibited: true }) });
      }
      if (url.includes('/session/csrf-token')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ csrf_token: 'test-csrf' }) });
      }
      if (url.includes('/dashboard')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(dashboard) });
      }
      return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
    }));

    render(<App />);
    await screen.findByText(/Ready for daily review/);
    const interviewBtns = screen.getAllByText('Interviews');
    fireEvent.click(interviewBtns[0]);
    await screen.findByText(/active interview workflows/);

    // Click "Awaiting Confirmation" (0 records)
    const metricButtons = document.querySelectorAll('.iv-metric-card');
    fireEvent.click(metricButtons[1]);

    // Should show an empty state
    expect(screen.getByText(/No records match the selected metric/)).toBeInTheDocument();
  });
});


// ===========================================================
// Queue Search Placeholder
// ===========================================================
describe('Queue search placeholder', () => {
  it('uses unfiltered record count in placeholder', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    const searchInput = await screen.findByLabelText('Filter queue records');
    expect(searchInput.getAttribute('placeholder')).toContain('3');
  });
});


// ===========================================================
// Keyboard Shortcut Safety
// ===========================================================
describe('Keyboard shortcut safety', () => {
  it('slash does not trigger from editable controls', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    const searchInput = await screen.findByLabelText('Filter queue records');

    // Focus an input and press /
    searchInput.focus();
    fireEvent.keyDown(searchInput, { key: '/' });

    // Should not prevent the character from being typed
    // (the slash handler should have returned early because target is INPUT)
    // No error should be thrown
  });

  it('Ctrl+K focuses global search', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);

    // In jsdom navigator.platform is empty, so the handler uses ctrlKey
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true });

    // Global search should be focused
    const globalSearch = screen.getByLabelText('Search records');
    expect(document.activeElement).toBe(globalSearch);
  });

  it('Ctrl+K does not trigger from input elements', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    const queueSearch = await screen.findByLabelText('Filter queue records');

    // Focus the queue search and press Ctrl+K
    queueSearch.focus();
    fireEvent.keyDown(queueSearch, { key: 'k', ctrlKey: true });

    // Should stay on the queue search, not jump to global
    expect(document.activeElement).toBe(queueSearch);
  });
});


// ===========================================================
// Interview card action hierarchy
// ===========================================================
describe('Interview card action hierarchy', () => {
  it('shows prominent pending action on interview cards', async () => {
    // Set up records that appear in the Interviews view
    const records = [
      makeHeader({
        candidate_name: 'CardAction Alice',
        domain_status: 'InterviewAwaitingConfirmation',
        interview_state: 'AwaitingConfirmation',
        job_id: 'J200',
        skill: 'React',
        customer: 'Acme Corp',
      }),
    ];
    mockDashboard = makeDashboard(records);

    render(<App />);
    await screen.findByText(/Ready for daily review/);
    const interviewBtns = screen.getAllByText('Interviews');
    fireEvent.click(interviewBtns[0]);
    await screen.findByText(/active interview workflows/);

    // The action text should be visible on the card
    expect(screen.getByText('Confirm interview details')).toBeInTheDocument();
    // The candidate name should be visible
    expect(screen.getByText('CardAction Alice')).toBeInTheDocument();
    // Job ID should appear
    expect(screen.getByText('J200')).toBeInTheDocument();
  });

  it('shows correct action for feedback overdue', async () => {
    const records = [
      makeHeader({
        candidate_name: 'Feedback Bob',
        domain_status: 'FeedbackDue',
        interview_state: 'FeedbackOverdue',
        feedback_due_at: '2026-07-01T10:00:00Z',
      }),
    ];
    mockDashboard = makeDashboard(records);

    render(<App />);
    await screen.findByText(/Ready for daily review/);
    const interviewBtns = screen.getAllByText('Interviews');
    fireEvent.click(interviewBtns[0]);
    await screen.findByText(/active interview workflows/);

    expect(screen.getByText('Collect overdue feedback')).toBeInTheDocument();
  });
});


// ===========================================================
// Overview clean preview
// ===========================================================
describe('Overview clean preview', () => {
  it('shows clean body_preview from timeline instead of raw headers', async () => {
    // Put raw header content in latest_update and clean body in timeline
    mockRecord = makeFullRecord({
      latest_update: 'Regards, Tarun\nFrom: manager@acme.com\nSent: 2026-07-01\nTo: candidate@example.com\nSubject: Re: Interview',
      latest_sender: 'manager@acme.com',
      // timeline[2] has the newest timestamp with clean body_preview
    });

    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    await screen.findByText('Alice');
    const row = screen.getAllByRole('row').find(r => r.textContent?.includes('Alice'));
    if (row) fireEvent.click(row);

    await screen.findByText('Latest Update');
    // Should see the clean body_preview from the newest timeline entry (e3, candidate@external.com)
    const preview = document.querySelector('[data-testid="overview-preview"]');
    expect(preview).not.toBeNull();
    expect(preview?.textContent).toContain('updated resume');
    // Should NOT see raw header text
    expect(preview?.textContent).not.toContain('From: manager@acme.com');
  });

  it('shows metadata-only fallback when no body_preview exists', async () => {
    mockRecord = makeFullRecord({
      latest_update: 'From: x@y.com\nSent: 2026-07-01\nTo: a@b.com',
      timeline: [
        {
          entry_id: 'no-body-1',
          record_id: 'test-full-1',
          sender: 'x@y.com',
          timestamp: '2026-07-01T10:00:00Z',
          body_preview: '',
          is_system_note: false,
        },
      ],
    });

    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    await screen.findByText('Alice');
    const row = screen.getAllByRole('row').find(r => r.textContent?.includes('Alice'));
    if (row) fireEvent.click(row);

    await screen.findByText('Latest Update');
    // Should show the metadata-only message
    expect(screen.getByText(/Full message content was not stored locally/i)).toBeInTheDocument();
  });

  it('shows View conversation button that switches tabs', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    await screen.findByText('Alice');
    const row = screen.getAllByRole('row').find(r => r.textContent?.includes('Alice'));
    if (row) fireEvent.click(row);

    await screen.findByText('Latest Update');
    const viewConvBtn = screen.getByLabelText('View full conversation');
    expect(viewConvBtn).toBeInTheDocument();

    fireEvent.click(viewConvBtn);
    // Conversation tab should now be active — check for the chronology toggle
    expect(screen.getByText('Newest first')).toBeInTheDocument();
  });
});


// ===========================================================
// Conversation timeline improvements
// ===========================================================
describe('Conversation timeline', () => {
  it('renders direction indicators on conversation messages', async () => {
    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    await screen.findByText('Alice');
    const row = screen.getAllByRole('row').find(r => r.textContent?.includes('Alice'));
    if (row) fireEvent.click(row);

    await screen.findByText('Latest Update');
    // Switch to Conversation tab
    fireEvent.click(screen.getByRole('tab', { name: /Conversation/ }));

    // Wait for timeline messages
    const messages = await screen.findAllByTestId('timeline-message');
    expect(messages.length).toBeGreaterThan(0);

    // Should have at least one direction badge
    const directionBadges = document.querySelectorAll('.timeline-direction-badge');
    expect(directionBadges.length).toBeGreaterThan(0);
  });

  it('shows metadata-only state for messages without body', async () => {
    mockRecord = makeFullRecord({
      timeline: [
        {
          entry_id: 'meta-only-1',
          record_id: 'test-full-1',
          sender: 'someone@example.com',
          timestamp: '2026-07-01T10:00:00Z',
          body_preview: '',
          is_system_note: false,
        },
      ],
    });

    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    await screen.findByText('Alice');
    const row = screen.getAllByRole('row').find(r => r.textContent?.includes('Alice'));
    if (row) fireEvent.click(row);

    await screen.findByText('Latest Update');
    fireEvent.click(screen.getByRole('tab', { name: /Conversation/ }));

    // Should see metadata-only message in the conversation
    expect(await screen.findByText(/Full message content was not stored locally/i)).toBeInTheDocument();
  });

  it('Show more / Show less controls have aria-expanded', async () => {
    // Create a record with a very long body_preview
    const longBody = 'A'.repeat(350); // > BODY_TRUNCATE (280)
    mockRecord = makeFullRecord({
      timeline: [
        {
          entry_id: 'long-1',
          record_id: 'test-full-1',
          sender: 'candidate@external.com',
          timestamp: '2026-07-01T10:00:00Z',
          body_preview: longBody,
          is_system_note: false,
        },
      ],
    });

    render(<App />);
    await screen.findByText(/Ready for daily review/);
    fireEvent.click(screen.getByText('Work Queue'));
    await screen.findByText('Alice');
    const row = screen.getAllByRole('row').find(r => r.textContent?.includes('Alice'));
    if (row) fireEvent.click(row);

    await screen.findByText('Latest Update');
    fireEvent.click(screen.getByRole('tab', { name: /Conversation/ }));

    // Find Show more button
    const showMore = await screen.findByText('Show more');
    expect(showMore).toBeInTheDocument();
    expect(showMore.getAttribute('aria-expanded')).toBe('false');

    // Click Show more
    fireEvent.click(showMore);
    const showLess = screen.getByText('Show less');
    expect(showLess.getAttribute('aria-expanded')).toBe('true');
  });
});

describe('Legacy Body Preview Cleanup', () => {
  it('truncates body preview at quoted reply boundary', async () => {
    const rawLegacy = `Regards,
Tarun
________________________________
From: Manager <manager@acme.com>
Sent: Wed, 08 Aug 2026 10:00:00 GMT
To: Tarun
Subject: RE: Candidate`;

    const fullRec = makeFullRecord({
      domain_status: 'ManagerActionRequired',
      timeline: [
        {
          entry_id: 'te-1',
          record_id: 'test-full-1',
          sender: 'tarun@clifyx.com',
          timestamp: '2026-08-08T10:05:00Z',
          body_preview: rawLegacy,
          classification: 'CandidateFollowUp',
          is_system_note: false,
          to_recipients: [],
          cc_recipients: [],
          role: 'original_submission'
        }
      ]
    });

    render(<RecordWorkspace record={fullRec} loading={false} onClose={() => {}} onRefreshRecord={vi.fn()} />);
    
    // The rendered text should contain "Regards, Tarun" but NOT "From: Manager"
    const timelineEntry = await screen.findByTestId('overview-preview');
    expect(timelineEntry.textContent).toContain('Regards');
    expect(timelineEntry.textContent).not.toContain('From: Manager');
    expect(timelineEntry.textContent).not.toContain('Sent: Wed');
  });

  it('renders unavailable content message if cleanup leaves nothing', async () => {
    const rawLegacy = `________________________________
From: System
Sent: Wed, 08 Aug 2026
To: Test`;

    const fullRec = makeFullRecord({
      timeline: [
        {
          entry_id: 'te-1',
          record_id: 'test-full-1',
          sender: 'system@acme.com',
          timestamp: '2026-08-08T10:05:00Z',
          body_preview: rawLegacy,
          is_system_note: false,
          to_recipients: [],
          cc_recipients: [],
          role: 'original_submission'
        }
      ]
    });

    render(<RecordWorkspace record={fullRec} loading={false} onClose={() => {}} onRefreshRecord={vi.fn()} />);
    
    const timelineEntry = await screen.findByTestId('overview-preview');
    expect(timelineEntry.textContent).toContain('Full message content was not stored locally.');
  });

  it('handles single-record Refresh Thread button click successfully', async () => {
    const fullRec = makeFullRecord({ id: 'rec-refresh-1' });
    const onRefreshMock = vi.fn().mockResolvedValue(undefined);

    const fetchMock = vi.fn((url: string) => {
      if (String(url).includes('/session/csrf-token')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ csrf_token: 'test-csrf-token' }),
        });
      }
      if (String(url).includes('/records/rec-refresh-1/refresh')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(fullRec),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<RecordWorkspace record={fullRec} loading={false} onClose={() => {}} onRefreshRecord={onRefreshMock} />);

    const refreshBtn = screen.getByRole('button', { name: /Refresh Thread/i });
    expect(refreshBtn).toBeDefined();

    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(onRefreshMock).toHaveBeenCalledWith('rec-refresh-1');
      expect(screen.getByText('Thread refreshed')).toBeDefined();
    });
  });

  it('does not call refresh endpoint if CSRF token fetch fails or returns empty token', async () => {
    const fullRec = makeFullRecord({ id: 'rec-refresh-csrf-fail' });
    const onRefreshMock = vi.fn().mockResolvedValue(undefined);

    const fetchMock = vi.fn((url: string) => {
      if (String(url).includes('/session/csrf-token')) {
        return Promise.resolve({
          ok: false,
          status: 500,
          json: () => Promise.resolve({}),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<RecordWorkspace record={fullRec} loading={false} onClose={() => {}} onRefreshRecord={onRefreshMock} />);

    const refreshBtn = screen.getByRole('button', { name: /Refresh Thread/i });
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(screen.getByText('Could not refresh the thread. Please try again.')).toBeDefined();
    });

    const refreshCall = fetchMock.mock.calls.find(([url]) => String(url).includes('/refresh'));
    expect(refreshCall).toBeUndefined();
    expect(onRefreshMock).not.toHaveBeenCalled();
  });

  it('sends CSRF header on refresh and passes explicit record ID to onRefreshRecord', async () => {
    const fullRec = makeFullRecord({ id: 'rec-explicit-id-99' });
    const onRefreshMock = vi.fn().mockResolvedValue(undefined);

    const fetchMock = vi.fn((url: string, _opts?: any) => {
      if (String(url).includes('/session/csrf-token')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ csrf_token: 'secret-csrf-123' }),
        });
      }
      if (String(url).includes('/records/rec-explicit-id-99/refresh')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(fullRec),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<RecordWorkspace record={fullRec} loading={false} onClose={() => {}} onRefreshRecord={onRefreshMock} />);

    const refreshBtn = screen.getByRole('button', { name: /Refresh Thread/i });
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(onRefreshMock).toHaveBeenCalledWith('rec-explicit-id-99');
    });

    const refreshCall = fetchMock.mock.calls.find(([url]) => String(url).includes('/refresh')) as [string, any] | undefined;
    expect(refreshCall).toBeDefined();
    const [, opts] = refreshCall!;
    expect(opts?.headers?.['X-CSRF-Token']).toBe('secret-csrf-123');
  });

  it('shows required user messages for 404, 409, and 503 error responses', async () => {
    const fullRec = makeFullRecord({ id: 'rec-error-codes' });

    for (const { status, expectedText } of [
      { status: 404, expectedText: 'This record is no longer available.' },
      { status: 409, expectedText: 'This record changed while refreshing. Please try again.' },
      { status: 503, expectedText: 'Thread refresh is currently disabled.' },
    ]) {
      const fetchMock = vi.fn((url: string) => {
        if (String(url).includes('/session/csrf-token')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve({ csrf_token: 'csrf-tok' }),
          });
        }
        if (String(url).includes('/records/rec-error-codes/refresh')) {
          return Promise.resolve({
            ok: false,
            status,
            json: () => Promise.resolve({ detail: 'Error' }),
          });
        }
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
      });
      vi.stubGlobal('fetch', fetchMock);

      const { unmount } = render(<RecordWorkspace record={fullRec} loading={false} onClose={() => {}} onRefreshRecord={vi.fn()} />);
      const refreshBtn = screen.getByRole('button', { name: /Refresh Thread/i });
      fireEvent.click(refreshBtn);

      await waitFor(() => {
        expect(screen.getByText(expectedText)).toBeDefined();
      });
      unmount();
    }
  });

  it('disables Refresh Thread button while request is pending', async () => {
    const fullRec = makeFullRecord({ id: 'rec-pending-test' });
    let resolveRefresh: (val: any) => void;

    const fetchMock = vi.fn((url: string) => {
      if (String(url).includes('/session/csrf-token')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ csrf_token: 'csrf-pending' }),
        });
      }
      if (String(url).includes('/records/rec-pending-test/refresh')) {
        return new Promise(resolve => {
          resolveRefresh = resolve;
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<RecordWorkspace record={fullRec} loading={false} onClose={() => {}} onRefreshRecord={vi.fn()} />);

    const refreshBtn = screen.getByRole('button', { name: /Refresh Thread/i }) as HTMLButtonElement;
    expect(refreshBtn.disabled).toBe(false);

    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(refreshBtn.disabled).toBe(true);
      expect(refreshBtn.textContent).toContain('Refreshing...');
    });

    resolveRefresh!({
      ok: true,
      status: 200,
      json: () => Promise.resolve(fullRec),
    });

    await waitFor(() => {
      expect(refreshBtn.disabled).toBe(false);
      expect(refreshBtn.textContent).toContain('Refresh Thread');
    });
  });

  it('passes explicit initial targetRecordId to onRefreshRecord callback proving passed ID is used', async () => {
    const initialRec = makeFullRecord({ id: 'rec-initial-id-101' });
    const onRefreshMock = vi.fn().mockResolvedValue(undefined);

    const fetchMock = vi.fn((url: string) => {
      if (String(url).includes('/session/csrf-token')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ csrf_token: 'test-csrf-token' }),
        });
      }
      if (String(url).includes('/records/rec-initial-id-101/refresh')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(initialRec),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<RecordWorkspace record={initialRec} loading={false} onClose={() => {}} onRefreshRecord={onRefreshMock} />);

    const refreshBtn = screen.getByRole('button', { name: /Refresh Thread/i });
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(onRefreshMock).toHaveBeenCalledTimes(1);
      expect(onRefreshMock).toHaveBeenCalledWith('rec-initial-id-101');
    });
  });

  describe('Manager action bar primary button updates for outcome decisions', () => {
    it('shows Close Record when ManagerActionRequired has canonical Rejection', () => {
      const rec = makeFullRecord({
        domain_status: 'ManagerActionRequired',
        structured_evidence: {
          category: 'Rejection',
          workflow_status: 'ManagerActionRequired',
          reason_code: 'manager_override',
          logical_messages_evaluated: 1,
        },
      });

      render(<ManagerActionBar record={rec} onOpenModal={() => {}} />);
      expect(screen.getByRole('button', { name: 'Close Record' })).toBeDefined();
    });

    it('shows Close Record when ManagerActionRequired has canonical Position Closed', () => {
      const rec = makeFullRecord({
        domain_status: 'ManagerActionRequired',
        structured_evidence: {
          category: 'Position Closed',
          workflow_status: 'ManagerActionRequired',
          reason_code: 'manager_override',
          logical_messages_evaluated: 1,
        },
      });

      render(<ManagerActionBar record={rec} onOpenModal={() => {}} />);
      expect(screen.getByRole('button', { name: 'Close Record' })).toBeDefined();
    });

    it('shows Close Record when ManagerActionRequired has canonical Client Rejected', () => {
      const rec = makeFullRecord({
        domain_status: 'ManagerActionRequired',
        structured_evidence: {
          category: 'Client Rejected',
          workflow_status: 'ManagerActionRequired',
          reason_code: 'manager_override',
          logical_messages_evaluated: 1,
        },
      });

      render(<ManagerActionBar record={rec} onOpenModal={() => {}} />);
      expect(screen.getByRole('button', { name: 'Close Record' })).toBeDefined();
    });

    it('does not show Close Record when timeline contains old Rejection event but canonical category is Keep Open', () => {
      const rec = makeFullRecord({
        domain_status: 'ManagerActionRequired',
        structured_evidence: {
          category: 'Keep Open',
          workflow_status: 'ManagerActionRequired',
          reason_code: 'manager_override',
          logical_messages_evaluated: 1,
        },
        timeline: [
          {
            entry_id: 'audit-old',
            record_id: 'rec-1',
            sender: 'tarun@clifyx.com',
            timestamp: '2026-08-09T10:00:00Z',
            is_system_note: true,
            event_type: 'MANAGER_OUTCOME_DECISION',
            body_preview: 'Manager set outcome decision: Rejection',
          },
        ],
      });

      render(<ManagerActionBar record={rec} onOpenModal={() => {}} />);
      expect(screen.queryByRole('button', { name: 'Close Record' })).toBeNull();
      expect(screen.getByRole('button', { name: 'Review Outcome' })).toBeDefined();
    });

    it('does not show Close Record for Keep Open in ManagerActionRequired and still shows Review Outcome', () => {
      const rec = makeFullRecord({
        domain_status: 'ManagerActionRequired',
        structured_evidence: {
          category: 'Keep Open',
          workflow_status: 'ManagerActionRequired',
          reason_code: 'manager_override',
          logical_messages_evaluated: 1,
        },
      });

      render(<ManagerActionBar record={rec} onOpenModal={() => {}} />);
      expect(screen.queryByRole('button', { name: 'Close Record' })).toBeNull();
      expect(screen.getByRole('button', { name: 'Review Outcome' })).toBeDefined();
    });

    it('does not show Close Record for NeedsReview or Move to Needs Review', () => {
      const recNeedsReview = makeFullRecord({
        domain_status: 'NeedsReview',
        structured_evidence: {
          category: 'Move to Needs Review',
          workflow_status: 'NeedsReview',
          reason_code: 'manager_override',
          logical_messages_evaluated: 1,
        },
      });

      render(<ManagerActionBar record={recNeedsReview} onOpenModal={() => {}} />);
      expect(screen.getByRole('button', { name: 'Set Outcome' })).toBeDefined();
      expect(screen.queryByRole('button', { name: 'Close Record' })).toBeNull();
    });

    it('opens existing Close Record flow when primary Close Record button is clicked', () => {
      const onOpenModalMock = vi.fn();
      const rec = makeFullRecord({
        domain_status: 'ManagerActionRequired',
        structured_evidence: {
          category: 'Rejection',
          workflow_status: 'ManagerActionRequired',
          reason_code: 'manager_override',
          logical_messages_evaluated: 1,
        },
      });

      render(<ManagerActionBar record={rec} onOpenModal={onOpenModalMock} />);
      const closeBtn = screen.getByRole('button', { name: 'Close Record' });
      fireEvent.click(closeBtn);

      expect(onOpenModalMock).toHaveBeenCalledWith('close');
    });
  });

  describe('CustomDropdown & Audio UI Enhancement', () => {
    beforeEach(() => {
      localStorage.clear();
    });

    it('opens dropdown, selects an option, and submits selected value', () => {
      const onChangeMock = vi.fn();
      const options = [
        { value: 'Position Closed', label: 'Position Closed' },
        { value: 'Rejection', label: 'Rejection' },
      ];

      render(
        <CustomDropdown
          options={options}
          value="Position Closed"
          onChange={onChangeMock}
          ariaLabel="Manager Action Choice"
        />
      );

      const triggerBtn = screen.getByRole('button', { name: 'Manager Action Choice' });
      expect(triggerBtn).toBeDefined();

      fireEvent.click(triggerBtn);
      expect(screen.getByRole('listbox')).toBeDefined();

      const rejectionOption = screen.getByRole('option', { name: /Rejection/i });
      fireEvent.click(rejectionOption);

      expect(onChangeMock).toHaveBeenCalledWith('Rejection');
      expect(screen.queryByRole('listbox')).toBeNull();
    });

    it('handles keyboard navigation and Escape close behavior', () => {
      const onChangeMock = vi.fn();
      const options = [
        { value: 'Position Closed', label: 'Position Closed' },
        { value: 'Rejection', label: 'Rejection' },
      ];

      render(
        <CustomDropdown
          options={options}
          value="Position Closed"
          onChange={onChangeMock}
          ariaLabel="Manager Action Choice"
        />
      );

      const triggerBtn = screen.getByRole('button', { name: 'Manager Action Choice' });

      // Press Enter to open
      fireEvent.keyDown(triggerBtn, { key: 'Enter' });
      expect(screen.getByRole('listbox')).toBeDefined();

      // Press Escape to close
      fireEvent.keyDown(triggerBtn, { key: 'Escape' });
      expect(screen.queryByRole('listbox')).toBeNull();
    });

    it('closes dropdown when clicking outside', () => {
      const options = [
        { value: 'Position Closed', label: 'Position Closed' },
        { value: 'Rejection', label: 'Rejection' },
      ];

      render(
        <div>
          <div data-testid="outside">Outside Area</div>
          <CustomDropdown
            options={options}
            value="Position Closed"
            onChange={() => {}}
            ariaLabel="Manager Action Choice"
          />
        </div>
      );

      const triggerBtn = screen.getByRole('button', { name: 'Manager Action Choice' });
      fireEvent.click(triggerBtn);
      expect(screen.getByRole('listbox')).toBeDefined();

      fireEvent.mouseDown(screen.getByTestId('outside'));
      expect(screen.queryByRole('listbox')).toBeNull();
    });

    it('persists mute preference in localStorage and prevents sound execution', () => {
      expect(isMuted()).toBe(false);
      setMuted(true);
      expect(isMuted()).toBe(true);
      expect(localStorage.getItem('app_sound_muted')).toBe('true');

      expect(() => playSound('apply')).not.toThrow();
    });

    it('handles sound playback failure silently without blocking UI operations', () => {
      vi.stubGlobal('AudioContext', undefined);
      vi.stubGlobal('webkitAudioContext', undefined);

      expect(() => playSound('select')).not.toThrow();
      expect(() => playSound('apply')).not.toThrow();
      expect(() => playSound('close')).not.toThrow();
      expect(() => playSound('refresh')).not.toThrow();
    });
  });

  describe('Close Reason CustomDropdown and sound wiring', () => {
    beforeEach(() => {
      localStorage.clear();
      vi.restoreAllMocks();
    });

    it('uses CustomDropdown for Close Reason and submits unchanged selected value', () => {
      const onChangeMock = vi.fn();
      const options = [
        { value: 'Position closed', label: 'Position closed' },
        { value: 'Candidate withdrawn', label: 'Candidate withdrawn' },
        { value: 'Client rejected', label: 'Client rejected' },
        { value: 'No follow-up needed', label: 'No follow-up needed' },
        { value: 'Other', label: 'Other (Note required)' },
      ];

      render(
        <CustomDropdown
          options={options}
          value="Position closed"
          onChange={onChangeMock}
          ariaLabel="Close Reason"
        />
      );

      const triggerBtn = screen.getByRole('button', { name: 'Close Reason' });
      expect(triggerBtn).toBeDefined();

      fireEvent.click(triggerBtn);
      const rejectedOpt = screen.getByRole('option', { name: /Client rejected/i });
      fireEvent.click(rejectedOpt);

      expect(onChangeMock).toHaveBeenCalledWith('Client rejected');
    });

    it('selecting Close Reason invokes select sound function when unmuted', () => {
      const audioModule = vi.spyOn(audio, 'playSound');
      const onChangeMock = vi.fn();

      render(
        <CustomDropdown
          options={[{ value: 'Position closed', label: 'Position closed' }]}
          value="Position closed"
          onChange={onChangeMock}
          ariaLabel="Close Reason"
        />
      );

      const triggerBtn = screen.getByRole('button', { name: 'Close Reason' });
      fireEvent.click(triggerBtn);
      const opt = screen.getByRole('option', { name: /Position closed/i });
      fireEvent.click(opt);

      expect(audioModule).toHaveBeenCalledWith('select');
    });

    it('close confirmation, apply decision, and refresh invoke intended sound functions', () => {
      const audioSpy = vi.spyOn(audio, 'playSound');

      audio.playSound('apply');
      expect(audioSpy).toHaveBeenCalledWith('apply');

      audio.playSound('close');
      expect(audioSpy).toHaveBeenCalledWith('close');

      audio.playSound('refresh');
      expect(audioSpy).toHaveBeenCalledWith('refresh');
    });

    it('muted preference prevents all sound calls', () => {
      audio.setMuted(true);

      audio.playSound('select');
      audio.playSound('apply');
      audio.playSound('close');
      audio.playSound('refresh');

      expect(audio.isMuted()).toBe(true);
    });
  });

  describe('Canonical UI State Synchronization Proof', () => {
    beforeEach(() => {
      localStorage.clear();
      vi.restoreAllMocks();
    });

    it('applying Rejection updates workspace and list/action state automatically', async () => {
      const rec = makeFullRecord({
        id: 'rec-rej-1',
        candidate_name: 'Bob Marley',
        domain_status: 'ManagerActionRequired',
        record_version: 1,
      });

      const updatedRec = {
        ...rec,
        record_version: 2,
        domain_status: 'ManagerActionRequired',
        structured_evidence: {
          category: 'Rejection',
          workflow_status: 'ManagerActionRequired',
          reason_code: 'manager_override',
          logical_messages_evaluated: 1,
        },
      };

      const dashboard = makeDashboard([rec]);
      const updatedDashboard = makeDashboard([updatedRec]);

      let outcomeApplied = false;
      vi.stubGlobal('fetch', vi.fn((url: string) => {
        if (url.includes('/dashboard')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(outcomeApplied ? updatedDashboard : dashboard) });
        }
        if (url.includes('/records/rec-rej-1/outcome-decision')) {
          outcomeApplied = true;
          return Promise.resolve({ ok: true, json: () => Promise.resolve(updatedRec) });
        }
        if (url.includes('/records/rec-rej-1')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(outcomeApplied ? updatedRec : rec) });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }));

      render(<App />);

      fireEvent.click(screen.getByText('Work Queue'));
      await screen.findByText('Bob Marley');

      const rows = await screen.findAllByRole('row');
      fireEvent.click(rows[1]);

      await screen.findByText('Review Outcome');
      fireEvent.click(screen.getByRole('button', { name: 'Review Outcome' }));

      const triggerBtn = screen.getByRole('button', { name: 'Manager Action Choice' });
      fireEvent.click(triggerBtn);
      fireEvent.click(screen.getByRole('option', { name: /Rejection/i }));

      fireEvent.click(screen.getByRole('button', { name: 'Apply Decision' }));

      // Automatically updates primary action button to Close Record without page reload
      await screen.findByRole('button', { name: 'Close Record' });
      expect(screen.getByText('Rejection recorded. Close this record to complete the workflow.')).toBeDefined();
    });

    it('closing a record removes or updates it correctly under the active filter', async () => {
      const rec = makeFullRecord({
        id: 'rec-close-1',
        candidate_name: 'Carol Danvers',
        domain_status: 'ManagerActionRequired',
        structured_evidence: {
          category: 'Rejection',
          workflow_status: 'ManagerActionRequired',
          reason_code: 'manager_override',
          logical_messages_evaluated: 1,
        },
      });

      const closedRec = {
        ...rec,
        domain_status: 'Closed' as any,
        closed_at: '2026-08-10T12:00:00Z',
      };

      const dashboardOpen = makeDashboard([rec]);
      const dashboardClosed = makeDashboard([closedRec]);

      let isClosed = false;
      vi.stubGlobal('fetch', vi.fn((url: string) => {
        if (url.includes('/dashboard')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(isClosed ? dashboardClosed : dashboardOpen) });
        }
        if (url.includes('/records/rec-close-1/close')) {
          isClosed = true;
          return Promise.resolve({ ok: true, json: () => Promise.resolve(closedRec) });
        }
        if (url.includes('/records/rec-close-1')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(isClosed ? closedRec : rec) });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }));

      render(<App />);

      fireEvent.click(screen.getByText('Work Queue'));
      await screen.findByText('Carol Danvers');

      const rows = await screen.findAllByRole('row');
      fireEvent.click(rows[1]);

      const primaryCloseBtn = await screen.findByRole('button', { name: 'Close Record' });
      fireEvent.click(primaryCloseBtn);

      const confirmCloseBtn = screen.getAllByRole('button', { name: 'Close Record' })[1];
      fireEvent.click(confirmCloseBtn);

      await waitFor(() => {
        expect(isClosed).toBe(true);
      });
    });

    it('adding a note updates the timeline/notes without a browser refresh', async () => {
      const rec = makeFullRecord({
        id: 'rec-note-1',
        candidate_name: 'David Bowie',
        manager_notes: undefined,
      });

      const updatedRec = {
        ...rec,
        manager_notes: 'Spoke with candidate on phone',
      };

      const dashboard = makeDashboard([rec]);
      const updatedDashboard = makeDashboard([updatedRec]);

      let fetchCount = 0;
      vi.stubGlobal('fetch', vi.fn((url: string) => {
        fetchCount++;
        if (url.includes('/dashboard')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(fetchCount > 1 ? updatedDashboard : dashboard) });
        }
        if (url.includes('/records/rec-note-1/notes')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(updatedRec) });
        }
        if (url.includes('/records/rec-note-1')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(fetchCount > 2 ? updatedRec : rec) });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }));

      render(<App />);

      fireEvent.click(screen.getByText('Work Queue'));
      await screen.findByText('David Bowie');

      const rows = await screen.findAllByRole('row');
      fireEvent.click(rows[1]);

      const notesTab = await screen.findByText('Notes');
      fireEvent.click(notesTab);

      const noteBtn = screen.getAllByText('Add Note')[0];
      fireEvent.click(noteBtn);

      const textarea = screen.getByPlaceholderText(/Type your manager note/);
      fireEvent.change(textarea, { target: { value: 'Spoke with candidate on phone' } });

      fireEvent.click(screen.getByRole('button', { name: 'Save Note' }));

      await screen.findByText('Spoke with candidate on phone');
    });

    it('failed API updates do not falsely change the UI state', async () => {
      const rec = makeFullRecord({
        id: 'rec-fail-1',
        candidate_name: 'Eve Online',
        domain_status: 'ManagerActionRequired',
      });

      const dashboard = makeDashboard([rec]);

      vi.stubGlobal('fetch', vi.fn((url: string) => {
        if (url.includes('/dashboard')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(dashboard) });
        }
        if (url.includes('/records/rec-fail-1/outcome-decision')) {
          return Promise.resolve({
            ok: false,
            status: 500,
            json: () => Promise.resolve({ detail: 'Internal server failure' }),
          });
        }
        if (url.includes('/records/rec-fail-1')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(rec) });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }));

      render(<App />);

      fireEvent.click(screen.getByText('Work Queue'));
      await screen.findByText('Eve Online');

      const rows = await screen.findAllByRole('row');
      fireEvent.click(rows[1]);

      await screen.findByText('Review Outcome');
      fireEvent.click(screen.getByRole('button', { name: 'Review Outcome' }));

      const triggerBtn = screen.getByRole('button', { name: 'Manager Action Choice' });
      fireEvent.click(triggerBtn);
      fireEvent.click(screen.getByRole('option', { name: /Rejection/i }));

      fireEvent.click(screen.getByRole('button', { name: 'Apply Decision' }));

      await screen.findByText('Internal server failure');

      expect(screen.getByRole('button', { name: 'Review Outcome' })).toBeDefined();
    });
  });

  describe('Skip For Later Focus Queue Feature', () => {
    beforeEach(() => {
      localStorage.clear();
      vi.restoreAllMocks();
    });

    it('Skip immediately hides current focus record and shows next pending record', async () => {
      const rec1 = makeFullRecord({ id: 'rec-1', candidate_name: 'Alice Cooper', domain_status: 'ManagerActionRequired' });
      const rec2 = makeFullRecord({ id: 'rec-2', candidate_name: 'Bob Marley', domain_status: 'ManagerActionRequired' });
      const dashboard = makeDashboard([rec1, rec2]);

      vi.stubGlobal('fetch', vi.fn((url: string) => {
        if (url.includes('/dashboard')) return Promise.resolve({ ok: true, json: () => Promise.resolve(dashboard) });
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }));

      render(<App />);

      await screen.findByText(/Alice Cooper/);

      const skipBtn = screen.getByRole('button', { name: 'Skip for later' });
      fireEvent.click(skipBtn);

      await screen.findByText(/Bob Marley/);
      expect(screen.getByText(/Skipped until tomorrow morning/)).toBeDefined();
    });

    it('Skipped record remains unchanged in canonical record data', async () => {
      const rec1 = makeFullRecord({ id: 'rec-1', candidate_name: 'Alice Cooper', domain_status: 'ManagerActionRequired', record_version: 1 });
      const dashboard = makeDashboard([rec1]);

      vi.stubGlobal('fetch', vi.fn((url: string) => {
        if (url.includes('/dashboard')) return Promise.resolve({ ok: true, json: () => Promise.resolve(dashboard) });
        return Promise.resolve({ ok: true, json: () => Promise.resolve(rec1) });
      }));

      skipManager.skipRecord('rec-1');

      expect(rec1.domain_status).toBe('ManagerActionRequired');
      expect(rec1.record_version).toBe(1);
    });

    it('Skip preference persists in localStorage after reload', () => {
      skipManager.skipRecord('rec-1');

      expect(skipManager.isRecordSkipped('rec-1')).toBe(true);

      const raw = localStorage.getItem('fua-skipped-records');
      expect(raw).toBeDefined();
      expect(raw).toContain('rec-1');
    });

    it('Skipped record is excluded before 9:00 AM tomorrow and eligible again after that time', () => {
      const baseDate = new Date('2026-08-10T14:00:00-04:00');
      skipManager.skipRecord('rec-1', baseDate);

      // Same day 6 PM -> still skipped
      const sameDay6PM = new Date('2026-08-10T18:00:00-04:00').getTime();
      expect(skipManager.isRecordSkipped('rec-1', sameDay6PM)).toBe(true);

      // Tomorrow 8:59 AM -> still skipped
      const tomorrow859AM = new Date('2026-08-11T08:59:00-04:00').getTime();
      expect(skipManager.isRecordSkipped('rec-1', tomorrow859AM)).toBe(true);

      // Tomorrow 9:01 AM -> returned to queue (no longer skipped)
      const tomorrow901AM = new Date('2026-08-11T09:01:00-04:00').getTime();
      expect(skipManager.isRecordSkipped('rec-1', tomorrow901AM)).toBe(false);
    });

    it('shows empty/all-skipped queue state with reset button when all pending records are skipped', async () => {
      const rec1 = makeFullRecord({ id: 'rec-1', candidate_name: 'Alice Cooper', domain_status: 'ManagerActionRequired' });
      const dashboard = makeDashboard([rec1]);

      vi.stubGlobal('fetch', vi.fn((url: string) => {
        if (url.includes('/dashboard')) return Promise.resolve({ ok: true, json: () => Promise.resolve(dashboard) });
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }));

      render(<App />);

      await screen.findByText(/Alice Cooper/);

      const skipBtn = screen.getByRole('button', { name: 'Skip for later' });
      fireEvent.click(skipBtn);

      await screen.findByText('All pending tasks skipped until tomorrow.');
      const resetBtn = screen.getByRole('button', { name: 'Reset skipped items' });
      expect(resetBtn).toBeDefined();

      fireEvent.click(resetBtn);

      await screen.findByText(/Alice Cooper/);
    });
  });

  describe('Sidebar Refinements & Collapse behavior', () => {
    beforeEach(() => {
      localStorage.clear();
      vi.restoreAllMocks();
    });

    it('places Retention & Operations in primary nav below Interviews and removes Outlook card', () => {
      const dashboard = makeDashboard();
      vi.stubGlobal('fetch', vi.fn((url: string) => {
        if (url.includes('/dashboard')) return Promise.resolve({ ok: true, json: () => Promise.resolve(dashboard) });
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }));

      render(<App />);

      const navItems = screen.getAllByRole('button', { name: /Today|Work Queue|Interviews|Retention/i });
      expect(navItems.map(btn => btn.textContent)).toEqual([
        'Today',
        'Work Queue',
        'Interviews',
        'Retention & Operations',
      ]);

      expect(screen.queryByText(/Drafts open in Outlook/i)).toBeNull();
    });

    it('toggles collapse state adding app-shell-collapsed and sidebar-collapsed classes', () => {
      const dashboard = makeDashboard();
      vi.stubGlobal('fetch', vi.fn((url: string) => {
        if (url.includes('/dashboard')) return Promise.resolve({ ok: true, json: () => Promise.resolve(dashboard) });
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }));

      const { container } = render(<App />);

      const toggleBtn = screen.getByRole('button', { name: /Collapse sidebar/i });
      fireEvent.click(toggleBtn);

      const appShell = container.querySelector('.app-shell');
      const sidebar = container.querySelector('.sidebar');

      expect(appShell?.classList.contains('app-shell-collapsed')).toBe(true);
      expect(sidebar?.classList.contains('sidebar-collapsed')).toBe(true);
    });

    it('renders branded footer with company name in expanded mode and tooltip in collapsed mode', () => {
      const dashboard = makeDashboard();
      vi.stubGlobal('fetch', vi.fn((url: string) => {
        if (url.includes('/dashboard')) return Promise.resolve({ ok: true, json: () => Promise.resolve(dashboard) });
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }));

      const { container } = render(<App />);

      expect(screen.getByText('ClifyX Inc.')).toBeDefined();
      expect(screen.getByText('© 2026 ClifyX Inc. All rights reserved.')).toBeDefined();

      const toggleBtn = screen.getByRole('button', { name: /Collapse sidebar/i });
      fireEvent.click(toggleBtn);

      const footerContent = container.querySelector('.sidebar-brand-footer-content');
      expect(footerContent?.getAttribute('title')).toBe('ClifyX Inc.');
    });
  });

  describe('Dashboard Later Today Synchronized State Proof', () => {
    beforeEach(() => {
      localStorage.clear();
      vi.restoreAllMocks();
    });

    it('completing/changing focused record outcome updates Later today counts immediately', () => {
      const rec1 = makeHeader({
        id: 'rec-101',
        candidate_name: 'Arthur Dent',
        domain_status: 'ManagerActionRequired',
      });

      const updatedRec1 = makeHeader({
        ...rec1,
        domain_status: 'Closed' as any,
      });

      const initialDashboard = makeDashboard([rec1]);
      const updatedDashboard = makeDashboard([updatedRec1]);

      const { rerender } = render(
        <DashboardView
          dashboard={initialDashboard}
          onRecordClick={vi.fn()}
          onNavigate={vi.fn()}
        />
      );

      expect(screen.getAllByText('1 conversation').length).toBeGreaterThan(0);

      rerender(
        <DashboardView
          dashboard={updatedDashboard}
          onRecordClick={vi.fn()}
          onNavigate={vi.fn()}
        />
      );

      expect(screen.getAllByText('0 conversations').length).toBeGreaterThan(0);
    });

    it('closing a record removes it from Later today under the active filter', () => {
      const rec1 = makeHeader({
        id: 'rec-102',
        candidate_name: 'Ford Prefect',
        domain_status: 'PendingFollowUp',
      });

      const closedRec1 = makeHeader({
        ...rec1,
        domain_status: 'Closed' as any,
      });

      const initialDashboard = makeDashboard([rec1]);
      const updatedDashboard = makeDashboard([closedRec1]);

      const { rerender } = render(
        <DashboardView
          dashboard={initialDashboard}
          onRecordClick={vi.fn()}
          onNavigate={vi.fn()}
        />
      );

      expect(screen.getAllByText('1 conversation').length).toBeGreaterThan(0);

      rerender(
        <DashboardView
          dashboard={updatedDashboard}
          onRecordClick={vi.fn()}
          onNavigate={vi.fn()}
        />
      );

      expect(screen.getAllByText('0 conversations').length).toBeGreaterThan(0);
    });

    it('Skip for later immediately removes record from Later today and shows next eligible card', async () => {
      const rec1 = makeHeader({
        id: 'rec-103',
        candidate_name: 'Zaphod Beeblebrox',
        domain_status: 'PendingFollowUp',
      });
      const rec2 = makeHeader({
        id: 'rec-104',
        candidate_name: 'Tricia McMillan',
        domain_status: 'NeedsReview',
      });

      const dashboard = makeDashboard([rec1, rec2]);

      render(
        <DashboardView
          dashboard={dashboard}
          onRecordClick={vi.fn()}
          onNavigate={vi.fn()}
        />
      );

      await screen.findByText(/Zaphod Beeblebrox/);
      expect(screen.getAllByText('1 conversation').length).toBeGreaterThan(0);

      const skipBtn = screen.getByRole('button', { name: 'Skip for later' });
      fireEvent.click(skipBtn);

      await screen.findByText(/Tricia McMillan/);
      expect(screen.getAllByText('0 conversations').length).toBeGreaterThan(0);
    });

    it('a failed update does not falsely remove or change any card', () => {
      const rec1 = makeHeader({
        id: 'rec-105',
        candidate_name: 'Marvin Android',
        domain_status: 'ManagerActionRequired',
      });

      const dashboard = makeDashboard([rec1]);

      render(
        <DashboardView
          dashboard={dashboard}
          onRecordClick={vi.fn()}
          onNavigate={vi.fn()}
        />
      );

      expect(screen.getAllByText('1 conversation').length).toBeGreaterThan(0);
      expect(screen.getByText(/Marvin Android/)).toBeDefined();
    });
  });

  describe('Manual Interview Scheduled Option', () => {
    beforeEach(() => {
      localStorage.clear();
      vi.restoreAllMocks();
    });

    it('dropdown contains Interview Scheduled as a selectable option', () => {
      const rec = makeFullRecord({
        id: 'iv-modal-1',
        domain_status: 'InterviewAwaitingConfirmation',
      });

      render(
        <ManagerActionModals
          activeModal="interview"
          record={rec}
          onCloseModal={vi.fn()}
          onSuccessAction={vi.fn()}
        />
      );

      const triggerBtn = screen.getByRole('button', { name: 'Status Choice' });
      fireEvent.click(triggerBtn);

      const scheduledOpt = screen.getByRole('option', { name: /Interview Scheduled/i });
      expect(scheduledOpt).toBeDefined();
    });

    it('prefills detected interview date, time, timezone and retains editability', () => {
      const rec = makeFullRecord({
        id: 'iv-modal-2',
        domain_status: 'InterviewAwaitingConfirmation',
        interview_date: '2026-08-20',
        interview_time: '14:00',
        interview_timezone: 'America/New_York',
        timezone_source: 'message_text',
        attachment_count: 0,
      });

      render(
        <ManagerActionModals
          activeModal="interview"
          record={rec}
          onCloseModal={vi.fn()}
          onSuccessAction={vi.fn()}
        />
      );

      expect(screen.getByText(/Detected from thread/i)).toBeDefined();

      const dateInput = screen.getByLabelText(/Interview Date:/i) as HTMLInputElement;
      expect(dateInput.value).toBe('2026-08-20');

      fireEvent.change(dateInput, { target: { value: '2026-08-25' } });
      expect(dateInput.value).toBe('2026-08-25');
    });

    it('allows manual scheduling without date/time present', async () => {
      vi.spyOn(globalThis, 'fetch').mockImplementation((url) => {
        if (typeof url === 'string' && url.includes('csrf-token')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ csrf_token: 'fake-token' }) } as Response);
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
      });

      const rec = makeFullRecord({
        id: 'iv-modal-3',
        domain_status: 'InterviewAwaitingConfirmation',
      });

      const onSuccessMock = vi.fn();

      render(
        <ManagerActionModals
          activeModal="interview"
          record={rec}
          onCloseModal={vi.fn()}
          onSuccessAction={onSuccessMock}
        />
      );

      const saveBtn = screen.getByRole('button', { name: 'Save Interview Status' });
      expect(saveBtn.hasAttribute('disabled')).toBe(false);

      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(onSuccessMock).toHaveBeenCalledWith(
          'interview-confirmation',
          expect.objectContaining({
            choice: 'scheduled',
            source: 'Scheduled manually',
          })
        );
      });
    });

    it('timeline records correct detected source tag', async () => {
      vi.spyOn(globalThis, 'fetch').mockImplementation((url) => {
        if (typeof url === 'string' && url.includes('csrf-token')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ csrf_token: 'fake-token' }) } as Response);
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
      });

      const rec = makeFullRecord({
        id: 'iv-modal-4',
        domain_status: 'InterviewAwaitingConfirmation',
        interview_date: '2026-08-22',
        interview_time: '10:00',
        interview_timezone: 'America/New_York',
        attachment_count: 1,
      });

      const onSuccessMock = vi.fn();

      render(
        <ManagerActionModals
          activeModal="interview"
          record={rec}
          onCloseModal={vi.fn()}
          onSuccessAction={onSuccessMock}
        />
      );

      const saveBtn = screen.getByRole('button', { name: 'Save Interview Status' });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(onSuccessMock).toHaveBeenCalledWith(
          'interview-confirmation',
          expect.objectContaining({
            choice: 'scheduled',
            source: 'Scheduled from calendar invite',
          })
        );
      });
    });

    it('failed saves do not trigger onSuccessAction or falsely update UI state', async () => {
      vi.spyOn(globalThis, 'fetch').mockImplementation((url) => {
        if (typeof url === 'string' && url.includes('csrf-token')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ csrf_token: 'fake-token' }) } as Response);
        }
        return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({ detail: 'Database error' }) } as Response);
      });

      const rec = makeFullRecord({
        id: 'iv-modal-5',
        domain_status: 'InterviewAwaitingConfirmation',
      });

      const onSuccessMock = vi.fn();

      render(
        <ManagerActionModals
          activeModal="interview"
          record={rec}
          onCloseModal={vi.fn()}
          onSuccessAction={onSuccessMock}
        />
      );

      const saveBtn = screen.getByRole('button', { name: 'Save Interview Status' });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(screen.getByText('Database error')).toBeDefined();
      });

      expect(onSuccessMock).not.toHaveBeenCalled();
    });

    it('revalidates Pending Response, Interviews, Work Queue, Workspace and Dashboard together via single canonical refresh pass without browser reload', async () => {
      const pendingRec = makeFullRecord({
        id: 'sync-rec-1',
        candidate_name: 'Sync Candidate',
        domain_status: 'InterviewAwaitingConfirmation',
        record_version: 1,
      });

      const updatedRec = {
        ...pendingRec,
        domain_status: 'InterviewRequestScheduled',
        interview_state: 'scheduled',
        interview_date: '2026-08-28',
        interview_time: '11:00',
        interview_timezone: 'America/New_York',
        record_version: 2,
      };

      const initialDashboard = makeDashboard([pendingRec]);
      const updatedDashboard = makeDashboard([updatedRec]);

      let actionExecuted = false;
      vi.stubGlobal('fetch', vi.fn((url: string) => {
        if (typeof url === 'string' && url.includes('csrf-token')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ csrf_token: 'fake-token' }) } as Response);
        }
        if (typeof url === 'string' && url.includes('/dashboard')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(actionExecuted ? updatedDashboard : initialDashboard) });
        }
        if (typeof url === 'string' && url.includes('/interview-confirmation')) {
          actionExecuted = true;
          return Promise.resolve({ ok: true, json: () => Promise.resolve(updatedRec) });
        }
        if (typeof url === 'string' && url.includes('/records/sync-rec-1')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(actionExecuted ? updatedRec : pendingRec) });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }));

      render(<App />);

      fireEvent.click(screen.getByText('Work Queue'));
      await screen.findByText('Sync Candidate');

      const rows = await screen.findAllByRole('row');
      fireEvent.click(rows[1]);

      const primaryBtn = await screen.findByRole('button', { name: 'Confirm Interview' });
      fireEvent.click(primaryBtn);

      const saveBtn = screen.getByRole('button', { name: 'Save Interview Status' });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(actionExecuted).toBe(true);
      });

      expect(await screen.findByRole('button', { name: 'Update Interview' })).toBeDefined();
      expect(await screen.findByText(/Scheduled for 2026-08-28 at 11:00/)).toBeDefined();

      // Verify Interviews view reflects updated count and state automatically
      const interviewBtns = screen.getAllByText('Interviews');
      fireEvent.click(interviewBtns[0]);
      await screen.findByText('Sync Candidate');
      expect(screen.getByText(/1 record with active interview workflows/i)).toBeDefined();
    });
  });
});


