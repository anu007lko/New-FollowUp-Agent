import type { FullRecord } from '../types';
import { OverflowMenu } from './OverflowMenu';
import { IconWarning } from './icons';
import { playSound } from '../utils/audio';

interface ActionDTO {
  action_id: string;
  label: string;
  style: 'primary' | 'secondary' | 'danger' | 'ghost';
  execution_kind: 'workflow_mutation' | 'draft_command' | 'navigation';
  requires_confirmation?: boolean;
}

interface ManagerActionBarProps {
  record: FullRecord;
  onOpenModal: (actionType: string) => void;
  draftCreationAvailable?: boolean;
}

function openModalForAction(action_id: string, onOpenModal: (type: string) => void) {
  if (action_id === 'CREATE_DRAFT' || action_id === 'REVIEW_FOLLOW_UP_DRAFT') onOpenModal('followup');
  else if (action_id === 'REVIEW_OUTCOME') onOpenModal('review_outcome');
  else if (action_id === 'CLOSE_RECORD') onOpenModal('close');
  else if (action_id === 'MARK_DUPLICATE_SUBMISSION') onOpenModal('action_duplicate');
  else if (action_id === 'REOPEN_RECORD') onOpenModal('reopen');
  else if (action_id === 'ADD_NOTE') onOpenModal('note');
  else if (action_id === 'INTERVIEW_CONFIRMATION') onOpenModal('interview');
  else onOpenModal(action_id.toLowerCase());
}

export function ManagerActionBar({ record, onOpenModal, draftCreationAvailable: _draftCreationAvailable = false }: ManagerActionBarProps) {
  const workflow = (record as any).workflow;
  const allowedActions: ActionDTO[] = workflow?.allowed_actions || [];

  const isIncomplete = (!record.timeline || record.timeline.length === 0) && (!record.logical_message_count && record.thread_message_count === 0);

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

  // If backend workflow allowed_actions exist, render directly from DTO
  if (allowedActions.length > 0) {
    const primaryDTO = allowedActions.find(a => a.style === 'primary');
    const secondaryDTO = allowedActions.find(a => a.style === 'secondary');

    const overflowDTOs = allowedActions.filter(
      a => a !== primaryDTO && a !== secondaryDTO
    );

    const overflowItems = overflowDTOs.map(a => ({
      label: a.label,
      onClick: () => {
        playSound('click');
        openModalForAction(a.action_id, onOpenModal);
      },
      danger: a.style === 'danger'
    }));

    return (
      <div className="manager-action-bar-wrap">
        <div className="manager-action-bar" role="region" aria-label="Record action bar">
          {primaryDTO && (
            <button
              className="btn-action btn-primary"
              onClick={() => {
                playSound('click');
                openModalForAction(primaryDTO.action_id, onOpenModal);
              }}
              aria-label={primaryDTO.label}
            >
              {primaryDTO.label}
            </button>
          )}

          {secondaryDTO && (
            <button
              className="btn-action btn-secondary"
              onClick={() => {
                playSound('click');
                openModalForAction(secondaryDTO.action_id, onOpenModal);
              }}
              aria-label={secondaryDTO.label}
              style={{ marginLeft: '8px' }}
            >
              {secondaryDTO.label}
            </button>
          )}

          <div className="action-bar-spacer" />
          {overflowItems.length > 0 && <OverflowMenu items={overflowItems} />}
        </div>
      </div>
    );
  }

  return (
    <div className="manager-action-bar-wrap">
      <div className="manager-action-bar" role="region" aria-label="Record action bar">
        <button className="btn-action btn-secondary" disabled style={{ opacity: 0.6, cursor: 'not-allowed' }}>
          No actions available
        </button>
      </div>
    </div>
  );
}
