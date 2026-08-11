"""
Workflow Policy Engine — Single source of truth for workflow status transitions,
action eligibility, input validation, reason normalization, outcome options,
classifier proposal evaluation, and timer-driven transitions.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Optional, Tuple, Dict, Any, Set

from backend.app.domain.models import (
    WorkflowStatus, ActionID, CloseReason, OutcomeOptionID,
    ActionStyle, ActionExecutionKind, OutcomeOptionDTO, ActionDTO,
    ActionExecutionRequest, ClassificationProposal, ClassificationDecision
)

TIMEZONE_NEW_YORK = ZoneInfo("America/New_York")

# --- §6.2 Canonical Outcome Options ---

CANONICAL_OUTCOME_OPTIONS: List[OutcomeOptionDTO] = [
    OutcomeOptionDTO(
        option_id=OutcomeOptionID.POSITION_CLOSED,
        label="Position Closed",
        is_terminal=True,
        resulting_status=WorkflowStatus.CLOSED,
        close_reason=CloseReason.POSITION_CLOSED,
        requires_note=False
    ),
    OutcomeOptionDTO(
        option_id=OutcomeOptionID.CLIENT_REJECTED,
        label="Client Rejected",
        is_terminal=True,
        resulting_status=WorkflowStatus.CLOSED,
        close_reason=CloseReason.CLIENT_REJECTED,
        requires_note=False
    ),
    OutcomeOptionDTO(
        option_id=OutcomeOptionID.CANDIDATE_WITHDRAWN,
        label="Candidate Withdrawn",
        is_terminal=True,
        resulting_status=WorkflowStatus.CLOSED,
        close_reason=CloseReason.CANDIDATE_WITHDRAWN,
        requires_note=False
    ),
    OutcomeOptionDTO(
        option_id=OutcomeOptionID.DUPLICATE_SUBMISSION,
        label="Duplicate Submission",
        is_terminal=True,
        resulting_status=WorkflowStatus.CLOSED,
        close_reason=CloseReason.DUPLICATE_SUBMISSION_ENTRY,
        requires_note=False
    ),
    OutcomeOptionDTO(
        option_id=OutcomeOptionID.PLACED_JOINED,
        label="Placed / Joined",
        is_terminal=True,
        resulting_status=WorkflowStatus.CLOSED,
        close_reason=CloseReason.PLACED_JOINED,
        requires_note=False
    ),
    OutcomeOptionDTO(
        option_id=OutcomeOptionID.NO_LONGER_AVAILABLE,
        label="No Longer Available",
        is_terminal=True,
        resulting_status=WorkflowStatus.CLOSED,
        close_reason=CloseReason.NO_LONGER_AVAILABLE,
        requires_note=False
    ),
    OutcomeOptionDTO(
        option_id=OutcomeOptionID.NO_FOLLOW_UP_NEEDED,
        label="No Follow-up Needed",
        is_terminal=True,
        resulting_status=WorkflowStatus.CLOSED,
        close_reason=CloseReason.NO_FOLLOW_UP_NEEDED,
        requires_note=False
    ),
    OutcomeOptionDTO(
        option_id=OutcomeOptionID.OTHER_CLOSED,
        label="Other (Close)",
        is_terminal=True,
        resulting_status=WorkflowStatus.CLOSED,
        close_reason=CloseReason.OTHER,
        requires_note=True,
        note_hint="Specify reason for closing record"
    ),
    OutcomeOptionDTO(
        option_id=OutcomeOptionID.ON_HOLD,
        label="On Hold",
        is_terminal=False,
        resulting_status=WorkflowStatus.TRACKING,
        close_reason=None,
        requires_note=False
    ),
    OutcomeOptionDTO(
        option_id=OutcomeOptionID.KEEP_IN_REVIEW,
        label="Keep in Review",
        is_terminal=False,
        resulting_status=WorkflowStatus.NEEDS_REVIEW,
        close_reason=None,
        requires_note=False
    ),
]

_OUTCOME_OPTIONS_BY_ID: Dict[OutcomeOptionID, OutcomeOptionDTO] = {
    opt.option_id: opt for opt in CANONICAL_OUTCOME_OPTIONS
}


class WorkflowPolicyEngine:
    """Single authority for workflow policies."""

    @staticmethod
    def is_active_status(status: WorkflowStatus) -> bool:
        return status != WorkflowStatus.CLOSED

    @staticmethod
    def get_allowed_actions(status: WorkflowStatus, has_draft: bool = False) -> List[ActionDTO]:
        """Returns ordered list of allowed actions for given status and draft presence."""
        actions: List[ActionDTO] = []

        if status == WorkflowStatus.CLOSED:
            # Closed status allowed actions
            actions.append(ActionDTO(
                action_id=ActionID.REOPEN_RECORD,
                label="Reopen Record",
                style=ActionStyle.PRIMARY,
                execution_kind=ActionExecutionKind.WORKFLOW_MUTATION,
                requires_confirmation=True,
                confirmation_title="Reopen Record",
                confirmation_message="Reopen this record and return to active review?"
            ))
            actions.append(ActionDTO(
                action_id=ActionID.ADD_NOTE,
                label="Add Note",
                style=ActionStyle.GHOST,
                execution_kind=ActionExecutionKind.WORKFLOW_MUTATION
            ))
            actions.append(ActionDTO(
                action_id=ActionID.VIEW_CONVERSATION,
                label="View Thread",
                style=ActionStyle.GHOST,
                execution_kind=ActionExecutionKind.NAVIGATION
            ))
            actions.append(ActionDTO(
                action_id=ActionID.VIEW_AUDIT_TRAIL,
                label="View Audit History",
                style=ActionStyle.GHOST,
                execution_kind=ActionExecutionKind.NAVIGATION
            ))
            return actions

        # Active statuses
        # 1. Primary Action
        if status == WorkflowStatus.NEEDS_REVIEW:
            actions.append(ActionDTO(
                action_id=ActionID.REVIEW_OUTCOME,
                label="Review Outcome",
                style=ActionStyle.PRIMARY,
                execution_kind=ActionExecutionKind.WORKFLOW_MUTATION,
                outcome_options=CANONICAL_OUTCOME_OPTIONS
            ))
            if has_draft:
                actions.append(ActionDTO(
                    action_id=ActionID.REVIEW_FOLLOW_UP_DRAFT,
                    label="Review Draft",
                    style=ActionStyle.SECONDARY,
                    execution_kind=ActionExecutionKind.DRAFT_COMMAND
                ))
            else:
                actions.append(ActionDTO(
                    action_id=ActionID.CREATE_DRAFT,
                    label="Create Draft",
                    style=ActionStyle.SECONDARY,
                    execution_kind=ActionExecutionKind.DRAFT_COMMAND
                ))
        else:
            # Tracking, ActionRequired, InterviewScheduled, FeedbackPending, FeedbackDue
            if has_draft:
                actions.append(ActionDTO(
                    action_id=ActionID.REVIEW_FOLLOW_UP_DRAFT,
                    label="Review Draft",
                    style=ActionStyle.PRIMARY,
                    execution_kind=ActionExecutionKind.DRAFT_COMMAND
                ))
            else:
                actions.append(ActionDTO(
                    action_id=ActionID.CREATE_DRAFT,
                    label="Create Draft",
                    style=ActionStyle.PRIMARY,
                    execution_kind=ActionExecutionKind.DRAFT_COMMAND
                ))
            actions.append(ActionDTO(
                action_id=ActionID.REVIEW_OUTCOME,
                label="Review Outcome",
                style=ActionStyle.SECONDARY,
                execution_kind=ActionExecutionKind.WORKFLOW_MUTATION,
                outcome_options=CANONICAL_OUTCOME_OPTIONS
            ))

        # Secondary / Mutation Actions
        actions.append(ActionDTO(
            action_id=ActionID.CLOSE_RECORD,
            label="Close Record",
            style=ActionStyle.DANGER,
            execution_kind=ActionExecutionKind.WORKFLOW_MUTATION,
            requires_confirmation=True,
            confirmation_title="Close Record",
            confirmation_message="Are you sure you want to close this record?",
            reason_options=list(CloseReason),
            note_required_when_reason=CloseReason.OTHER
        ))

        actions.append(ActionDTO(
            action_id=ActionID.MARK_DUPLICATE_SUBMISSION,
            label="Mark Duplicate",
            style=ActionStyle.DANGER,
            execution_kind=ActionExecutionKind.WORKFLOW_MUTATION,
            requires_confirmation=True,
            confirmation_title="Mark Duplicate Submission",
            confirmation_message="Confirm duplicate submission for this candidate?",
            reason_options=[CloseReason.DUPLICATE_SUBMISSION_ENTRY],
            locked_reason=CloseReason.DUPLICATE_SUBMISSION_ENTRY
        ))

        actions.append(ActionDTO(
            action_id=ActionID.ADD_NOTE,
            label="Add Note",
            style=ActionStyle.GHOST,
            execution_kind=ActionExecutionKind.WORKFLOW_MUTATION
        ))

        # Navigation Actions
        actions.append(ActionDTO(
            action_id=ActionID.VIEW_CONVERSATION,
            label="View Thread",
            style=ActionStyle.GHOST,
            execution_kind=ActionExecutionKind.NAVIGATION
        ))

        actions.append(ActionDTO(
            action_id=ActionID.VIEW_AUDIT_TRAIL,
            label="View Audit History",
            style=ActionStyle.GHOST,
            execution_kind=ActionExecutionKind.NAVIGATION
        ))

        return actions

    @classmethod
    def validate_action(
        cls,
        action_id: ActionID,
        current_status: WorkflowStatus,
        request: ActionExecutionRequest,
        stored_version: int
    ) -> Tuple[WorkflowStatus, Optional[CloseReason], Optional[str]]:
        """
        Validates a workflow mutation request against the current state.

        Returns: (resulting_status, close_reason, close_note)
        Raises: ValueError (mapped to HTTP 400) or ConflictError (mapped to HTTP 409).
        """
        # Concurrency check
        if request.record_version != stored_version:
            raise ValueError(f"CONFLICT: Stale record version {request.record_version}, stored is {stored_version}")

        # Check action eligibility for status
        if action_id == ActionID.REOPEN_RECORD:
            if current_status != WorkflowStatus.CLOSED:
                raise ValueError(f"Cannot reopen record with status '{current_status.value}'. Record must be Closed.")
            # Rejected fields check
            if request.reason is not None or request.outcome_option_id is not None:
                raise ValueError("REOPEN_RECORD rejects 'reason' and 'outcome_option_id' fields.")
            return (WorkflowStatus.NEEDS_REVIEW, None, request.note)

        if action_id == ActionID.ADD_NOTE:
            if request.reason is not None or request.outcome_option_id is not None:
                raise ValueError("ADD_NOTE rejects 'reason' and 'outcome_option_id' fields.")
            if not request.note or not request.note.strip():
                raise ValueError("ADD_NOTE requires non-empty 'note' content.")
            return (current_status, None, request.note)

        # All other mutations require active status
        if current_status == WorkflowStatus.CLOSED:
            raise ValueError(f"Cannot perform action '{action_id.value}' on a Closed record.")

        if action_id == ActionID.CLOSE_RECORD:
            if request.outcome_option_id is not None:
                raise ValueError("CLOSE_RECORD rejects 'outcome_option_id' field.")
            if request.reason is None:
                raise ValueError("CLOSE_RECORD requires a valid 'reason'.")
            if request.reason == CloseReason.OTHER:
                if not request.note or not request.note.strip():
                    raise ValueError("Closing with reason 'Other' requires an explanatory note.")
            return (WorkflowStatus.CLOSED, request.reason, request.note)

        elif action_id == ActionID.MARK_DUPLICATE_SUBMISSION:
            if request.outcome_option_id is not None:
                raise ValueError("MARK_DUPLICATE_SUBMISSION rejects 'outcome_option_id' field.")
            if request.reason is not None and request.reason != CloseReason.DUPLICATE_SUBMISSION_ENTRY:
                raise ValueError(f"MARK_DUPLICATE_SUBMISSION locked reason is '{CloseReason.DUPLICATE_SUBMISSION_ENTRY}'. Cannot override with '{request.reason}'.")
            return (WorkflowStatus.CLOSED, CloseReason.DUPLICATE_SUBMISSION_ENTRY, request.note)

        elif action_id == ActionID.REVIEW_OUTCOME:
            if request.reason is not None:
                raise ValueError("REVIEW_OUTCOME rejects direct 'reason' field (derived from outcome option).")
            if request.outcome_option_id is None:
                raise ValueError("REVIEW_OUTCOME requires an 'outcome_option_id'.")

            option = _OUTCOME_OPTIONS_BY_ID.get(request.outcome_option_id)
            if option is None:
                raise ValueError(f"Unknown outcome_option_id '{request.outcome_option_id}'.")

            if option.requires_note and (not request.note or not request.note.strip()):
                raise ValueError(f"Outcome option '{option.label}' requires an explanatory note.")

            return (option.resulting_status, option.close_reason, request.note)

        elif action_id == ActionID.ADD_NOTE:
            if request.reason is not None or request.outcome_option_id is not None:
                raise ValueError("ADD_NOTE rejects 'reason' and 'outcome_option_id' fields.")
            if not request.note or not request.note.strip():
                raise ValueError("ADD_NOTE requires non-empty 'note' content.")
            return (current_status, None, request.note)

        else:
            raise ValueError(f"Action '{action_id}' is not a valid workflow mutation endpoint action.")

    @classmethod
    def evaluate_classifier_proposal(
        cls,
        record_status: WorkflowStatus,
        proposal: ClassificationProposal
    ) -> ClassificationDecision:
        """
        Evaluates classifier output against current record status.
        V1 rule: Classifier evidence updates evidence snapshot for active records, but NEVER transitions workflow_status.
        Closed records ignore classifier evidence entirely.
        """
        if record_status == WorkflowStatus.CLOSED:
            return ClassificationDecision(
                update_evidence=False,
                ignored_reason="Record is Closed. Classifier evidence is ignored."
            )

        if not proposal.evidence_category:
            return ClassificationDecision(
                update_evidence=False,
                ignored_reason="No evidence category in proposal."
            )

        return ClassificationDecision(
            update_evidence=True,
            new_classification_category=proposal.evidence_category
        )

    @classmethod
    def evaluate_time_based_transition(
        cls,
        record_status: WorkflowStatus,
        interview_end_datetime_iso: Optional[str],
        follow_up_due_datetime_iso: Optional[str],
        current_time: datetime,
        holidays: Optional[Set[Any]] = None
    ) -> Optional[WorkflowStatus]:
        """
        Evaluates timer-driven transitions for active records.
        """
        if record_status == WorkflowStatus.CLOSED:
            return None

        # Rule 1 & 2: InterviewScheduled -> FeedbackPending -> FeedbackDue
        if record_status in (WorkflowStatus.INTERVIEW_SCHEDULED, WorkflowStatus.FEEDBACK_PENDING):
            if interview_end_datetime_iso:
                try:
                    dt = datetime.fromisoformat(interview_end_datetime_iso)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=TIMEZONE_NEW_YORK)

                    if current_time >= dt:
                        # Interview end has elapsed. Check next business morning 9 AM NY cutoff.
                        local_dt = dt.astimezone(TIMEZONE_NEW_YORK)

                        # Find next business day
                        next_day = local_dt.date() + timedelta(days=1)
                        while next_day.weekday() in (5, 6) or (holidays and next_day in holidays):
                            next_day += timedelta(days=1)

                        cutoff_9am = datetime.combine(
                            next_day,
                            datetime.min.time().replace(hour=9)
                        ).replace(tzinfo=TIMEZONE_NEW_YORK)

                        if current_time >= cutoff_9am:
                            if record_status != WorkflowStatus.FEEDBACK_DUE:
                                return WorkflowStatus.FEEDBACK_DUE
                        else:
                            if record_status == WorkflowStatus.INTERVIEW_SCHEDULED:
                                return WorkflowStatus.FEEDBACK_PENDING
                except ValueError:
                    pass

        # Rule 3: Tracking -> ActionRequired (48h / follow_up_due)
        if record_status == WorkflowStatus.TRACKING:
            if follow_up_due_datetime_iso:
                try:
                    dt = datetime.fromisoformat(follow_up_due_datetime_iso)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=TIMEZONE_NEW_YORK)
                    if current_time >= dt:
                        return WorkflowStatus.ACTION_REQUIRED
                except ValueError:
                    pass

        return None
