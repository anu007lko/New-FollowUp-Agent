import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { DashboardView } from '../views/DashboardView';
import { RecordsView } from '../views/RecordsView';
import { ManagerActionBar } from './ManagerActionBar';
import { ManagerActionModals } from './ManagerActionModals';
import type { FullRecord, DashboardData } from '../types';

const sampleRecordWithActions: FullRecord = {
  id: 'rec-contract-001',
  graph_immutable_id: 'graph-c001',
  conversation_id: 'conv-c001',
  candidate_name: 'Test Candidate',
  job_id: 'JOB-999',
  domain_status: 'NeedsReview',
  received_at: '2026-08-11T10:00:00Z',
  created_at: '2026-08-11T10:00:00Z',
  record_version: 4,
  manager_notes: '',
  system_notes: '',
  attachment_count: 0,
  timeline: [
    { entry_id: 'e1', record_id: 'rec-contract-001', sender: 'test@example.com', timestamp: '2026-08-11T10:00:00Z', body_preview: 'Hello', is_system_note: false }
  ],
  workflow: {
    status: 'NeedsReview',
    evidence_category: 'New Submission',
    queue_membership: ['needs_review'],
    display: { label: 'Needs Review', tone: 'review', description: 'Requires manager review' },
    allowed_actions: [
      {
        action_id: 'REVIEW_OUTCOME',
        label: 'Review Outcome',
        style: 'primary',
        execution_kind: 'workflow_mutation',
        outcome_options: [
          { option_id: 'POSITION_CLOSED', label: 'Position Closed', is_terminal: true, resulting_status: 'Closed', close_reason: 'Position closed', requires_note: false },
          { option_id: 'ON_HOLD', label: 'On Hold', is_terminal: false, resulting_status: 'Tracking', close_reason: null, requires_note: false }
        ]
      },
      {
        action_id: 'CLOSE_RECORD',
        label: 'Close Record',
        style: 'danger',
        execution_kind: 'workflow_mutation',
        requires_confirmation: true,
        confirmation_title: 'Close Record',
        confirmation_message: 'Are you sure?',
        reason_options: ['Position closed', 'Candidate withdrawn', 'Other']
      }
    ]
  } as any
};

const mockDashboardData: DashboardData = {
  awaiting_response: 0,
  pending_follow_up: 1,
  interview_awaiting_confirmation: 0,
  interview_request_scheduled: 0,
  awaiting_feedback: 0,
  feedback_due: 0,
  manager_action_required: 0,
  in_evaluation: 0,
  needs_review: 1,
  incomplete: 0,
  complete_records: 0,
  closed: 0,
  total: 1,
  auth_status: 'ok',
  records: [sampleRecordWithActions]
};

describe('Phase 1 Canonical Workflow Contract Frontend Tests', () => {
  it('Dashboard focus card menu renders only workflow.allowed_actions', () => {
    const handleActionModal = vi.fn();
    render(
      <DashboardView
        dashboard={mockDashboardData}
        onRecordClick={vi.fn()}
        onActionModal={handleActionModal}
        onNavigate={vi.fn()}
      />
    );

    // Open overflow menu
    const menuBtn = screen.getByRole('button', { name: /more actions/i });
    fireEvent.click(menuBtn);

    expect(screen.getByText('Review Outcome')).toBeInTheDocument();
    expect(screen.getByText('Close Record')).toBeInTheDocument();
    // Unlisted hardcoded actions should NOT be rendered
    expect(screen.queryByText('Mark Placed / Joined')).not.toBeInTheDocument();
    expect(screen.queryByText('Mark No Longer Available')).not.toBeInTheDocument();
  });

  it('Records row menu renders only workflow.allowed_actions', () => {
    const handleActionModal = vi.fn();
    render(
      <RecordsView
        records={[sampleRecordWithActions]}
        onRecordClick={vi.fn()}
        onActionModal={handleActionModal}
      />
    );

    const menuBtn = screen.getByRole('button', { name: /more actions/i });
    fireEvent.click(menuBtn);

    expect(screen.getByText('Review Outcome')).toBeInTheDocument();
    expect(screen.getByText('Close Record')).toBeInTheDocument();
    expect(screen.queryByText('Schedule Next Follow-up')).not.toBeInTheDocument();
  });

  it('No menu/action appears when compact workflow data is absent', () => {
    const emptyRecord: FullRecord = {
      ...sampleRecordWithActions,
      workflow: { allowed_actions: [] } as any
    };
    render(
      <ManagerActionBar
        record={emptyRecord}
        onOpenModal={vi.fn()}
      />
    );

    expect(screen.getByText('No actions available')).toBeInTheDocument();
  });

  it('Action trigger passes the latest record_version', () => {
    const handleActionModal = vi.fn();
    render(
      <RecordsView
        records={[sampleRecordWithActions]}
        onRecordClick={vi.fn()}
        onActionModal={handleActionModal}
      />
    );

    const menuBtn = screen.getByRole('button', { name: /more actions/i });
    fireEvent.click(menuBtn);

    const closeBtn = screen.getByText('Close Record');
    fireEvent.click(closeBtn);

    // Expect record_version 4 passed to onActionModal
    expect(handleActionModal).toHaveBeenCalledWith('rec-contract-001', 'CLOSE_RECORD', 4);
  });

  it('Outcome and reason options shown in modals match DTO values', () => {
    render(
      <ManagerActionModals
        activeModal="close"
        record={sampleRecordWithActions}
        onCloseModal={vi.fn()}
        onSuccessAction={vi.fn()}
      />
    );

    expect(screen.getByText('Close Submission Record')).toBeInTheDocument();
    expect(screen.getByText('Position closed')).toBeInTheDocument();
  });
});
