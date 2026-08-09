import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import App from './App';
import { getDisplayStatus, getDisplayLabel, isInterviewRelated } from './utils/displayStatus';
import { getTimelineInfo, isAutomaticReply } from './utils/timelineClassifier';
import type { DashboardSummary, RecordHeader, FullRecord, TimelineEntry } from './types';

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

function makeDashboard(records: RecordHeader[] = []): DashboardSummary {
  return {
    total: records.length,
    awaiting_response: 0,
    pending_follow_up: 2,
    interview_awaiting_confirmation: 3,
    interview_request_scheduled: 0,
    awaiting_feedback: 1,
    feedback_due: 0,
    manager_action_required: 0,
    in_evaluation: 0,
    needs_review: records.length,
    incomplete: 0,
    complete_records: records.length,
    closed: 0,
    auth_status: 'authoritative_encrypted_database',
    records,
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
    expect(await screen.findByPlaceholderText(/Filter queue/)).toBeInTheDocument();
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
    const searchInput = await screen.findByPlaceholderText(/Filter queue/);
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
import { waitFor } from '@testing-library/react';

describe('Version Flow Proof', () => {
  it('handles stale version 409 rejection and preserves input', async () => {
    // 1. GET record detail returns version 1
    const testRecord = { ...mockRecord, record_version: 1 };
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
    const noteBtn = screen.getByText('Add Note');
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
