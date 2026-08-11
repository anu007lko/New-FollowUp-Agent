import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ManagerActionBar } from './ManagerActionBar';
import type { FullRecord } from '../types';

const mockRecord: FullRecord = {
  id: 'rec-001',
  graph_immutable_id: 'graph-001',
  conversation_id: 'conv-001',
  job_id: '424631',
  candidate_name: 'Naga Venkata Akhilesh Koorma',
  skill: 'Data Engineer',
  customer: 'FCB',
  location: 'Dallas, TX',
  domain_status: 'PendingFollowUp',
  received_at: '2026-07-29T15:17:00Z',
  created_at: '2026-07-29T15:17:00Z',
  manager_notes: '',
  system_notes: '',
  attachment_count: 0,
  thread_message_count: 1,
  timeline: [
    {
      entry_id: 'msg-001',
      record_id: 'rec-001',
      sender: 'Tarun',
      timestamp: 'Jul 29, 3:17 PM',
      body_preview: 'Hi Sara...',
      is_system_note: false,
    }
  ],
  record_version: 1,
  workflow: {
    allowed_actions: [
      { action_id: 'CREATE_DRAFT', label: 'Create Draft', style: 'primary', execution_kind: 'draft_command' },
      { action_id: 'REVIEW_OUTCOME', label: 'Review Outcome', style: 'secondary', execution_kind: 'workflow_mutation' }
    ]
  } as any
};

describe('ManagerActionBar Component', () => {
  it('renders primary allowed action button from backend DTO', () => {
    const handleOpenModal = vi.fn();
    render(
      <ManagerActionBar
        record={mockRecord}
        onOpenModal={handleOpenModal}
      />
    );

    const button = screen.getByRole('button', { name: /Create Draft/i });
    expect(button).toBeInTheDocument();

    fireEvent.click(button);
    expect(handleOpenModal).toHaveBeenCalledWith('followup');
  });

  it('renders secondary allowed action button from backend DTO', () => {
    const handleOpenModal = vi.fn();
    render(
      <ManagerActionBar
        record={mockRecord}
        onOpenModal={handleOpenModal}
      />
    );

    const button = screen.getByRole('button', { name: /Review Outcome/i });
    expect(button).toBeInTheDocument();

    fireEvent.click(button);
    expect(handleOpenModal).toHaveBeenCalledWith('review_outcome');
  });

  it('renders incomplete banner when record timeline is empty', () => {
    const incompleteRecord: FullRecord = { ...mockRecord, timeline: [], thread_message_count: 0 };
    render(
      <ManagerActionBar
        record={incompleteRecord}
        onOpenModal={vi.fn()}
      />
    );

    expect(screen.getByText(/Incomplete record/i)).toBeInTheDocument();
  });
});
