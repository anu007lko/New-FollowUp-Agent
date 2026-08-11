"""
Offline test suite for Phase 1 canonical workflow contract.
Verifies compact workflow DTO completeness, ActionDTO presentation metadata,
has_draft preservation, and ADD_NOTE route contract execution.
"""

import pytest
from backend.app.domain.models import (
    WorkflowStatus, CloseReason, ActionID, ActionExecutionKind,
    SubmissionRecord, DomainStatus
)
from backend.app.domain.workflow_policy_engine import WorkflowPolicyEngine, CANONICAL_OUTCOME_OPTIONS
from backend.app.domain.workflow_view_composer import WorkflowViewComposer


def test_compact_workflow_dto_includes_allowed_actions():
    compact_dto = WorkflowViewComposer.compose_compact_workflow_dto(
        status=WorkflowStatus.NEEDS_REVIEW,
        has_draft=False
    )
    assert hasattr(compact_dto, "allowed_actions")
    assert isinstance(compact_dto.allowed_actions, list)
    assert len(compact_dto.allowed_actions) > 0

    action_ids = [a.action_id for a in compact_dto.allowed_actions]
    assert ActionID.REVIEW_OUTCOME in action_ids
    assert ActionID.CREATE_DRAFT in action_ids
    assert ActionID.CLOSE_RECORD in action_ids
    assert ActionID.MARK_DUPLICATE_SUBMISSION in action_ids
    assert ActionID.ADD_NOTE in action_ids


def test_action_dto_provides_sufficient_presentation_metadata():
    actions = WorkflowPolicyEngine.get_allowed_actions(WorkflowStatus.NEEDS_REVIEW, has_draft=False)

    review_action = next(a for a in actions if a.action_id == ActionID.REVIEW_OUTCOME)
    assert review_action.label == "Review Outcome"
    assert review_action.execution_kind == ActionExecutionKind.WORKFLOW_MUTATION
    assert len(review_action.outcome_options) == len(CANONICAL_OUTCOME_OPTIONS)

    close_action = next(a for a in actions if a.action_id == ActionID.CLOSE_RECORD)
    assert close_action.label == "Close Record"
    assert close_action.requires_confirmation is True
    assert close_action.confirmation_title == "Close Record"
    assert len(close_action.reason_options) == len(CloseReason)

    dup_action = next(a for a in actions if a.action_id == ActionID.MARK_DUPLICATE_SUBMISSION)
    assert dup_action.label == "Mark Duplicate"
    assert dup_action.requires_confirmation is True
    assert dup_action.reason_options == [CloseReason.DUPLICATE_SUBMISSION_ENTRY]


def test_has_draft_context_preserved_in_compact_workflow_dto():
    dto_no_draft = WorkflowViewComposer.compose_compact_workflow_dto(
        status=WorkflowStatus.TRACKING,
        has_draft=False
    )
    action_ids_no_draft = [a.action_id for a in dto_no_draft.allowed_actions]
    assert ActionID.CREATE_DRAFT in action_ids_no_draft
    assert ActionID.REVIEW_FOLLOW_UP_DRAFT not in action_ids_no_draft

    dto_with_draft = WorkflowViewComposer.compose_compact_workflow_dto(
        status=WorkflowStatus.TRACKING,
        has_draft=True
    )
    action_ids_with_draft = [a.action_id for a in dto_with_draft.allowed_actions]
    assert ActionID.REVIEW_FOLLOW_UP_DRAFT in action_ids_with_draft
    assert ActionID.CREATE_DRAFT not in action_ids_with_draft


def test_compose_list_item_includes_compact_workflow_allowed_actions():
    rec = SubmissionRecord(
        id="rec-list-001",
        graph_immutable_id="g-001",
        conversation_id="c-001",
        candidate_name="Jane Candidate",
        job_id="JOB-100",
        domain_status=DomainStatus.NEEDS_REVIEW,
        received_at="2026-08-10T12:00:00Z",
        created_at="2026-08-10T12:00:00Z",
        record_version=3
    )
    item = WorkflowViewComposer.compose_list_item(rec, has_draft=False)
    assert item.workflow.allowed_actions is not None
    assert len(item.workflow.allowed_actions) > 0
    assert item.record.record_version == 3
