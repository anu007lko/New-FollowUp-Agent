"""
Workflow View Composer — Pure read-side DTO builder.
Constructs RecordWorkflowDTO, CompactWorkflowDTO, RecordDetailResponse, and RecordListItem
from stored facts and policy engine rules.
NEVER invokes the classifier or modifies database state.
"""

from typing import Dict, Any, Optional, List, Union
from backend.app.domain.models import (
    WorkflowStatus, CloseReason, QueueID, DisplayTone,
    DisplayMetadataDTO, RecordWorkflowDTO, CompactWorkflowDTO,
    SubmissionRecordDTO, RecordDetailResponse, RecordListItem,
    SubmissionRecord, ActionDTO
)
from backend.app.domain.workflow_policy_engine import WorkflowPolicyEngine


# --- Status Normalization ---

LEGACY_STATUS_MAP: Dict[str, WorkflowStatus] = {
    "NeedsReview": WorkflowStatus.NEEDS_REVIEW,
    "NewSubmission": WorkflowStatus.NEEDS_REVIEW,
    "Tracking": WorkflowStatus.TRACKING,
    "AwaitingResponse": WorkflowStatus.TRACKING,
    "InEvaluation": WorkflowStatus.TRACKING,
    "ActionRequired": WorkflowStatus.ACTION_REQUIRED,
    "ManagerActionRequired": WorkflowStatus.ACTION_REQUIRED,
    "PendingFollowUp": WorkflowStatus.ACTION_REQUIRED,
    "InterviewScheduled": WorkflowStatus.INTERVIEW_SCHEDULED,
    "InterviewRequestScheduled": WorkflowStatus.INTERVIEW_SCHEDULED,
    "InterviewAwaitingConfirmation": WorkflowStatus.INTERVIEW_SCHEDULED,
    "FeedbackPending": WorkflowStatus.FEEDBACK_PENDING,
    "AwaitingFeedback": WorkflowStatus.FEEDBACK_PENDING,
    "FeedbackDue": WorkflowStatus.FEEDBACK_DUE,
    "Closed": WorkflowStatus.CLOSED,
}


def normalize_workflow_status(raw: Any) -> WorkflowStatus:
    """Normalizes any persisted status string or enum to canonical WorkflowStatus."""
    if isinstance(raw, WorkflowStatus):
        return raw
    val = str(raw.value if hasattr(raw, 'value') else raw).strip()
    return LEGACY_STATUS_MAP.get(val, WorkflowStatus.NEEDS_REVIEW)


# --- Closed Display Mapping ---

CLOSED_DISPLAY_LABELS: Dict[CloseReason, str] = {
    CloseReason.DUPLICATE_SUBMISSION_ENTRY: "Duplicate Submission",
    CloseReason.CLIENT_REJECTED: "Client Rejected",
    CloseReason.POSITION_CLOSED: "Position Closed",
    CloseReason.CANDIDATE_WITHDRAWN: "Candidate Withdrawn",
    CloseReason.PLACED_JOINED: "Placed / Joined",
    CloseReason.NO_LONGER_AVAILABLE: "No Longer Available",
    CloseReason.NO_FOLLOW_UP_NEEDED: "Closed",
    CloseReason.OTHER: "Closed",
}


def get_display_metadata(status: WorkflowStatus, close_reason: Optional[CloseReason]) -> DisplayMetadataDTO:
    """Computes DisplayMetadataDTO from status and close_reason."""
    if status == WorkflowStatus.CLOSED:
        label = CLOSED_DISPLAY_LABELS.get(close_reason, "Closed") if close_reason else "Closed"
        return DisplayMetadataDTO(
            label=label,
            tone=DisplayTone.CLOSED,
            description="Record is closed"
        )
    elif status == WorkflowStatus.NEEDS_REVIEW:
        return DisplayMetadataDTO(
            label="Needs Review",
            tone=DisplayTone.REVIEW,
            description="Requires manager review"
        )
    elif status == WorkflowStatus.TRACKING:
        return DisplayMetadataDTO(
            label="Tracking",
            tone=DisplayTone.TRACKING,
            description="Active submission under follow-up tracking"
        )
    elif status == WorkflowStatus.ACTION_REQUIRED:
        return DisplayMetadataDTO(
            label="Action Required",
            tone=DisplayTone.ACTION,
            description="Manager intervention needed"
        )
    elif status == WorkflowStatus.INTERVIEW_SCHEDULED:
        return DisplayMetadataDTO(
            label="Interview Scheduled",
            tone=DisplayTone.INTERVIEW,
            description="Interview confirmed in future"
        )
    elif status == WorkflowStatus.FEEDBACK_PENDING:
        return DisplayMetadataDTO(
            label="Feedback Pending",
            tone=DisplayTone.AWAITING,
            description="Interview elapsed; awaiting client response"
        )
    elif status == WorkflowStatus.FEEDBACK_DUE:
        return DisplayMetadataDTO(
            label="Feedback Due",
            tone=DisplayTone.FEEDBACK,
            description="Past 09:00 America/New_York next business morning"
        )
    else:
        return DisplayMetadataDTO(
            label="Needs Review",
            tone=DisplayTone.REVIEW,
            description="Requires manager review"
        )


def get_queue_memberships(status: WorkflowStatus) -> List[QueueID]:
    """Computes queue membership from status."""
    if status == WorkflowStatus.NEEDS_REVIEW:
        return [QueueID.NEEDS_REVIEW]
    elif status == WorkflowStatus.TRACKING:
        return []
    elif status == WorkflowStatus.ACTION_REQUIRED:
        return [QueueID.ACTION_REQUIRED]
    elif status == WorkflowStatus.INTERVIEW_SCHEDULED:
        return [QueueID.INTERVIEWS]
    elif status == WorkflowStatus.FEEDBACK_PENDING:
        return [QueueID.INTERVIEWS, QueueID.FEEDBACK_PENDING]
    elif status == WorkflowStatus.FEEDBACK_DUE:
        return [QueueID.INTERVIEWS, QueueID.FEEDBACK_DUE]
    elif status == WorkflowStatus.CLOSED:
        return [QueueID.CLOSED]
    return []


def get_evidence_category(
    status: WorkflowStatus,
    close_reason: Optional[CloseReason],
    persisted_category: Optional[str]
) -> Optional[str]:
    """Computes evidence_category for DTO output."""
    if status == WorkflowStatus.CLOSED:
        if close_reason in CLOSED_DISPLAY_LABELS:
            return CLOSED_DISPLAY_LABELS[close_reason]
        return "Closed"
    return persisted_category if persisted_category else None


class WorkflowViewComposer:
    """Builds workflow DTOs from record data."""

    @classmethod
    def compose_workflow_dto(
        cls,
        status: WorkflowStatus,
        close_reason: Optional[CloseReason] = None,
        close_note: Optional[str] = None,
        persisted_classification_category: Optional[str] = None,
        has_draft: bool = False
    ) -> RecordWorkflowDTO:
        display = get_display_metadata(status, close_reason)
        queues = get_queue_memberships(status)
        evidence_cat = get_evidence_category(status, close_reason, persisted_classification_category)
        allowed_actions = WorkflowPolicyEngine.get_allowed_actions(status, has_draft=has_draft)

        return RecordWorkflowDTO(
            status=status,
            outcome=close_note if status == WorkflowStatus.CLOSED else None,
            close_reason=close_reason,
            evidence_category=evidence_cat,
            queue_membership=queues,
            display=display,
            allowed_actions=allowed_actions
        )

    @classmethod
    def compose_compact_workflow_dto(
        cls,
        status: WorkflowStatus,
        close_reason: Optional[CloseReason] = None,
        persisted_classification_category: Optional[str] = None,
        has_draft: bool = False
    ) -> CompactWorkflowDTO:
        display = get_display_metadata(status, close_reason)
        queues = get_queue_memberships(status)
        evidence_cat = get_evidence_category(status, close_reason, persisted_classification_category)
        allowed_actions = WorkflowPolicyEngine.get_allowed_actions(status, has_draft=has_draft)

        return CompactWorkflowDTO(
            status=status,
            evidence_category=evidence_cat,
            queue_membership=queues,
            display=display,
            allowed_actions=allowed_actions
        )

    @classmethod
    def compose_submission_record_dto(cls, record: Union[SubmissionRecord, Dict[str, Any]]) -> SubmissionRecordDTO:
        if isinstance(record, SubmissionRecord):
            rec_id = record.id
            cname = record.candidate_name or "Unknown Candidate"
            jid = record.job_id or ""
            jtitle = getattr(record, "job_title", None) or getattr(record, "skill", None)
            unit = getattr(record, "unit", None) or getattr(record, "customer", None)
            loc = record.location
            vendor = getattr(record, "vendor", None)
            rcvd = record.received_at
            closed = record.closed_at
            cr = record.close_reason
            cn = record.close_note
            ver = record.record_version
            tcount = len(record.timeline) if record.timeline else 0
            mcount = getattr(record, "logical_message_count", 0) or 0
        else:
            rec_id = str(record.get("id", ""))
            cname = str(record.get("candidate_name", "Unknown Candidate"))
            jid = str(record.get("job_id", ""))
            jtitle = record.get("job_title") or record.get("skill")
            unit = record.get("unit") or record.get("customer")
            loc = record.get("location")
            vendor = record.get("vendor")
            rcvd = record.get("received_at")
            closed = record.get("closed_at")
            cr = record.get("close_reason")
            cn = record.get("close_note")
            ver = int(record.get("record_version", 1))
            tcount = len(record.get("timeline", []))
            mcount = int(record.get("thread_message_count", 0))

        canonical_cr: Optional[CloseReason] = None
        if cr:
            if isinstance(cr, CloseReason):
                canonical_cr = cr
            else:
                try:
                    from backend.app.domain.models import normalize_close_reason
                    canonical_cr = normalize_close_reason(str(cr))
                except ValueError:
                    canonical_cr = None

        return SubmissionRecordDTO(
            id=rec_id,
            candidate_name=cname,
            job_id=jid,
            job_title=jtitle,
            unit=unit,
            location=loc,
            vendor=vendor,
            received_at=rcvd,
            closed_at=closed,
            close_reason=canonical_cr,
            close_note=cn,
            record_version=ver,
            timeline_count=tcount,
            thread_message_count=mcount
        )

    @classmethod
    def compose_detail(
        cls,
        record: Union[SubmissionRecord, Dict[str, Any]],
        has_draft: bool = False,
        persisted_classification_category: Optional[str] = None
    ) -> RecordDetailResponse:
        record_dto = cls.compose_submission_record_dto(record)

        if isinstance(record, SubmissionRecord):
            raw_status = record.domain_status
            cr = record.close_reason
            cn = record.close_note
            if not persisted_classification_category and record.structured_evidence:
                persisted_classification_category = record.structured_evidence.category
        else:
            raw_status = record.get("domain_status", record.get("workflow_status"))
            cr = record.get("close_reason")
            cn = record.get("close_note")
            if not persisted_classification_category:
                persisted_classification_category = record.get("classification_category")

        status = normalize_workflow_status(raw_status)
        canonical_cr = record_dto.close_reason

        workflow_dto = cls.compose_workflow_dto(
            status=status,
            close_reason=canonical_cr,
            close_note=cn,
            persisted_classification_category=persisted_classification_category,
            has_draft=has_draft
        )

        ep_ref = getattr(record, "ep_reference", None) if isinstance(record, SubmissionRecord) else record.get("ep_reference")
        rcvd = getattr(record, "received_at", None) if isinstance(record, SubmissionRecord) else record.get("received_at")
        clsd = getattr(record, "closed_at", None) if isinstance(record, SubmissionRecord) else record.get("closed_at")
        tline = getattr(record, "timeline", []) if isinstance(record, SubmissionRecord) else record.get("timeline", [])

        return RecordDetailResponse(
            id=record_dto.id,
            candidate_name=record_dto.candidate_name,
            job_id=record_dto.job_id,
            ep_reference=ep_ref,
            domain_status=status.value,
            record_version=record_dto.record_version,
            received_at=rcvd,
            closed_at=clsd,
            timeline=tline or [],
            record=record_dto,
            workflow=workflow_dto
        )

    @classmethod
    def compose_list_item(
        cls,
        record: Union[SubmissionRecord, Dict[str, Any]],
        persisted_classification_category: Optional[str] = None,
        has_draft: bool = False
    ) -> RecordListItem:
        record_dto = cls.compose_submission_record_dto(record)

        if isinstance(record, SubmissionRecord):
            raw_status = record.domain_status
            if not persisted_classification_category and record.structured_evidence:
                persisted_classification_category = record.structured_evidence.category
        else:
            raw_status = record.get("domain_status", record.get("workflow_status"))
            if not persisted_classification_category:
                persisted_classification_category = record.get("classification_category")

        status = normalize_workflow_status(raw_status)
        canonical_cr = record_dto.close_reason

        compact_workflow_dto = cls.compose_compact_workflow_dto(
            status=status,
            close_reason=canonical_cr,
            persisted_classification_category=persisted_classification_category,
            has_draft=has_draft
        )

        ep_ref = getattr(record, "ep_reference", None) if isinstance(record, SubmissionRecord) else record.get("ep_reference")

        return RecordListItem(
            id=record_dto.id,
            candidate_name=record_dto.candidate_name,
            job_id=record_dto.job_id,
            ep_reference=ep_ref,
            domain_status=status.value,
            record=record_dto,
            workflow=compact_workflow_dto
        )
