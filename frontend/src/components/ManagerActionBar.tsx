import type { FullRecord } from '../types';
import { OverflowMenu } from './OverflowMenu';
import { IconWarning } from './icons';

interface ManagerActionBarProps {
  record: FullRecord;
  onOpenModal: (actionType: string) => void;
  draftCreationAvailable?: boolean;
}

export function ManagerActionBar({ record, onOpenModal, draftCreationAvailable = false }: ManagerActionBarProps) {
  const ds = record.domain_status;
  const isIncomplete = (!record.timeline || record.timeline.length === 0) || (record.thread_message_count === 0);

  if (isIncomplete) {
    return (
      <div className="manager-action-bar manager-action-bar-incomplete" role="region" aria-label="Record action bar">
        <p className="incomplete-banner-text">
          <IconWarning size={14} />
          Incomplete record — cannot take action until conversation is recovered.
        </p>
      </div>
    );
  }

  if (ds === 'Closed') {
    return (
      <div className="manager-action-bar" role="region" aria-label="Record action bar">
        <button
          className="btn-action btn-primary"
          onClick={() => onOpenModal('reopen')}
          aria-label="Reopen record"
        >
          Reopen Record
        </button>
      </div>
    );
  }

  // Build primary + secondary actions based on status
  let primaryLabel = 'Add Note';
  let primaryAction = 'note';
  const overflowItems: { label: string; onClick: () => void; danger?: boolean; disabled?: boolean }[] = [];

  if (ds === 'PendingFollowUp') {
    primaryLabel = draftCreationAvailable ? 'Request Follow-up' : 'Outlook Drafts Paused';
    primaryAction = draftCreationAvailable ? 'followup' : '';
    overflowItems.push({ label: 'Add Note', onClick: () => onOpenModal('note') });
  } else if (ds === 'InterviewAwaitingConfirmation' || ds === 'InterviewScheduled' || ds === 'InterviewRequestScheduled') {
    primaryLabel = 'Confirm Interview';
    primaryAction = 'interview';
    overflowItems.push({ label: 'Add Note', onClick: () => onOpenModal('note') });
  } else if (ds === 'ManagerActionRequired') {
    primaryLabel = 'Review Outcome';
    primaryAction = 'review_outcome';
    overflowItems.push({ label: 'Add Note', onClick: () => onOpenModal('note') });
  } else if (ds === 'NeedsReview' || ds === 'NewSubmission') {
    primaryLabel = 'Set Outcome';
    primaryAction = 'set_outcome';
    overflowItems.push({ label: 'Request Follow-up', onClick: () => onOpenModal('followup'), disabled: !draftCreationAvailable });
    overflowItems.push({ label: 'Add Note', onClick: () => onOpenModal('note') });
  } else if (ds === 'AwaitingFeedback' || ds === 'FeedbackDue') {
    primaryLabel = 'Record Feedback';
    primaryAction = 'set_outcome';
    overflowItems.push({ label: 'Add Note', onClick: () => onOpenModal('note') });
  } else if (ds === 'AwaitingResponse') {
    primaryLabel = 'Add Note';
    primaryAction = 'note';
    overflowItems.push({ label: 'Request Follow-up', onClick: () => onOpenModal('followup'), disabled: !draftCreationAvailable });
  }

  // Close always in overflow as danger
  overflowItems.push({ label: 'Close Record', onClick: () => onOpenModal('close'), danger: true });

  return (
    <div className="manager-action-bar" role="region" aria-label="Record action bar">
      <button
        className="btn-action btn-primary"
        onClick={() => primaryAction && onOpenModal(primaryAction)}
        disabled={!primaryAction}
        title={!primaryAction ? 'Outlook draft creation is paused in the local service.' : undefined}
        aria-label={primaryLabel}
      >
        {primaryLabel}
      </button>
      <div className="action-bar-spacer" />
      <OverflowMenu items={overflowItems} />
    </div>
  );
}
