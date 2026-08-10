import type { FullRecord } from '../types';
import { OverflowMenu } from './OverflowMenu';
import { IconWarning } from './icons';
import { playSound } from '../utils/audio';

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
          onClick={() => { playSound('click'); onOpenModal('reopen'); }}
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

  let interviewDetail = '';

  if (ds === 'PendingFollowUp') {
    primaryLabel = draftCreationAvailable ? 'Request Follow-up' : 'Outlook Drafts Paused';
    primaryAction = draftCreationAvailable ? 'followup' : '';
    overflowItems.push({ label: 'Add Note', onClick: () => onOpenModal('note') });
  } else if (ds === 'InterviewAwaitingConfirmation' || ds === 'InterviewScheduled' || ds === 'InterviewRequestScheduled') {
    const istate = (record.interview_state || '').toLowerCase();
    if (istate === 'scheduled' || istate === 'rescheduled' || ds === 'InterviewRequestScheduled' || ds === 'InterviewScheduled') {
      primaryLabel = 'Update Interview';
    } else if (istate === 'completed' || istate === 'cancelled' || istate === 'not_confirmed') {
      primaryLabel = 'Update Interview Status';
    } else {
      primaryLabel = 'Confirm Interview';
    }
    primaryAction = 'interview';
    overflowItems.push({ label: 'Add Note', onClick: () => onOpenModal('note') });

    const dateVal = record.interview_date || record.structured_evidence?.interview_date;
    const timeVal = record.interview_time || record.structured_evidence?.interview_time;
    const tzVal = record.interview_timezone || record.structured_evidence?.timezone;
    const dateTimeStr = [dateVal, timeVal].filter(Boolean).join(' at ');

    if (istate === 'scheduled' || ds === 'InterviewRequestScheduled' || ds === 'InterviewScheduled') {
      interviewDetail = dateTimeStr ? `Scheduled for ${dateTimeStr}${tzVal ? ` (${tzVal})` : ''}` : 'Interview Scheduled';
    } else if (istate === 'rescheduled') {
      interviewDetail = dateTimeStr ? `Rescheduled for ${dateTimeStr}${tzVal ? ` (${tzVal})` : ''}` : 'Interview Rescheduled';
    } else if (istate === 'completed') {
      interviewDetail = 'Interview Completed';
    } else if (istate === 'cancelled') {
      interviewDetail = 'Interview Cancelled';
    } else if (istate === 'not_confirmed') {
      interviewDetail = 'Interview Not Confirmed';
    }
  } else if (ds === 'ManagerActionRequired') {
    const category = record.structured_evidence?.category;
    const isClosedOutcome = category === 'Rejection' || category === 'Position Closed' || category === 'Client Rejected';

    if (isClosedOutcome) {
      primaryLabel = 'Close Record';
      primaryAction = 'close';
      overflowItems.push({ label: 'Review Outcome', onClick: () => onOpenModal('review_outcome') });
      overflowItems.push({ label: 'Add Note', onClick: () => onOpenModal('note') });
    } else {
      primaryLabel = 'Review Outcome';
      primaryAction = 'review_outcome';
      overflowItems.push({ label: 'Add Note', onClick: () => onOpenModal('note') });
    }
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

  // Close always in overflow as danger unless it is already the primary action
  if (primaryAction !== 'close') {
    overflowItems.push({ label: 'Close Record', onClick: () => onOpenModal('close'), danger: true });
  }

  return (
    <div className="manager-action-bar-wrap">
      <div className="manager-action-bar" role="region" aria-label="Record action bar">
        <button
          className="btn-action btn-primary"
          onClick={() => { playSound('click'); primaryAction && onOpenModal(primaryAction); }}
          disabled={!primaryAction}
          title={!primaryAction ? 'Outlook draft creation is paused in the local service.' : undefined}
          aria-label={primaryLabel}
        >
          {primaryLabel}
        </button>
        <div className="action-bar-spacer" />
        <OverflowMenu items={overflowItems} />
      </div>
      {interviewDetail && (
        <div className="manager-action-detail" style={{ fontSize: '0.8rem', color: 'var(--figma-quiet, #b9bdc7)', marginTop: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span>ℹ</span>
          <span>{interviewDetail}</span>
        </div>
      )}
    </div>
  );
}
