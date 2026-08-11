"""
Unit tests for WorkflowPolicyEngine and WorkflowViewComposer.
Covers the regression matrix (§19.1 - §19.7).
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest

from backend.app.domain.models import (
    WorkflowStatus, ActionID, CloseReason, OutcomeOptionID,
    ActionStyle, ActionExecutionKind, QueueID, DisplayTone,
    ActionExecutionRequest, ClassificationProposal, AuditEventType,
    normalize_close_reason
)
from backend.app.domain.workflow_policy_engine import WorkflowPolicyEngine, TIMEZONE_NEW_YORK
from backend.app.domain.workflow_view_composer import WorkflowViewComposer, normalize_workflow_status


# --- §19.1 Every Action x Status ---

def test_close_record_needs_review_duplicate():
    req = ActionExecutionRequest(
        action_id=ActionID.CLOSE_RECORD,
        record_version=1,
        reason=CloseReason.DUPLICATE_SUBMISSION_ENTRY
    )
    status, reason, note = WorkflowPolicyEngine.validate_action(
        ActionID.CLOSE_RECORD, WorkflowStatus.NEEDS_REVIEW, req, stored_version=1
    )
    assert status == WorkflowStatus.CLOSED
    assert reason == CloseReason.DUPLICATE_SUBMISSION_ENTRY


def test_close_record_tracking_client_rejected():
    req = ActionExecutionRequest(
        action_id=ActionID.CLOSE_RECORD,
        record_version=1,
        reason=CloseReason.CLIENT_REJECTED
    )
    status, reason, _ = WorkflowPolicyEngine.validate_action(
        ActionID.CLOSE_RECORD, WorkflowStatus.TRACKING, req, stored_version=1
    )
    assert status == WorkflowStatus.CLOSED
    assert reason == CloseReason.CLIENT_REJECTED


def test_close_record_other_requires_note():
    req_no_note = ActionExecutionRequest(
        action_id=ActionID.CLOSE_RECORD,
        record_version=1,
        reason=CloseReason.OTHER
    )
    with pytest.raises(ValueError, match="requires an explanatory note"):
        WorkflowPolicyEngine.validate_action(
            ActionID.CLOSE_RECORD, WorkflowStatus.ACTION_REQUIRED, req_no_note, stored_version=1
        )

    req_with_note = ActionExecutionRequest(
        action_id=ActionID.CLOSE_RECORD,
        record_version=1,
        reason=CloseReason.OTHER,
        note="Custom close reason details"
    )
    status, reason, note = WorkflowPolicyEngine.validate_action(
        ActionID.CLOSE_RECORD, WorkflowStatus.ACTION_REQUIRED, req_with_note, stored_version=1
    )
    assert status == WorkflowStatus.CLOSED
    assert reason == CloseReason.OTHER
    assert note == "Custom close reason details"


def test_close_record_already_closed_fails():
    req = ActionExecutionRequest(
        action_id=ActionID.CLOSE_RECORD,
        record_version=1,
        reason=CloseReason.POSITION_CLOSED
    )
    with pytest.raises(ValueError, match="Cannot perform action 'CLOSE_RECORD' on a Closed record"):
        WorkflowPolicyEngine.validate_action(
            ActionID.CLOSE_RECORD, WorkflowStatus.CLOSED, req, stored_version=1
        )


def test_mark_duplicate_submission_locked_reason():
    req = ActionExecutionRequest(
        action_id=ActionID.MARK_DUPLICATE_SUBMISSION,
        record_version=1
    )
    status, reason, _ = WorkflowPolicyEngine.validate_action(
        ActionID.MARK_DUPLICATE_SUBMISSION, WorkflowStatus.NEEDS_REVIEW, req, stored_version=1
    )
    assert status == WorkflowStatus.CLOSED
    assert reason == CloseReason.DUPLICATE_SUBMISSION_ENTRY


def test_mark_duplicate_submission_rejects_override_attempt():
    req = ActionExecutionRequest(
        action_id=ActionID.MARK_DUPLICATE_SUBMISSION,
        record_version=1,
        reason=CloseReason.CLIENT_REJECTED
    )
    with pytest.raises(ValueError, match="MARK_DUPLICATE_SUBMISSION locked reason is"):
        WorkflowPolicyEngine.validate_action(
            ActionID.MARK_DUPLICATE_SUBMISSION, WorkflowStatus.NEEDS_REVIEW, req, stored_version=1
        )


def test_reopen_record_success():
    req = ActionExecutionRequest(
        action_id=ActionID.REOPEN_RECORD,
        record_version=1
    )
    status, reason, _ = WorkflowPolicyEngine.validate_action(
        ActionID.REOPEN_RECORD, WorkflowStatus.CLOSED, req, stored_version=1
    )
    assert status == WorkflowStatus.NEEDS_REVIEW
    assert reason is None


def test_reopen_record_active_fails():
    req = ActionExecutionRequest(
        action_id=ActionID.REOPEN_RECORD,
        record_version=1
    )
    with pytest.raises(ValueError, match="Cannot reopen record with status 'NeedsReview'"):
        WorkflowPolicyEngine.validate_action(
            ActionID.REOPEN_RECORD, WorkflowStatus.NEEDS_REVIEW, req, stored_version=1
        )


def test_review_outcome_options():
    # Position closed -> terminal closed
    req1 = ActionExecutionRequest(
        action_id=ActionID.REVIEW_OUTCOME,
        record_version=1,
        outcome_option_id=OutcomeOptionID.POSITION_CLOSED
    )
    status, reason, _ = WorkflowPolicyEngine.validate_action(
        ActionID.REVIEW_OUTCOME, WorkflowStatus.NEEDS_REVIEW, req1, stored_version=1
    )
    assert status == WorkflowStatus.CLOSED
    assert reason == CloseReason.POSITION_CLOSED

    # On Hold -> non-terminal Tracking
    req2 = ActionExecutionRequest(
        action_id=ActionID.REVIEW_OUTCOME,
        record_version=1,
        outcome_option_id=OutcomeOptionID.ON_HOLD
    )
    status, reason, _ = WorkflowPolicyEngine.validate_action(
        ActionID.REVIEW_OUTCOME, WorkflowStatus.ACTION_REQUIRED, req2, stored_version=1
    )
    assert status == WorkflowStatus.TRACKING
    assert reason is None

    # Other closed without note -> fails
    req3 = ActionExecutionRequest(
        action_id=ActionID.REVIEW_OUTCOME,
        record_version=1,
        outcome_option_id=OutcomeOptionID.OTHER_CLOSED
    )
    with pytest.raises(ValueError, match="requires an explanatory note"):
        WorkflowPolicyEngine.validate_action(
            ActionID.REVIEW_OUTCOME, WorkflowStatus.FEEDBACK_PENDING, req3, stored_version=1
        )


def test_add_note():
    req = ActionExecutionRequest(
        action_id=ActionID.ADD_NOTE,
        record_version=1,
        note="Timeline note text"
    )
    status, reason, note = WorkflowPolicyEngine.validate_action(
        ActionID.ADD_NOTE, WorkflowStatus.CLOSED, req, stored_version=1
    )
    assert status == WorkflowStatus.CLOSED
    assert reason is None
    assert note == "Timeline note text"


# --- §19.2 Legacy Alias Normalization ---

def test_alias_normalization():
    assert normalize_close_reason("Duplicate submission") == CloseReason.DUPLICATE_SUBMISSION_ENTRY
    assert normalize_close_reason("Duplicate Submission") == CloseReason.DUPLICATE_SUBMISSION_ENTRY
    assert normalize_close_reason("Candidate already submitted by another vendor") == CloseReason.DUPLICATE_SUBMISSION_ENTRY
    assert normalize_close_reason("Client Rejected") == CloseReason.CLIENT_REJECTED
    assert normalize_close_reason("Position Closed") == CloseReason.POSITION_CLOSED

    with pytest.raises(ValueError, match="Unknown close reason"):
        normalize_close_reason("unknown garbage")


def test_action_execution_request_alias_before_validator():
    req = ActionExecutionRequest(
        action_id=ActionID.CLOSE_RECORD,
        record_version=1,
        reason="Duplicate Submission"  # Raw string alias
    )
    assert req.reason == CloseReason.DUPLICATE_SUBMISSION_ENTRY


# --- §19.3 Classifier & Closed Immunity ---

def test_classifier_proposal_evaluation():
    prop = ClassificationProposal(evidence_category="Interview Completed")

    # Active record -> updates evidence snapshot, does not transition status
    dec1 = WorkflowPolicyEngine.evaluate_classifier_proposal(WorkflowStatus.TRACKING, prop)
    assert dec1.update_evidence is True
    assert dec1.new_classification_category == "Interview Completed"

    # Closed record -> ignores proposal completely
    dec2 = WorkflowPolicyEngine.evaluate_classifier_proposal(WorkflowStatus.CLOSED, prop)
    assert dec2.update_evidence is False
    assert "Closed" in dec2.ignored_reason


# --- §19.4 Concurrency & Cache ---

def test_stale_record_version_conflict():
    req = ActionExecutionRequest(
        action_id=ActionID.CLOSE_RECORD,
        record_version=1,
        reason=CloseReason.POSITION_CLOSED
    )
    with pytest.raises(ValueError, match="CONFLICT: Stale record version"):
        WorkflowPolicyEngine.validate_action(
            ActionID.CLOSE_RECORD, WorkflowStatus.NEEDS_REVIEW, req, stored_version=2
        )


# --- §19.5 Timezone & Calendar ---

def test_time_based_transitions_friday_to_monday():
    # Friday 5 PM EDT interview end
    fri_5pm = datetime(2026, 8, 7, 17, 0, 0, tzinfo=TIMEZONE_NEW_YORK)
    fri_iso = fri_5pm.isoformat()

    # Sat 10 AM ET -> FeedbackPending (not next business morning yet)
    sat_10am = datetime(2026, 8, 8, 10, 0, 0, tzinfo=TIMEZONE_NEW_YORK)
    res_sat = WorkflowPolicyEngine.evaluate_time_based_transition(
        WorkflowStatus.INTERVIEW_SCHEDULED, fri_iso, None, sat_10am
    )
    assert res_sat == WorkflowStatus.FEEDBACK_PENDING

    # Mon 8:59 AM ET -> FeedbackPending
    mon_859am = datetime(2026, 8, 10, 8, 59, 0, tzinfo=TIMEZONE_NEW_YORK)
    res_mon_before = WorkflowPolicyEngine.evaluate_time_based_transition(
        WorkflowStatus.FEEDBACK_PENDING, fri_iso, None, mon_859am
    )
    assert res_mon_before is None  # Status remains FeedbackPending

    # Mon 9:01 AM ET -> FeedbackDue
    mon_901am = datetime(2026, 8, 10, 9, 1, 0, tzinfo=TIMEZONE_NEW_YORK)
    res_mon_after = WorkflowPolicyEngine.evaluate_time_based_transition(
        WorkflowStatus.FEEDBACK_PENDING, fri_iso, None, mon_901am
    )
    assert res_mon_after == WorkflowStatus.FEEDBACK_DUE


# --- §19.6 UI Consistency & Display Labels ---

def test_view_composer_closed_display_labels():
    # Duplicate submission entry -> Duplicate Submission
    dto1 = WorkflowViewComposer.compose_compact_workflow_dto(
        WorkflowStatus.CLOSED, close_reason=CloseReason.DUPLICATE_SUBMISSION_ENTRY
    )
    assert dto1.display.label == "Duplicate Submission"
    assert dto1.display.tone == DisplayTone.CLOSED
    assert dto1.queue_membership == [QueueID.CLOSED]
    assert dto1.evidence_category == "Duplicate Submission"

    # Client rejected -> Client Rejected
    dto2 = WorkflowViewComposer.compose_compact_workflow_dto(
        WorkflowStatus.CLOSED, close_reason=CloseReason.CLIENT_REJECTED
    )
    assert dto2.display.label == "Client Rejected"

    # No follow-up needed -> Closed
    dto3 = WorkflowViewComposer.compose_compact_workflow_dto(
        WorkflowStatus.CLOSED, close_reason=CloseReason.NO_FOLLOW_UP_NEEDED
    )
    assert dto3.display.label == "Closed"


def test_view_composer_active_queues():
    dto_fp = WorkflowViewComposer.compose_compact_workflow_dto(WorkflowStatus.FEEDBACK_PENDING)
    assert dto_fp.queue_membership == [QueueID.INTERVIEWS, QueueID.FEEDBACK_PENDING]

    dto_fd = WorkflowViewComposer.compose_compact_workflow_dto(WorkflowStatus.FEEDBACK_DUE)
    assert dto_fd.queue_membership == [QueueID.INTERVIEWS, QueueID.FEEDBACK_DUE]


# --- §19.7 Fallback & Edge Cases ---

def test_rejected_fields_validation():
    # CLOSE_RECORD with outcome_option_id present
    req1 = ActionExecutionRequest(
        action_id=ActionID.CLOSE_RECORD,
        record_version=1,
        reason=CloseReason.POSITION_CLOSED,
        outcome_option_id=OutcomeOptionID.POSITION_CLOSED
    )
    with pytest.raises(ValueError, match="rejects 'outcome_option_id' field"):
        WorkflowPolicyEngine.validate_action(
            ActionID.CLOSE_RECORD, WorkflowStatus.TRACKING, req1, stored_version=1
        )

    # ADD_NOTE with reason present
    req2 = ActionExecutionRequest(
        action_id=ActionID.ADD_NOTE,
        record_version=1,
        reason=CloseReason.OTHER,
        note="Test note"
    )
    with pytest.raises(ValueError, match="rejects 'reason' and 'outcome_option_id' fields"):
        WorkflowPolicyEngine.validate_action(
            ActionID.ADD_NOTE, WorkflowStatus.TRACKING, req2, stored_version=1
        )
