"""
Domain models and enums for Recruitment Follow-Up Agent.
Authoritative domain state contracts.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class DomainStatus(str, Enum):
    NEW_SUBMISSION = "NewSubmission"
    AWAITING_RESPONSE = "AwaitingResponse"
    IN_EVALUATION = "InEvaluation"
    AWAITING_FEEDBACK = "AwaitingFeedback"
    INTERVIEW_REQUEST_SCHEDULED = "InterviewRequestScheduled"
    INTERVIEW_AWAITING_CONFIRMATION = "InterviewAwaitingConfirmation"
    MANAGER_ACTION_REQUIRED = "ManagerActionRequired"
    PENDING_FOLLOW_UP = "PendingFollowUp"
    FEEDBACK_DUE = "FeedbackDue"
    CLIENT_REJECTED = "ClientRejected"
    POSITION_CLOSED = "PositionClosed"
    NEEDS_REVIEW = "NeedsReview"
    CLOSED = "Closed"


class CategoryEnum(str, Enum):
    INTERVIEW_REQUEST_SCHEDULED = "InterviewRequestScheduled"
    POSITION_CLOSED = "PositionClosed"
    REJECTION = "Rejection"
    IN_EVALUATION = "InEvaluation"
    ACKNOWLEDGEMENT = "Acknowledgement"
    FEEDBACK_REQUEST_FOR_INFO = "FeedbackRequestForInfo"
    DUPLICATE_ALREADY_SUBMITTED = "DuplicateAlreadySubmitted"
    NO_RESPONSE = "NoResponse"
    UNRELATED = "Unrelated"
    NEEDS_REVIEW = "NeedsReview"


class InterviewState(str, Enum):
    REQUESTED = "requested"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    RESCHEDULED = "rescheduled"
    CANCELLED = "cancelled"
    NOT_CONFIRMED = "not_confirmed"


class InterviewOutcome(str, Enum):
    """Legacy alias — prefer InterviewState for M3+."""
    PENDING = "pending"
    COMPLETED = "completed"
    RESCHEDULED = "rescheduled"
    CANCELLED = "cancelled"
    NOT_CONFIRMED = "not-confirmed"


class CloseReason(str, Enum):
    POSITION_CLOSED = "Position closed"
    CANDIDATE_WITHDRAWN = "Candidate withdrawn"
    CLIENT_REJECTED = "Client rejected"
    NO_FOLLOW_UP_NEEDED = "No follow-up needed"
    OTHER = "Other"


# --- Shared models ---

class HealthStatus(BaseModel):
    status: str = "ok"
    service: str = "recruitment-follow-up-agent"
    version: str = "1.0.0"


class ConfigStatus(BaseModel):
    status: str = "ready"
    bound_address: str = "127.0.0.1"
    time_zone: str = "America/New_York"
    ollama_model: str = "llama3.2:latest"
    graph_permissions: str = "Mail.Read, Mail.ReadWrite (Mail.Send PROHIBITED)"
    mail_send_prohibited: bool = True
    secrets_redacted: bool = True
    graph_enabled: bool = False
    drafts_enabled: bool = False
    draft_creation_available: bool = False


# --- M2 Domain Models ---

class SourceMessageIdentity(BaseModel):
    graph_immutable_id: str
    conversation_id: str
    internet_message_id: Optional[str] = None


class SubjectMetadata(BaseModel):
    job_id: Optional[str] = None
    ep_reference: Optional[str] = None
    candidate_name: Optional[str] = None
    skill: Optional[str] = None
    customer: Optional[str] = None
    location: Optional[str] = None


class MessageRecipient(BaseModel):
    email: str
    name: Optional[str] = None
    recipient_type: str = "to"  # "to", "cc", "bcc"


class ImportItemSummary(BaseModel):
    graph_immutable_id: str
    conversation_id: str
    subject: str
    received_at: str
    is_eligible: bool
    exclusion_reason: Optional[str] = None
    tcs_recipients: List[str] = []
    co_recipients: List[str] = []
    metadata: SubjectMetadata = Field(default_factory=SubjectMetadata)


class ImportReport(BaseModel):
    import_id: str
    started_at: str
    completed_at: Optional[str] = None
    messages_scanned: int = 0
    messages_eligible: int = 0
    messages_imported: int = 0
    duplicates_skipped: int = 0
    excluded_count: int = 0
    error_count: int = 0
    is_preview: bool = True
    auth_status: str = "ok"  # "ok", "mock", "no_cached_token"
    items: List[ImportItemSummary] = []


class SubmissionRecordHeader(BaseModel):
    id: str
    graph_immutable_id: str
    conversation_id: str
    job_id: Optional[str] = None
    ep_reference: Optional[str] = None
    candidate_name: Optional[str] = None
    tcs_eligibility: str = "eligible"
    domain_status: DomainStatus = DomainStatus.NEW_SUBMISSION
    received_at: str
    created_at: str
    record_version: int = 1
    # Enriched fields for frontend table (additive, backward-compatible)
    latest_logical_timestamp: Optional[str] = None
    latest_logical_author: Optional[str] = None
    logical_message_count: int = 0
    skill: Optional[str] = None
    customer: Optional[str] = None
    location: Optional[str] = None
    thread_message_count: int = 0
    source_content_warning: Optional[str] = None
    # Interview operational fields (read from payload at list time)
    feedback_due_at: Optional[str] = None
    interview_state: Optional[str] = None
    interview_updated_at: Optional[str] = None
    interview_datetime: Optional[str] = None


# --- M3 Domain Models ---

class TimelineEntry(BaseModel):
    entry_id: str
    record_id: str
    sender: str
    timestamp: str
    body_preview: str = ""
    classification: Optional[str] = None
    is_system_note: bool = False
    to_recipients: List[str] = Field(default_factory=list)
    cc_recipients: List[str] = Field(default_factory=list)
    reply_to: Optional[str] = None
    graph_immutable_id: Optional[str] = None
    event_type: Optional[str] = None
    conversation_id: Optional[str] = None
    role: Optional[str] = None  # "original_submission" or "interview_coordination"


class StructuredEvidence(BaseModel):
    category: str
    workflow_status: str
    reason_code: str
    timer_anchor_timestamp: Optional[str] = None
    latest_logical_timestamp: Optional[str] = None
    logical_messages_evaluated: int = 0
    interview_date: Optional[str] = None
    interview_time: Optional[str] = None
    timezone: Optional[str] = None
    timezone_source: Optional[str] = None
    confidence_label: Optional[str] = None
    supporting_message_ids: List[str] = Field(default_factory=list)


class LinkedConversationRole(str, Enum):
    ORIGINAL_SUBMISSION = "original_submission"
    INTERVIEW_COORDINATION = "interview_coordination"


class LinkedConversation(BaseModel):
    conversation_id: str
    role: str = LinkedConversationRole.INTERVIEW_COORDINATION.value
    subject: Optional[str] = None
    received_at: Optional[str] = None
    linked_at: str
    linked_by: str = "tarun@clifyx.com"
    latest_message_excerpt: Optional[str] = None
    latest_message_sender: Optional[str] = None
    thread_messages: List[Dict[str, Any]] = Field(default_factory=list)


class LinkedInterviewSuggestion(BaseModel):
    suggestion_id: str
    record_id: str
    conversation_id: str
    candidate_name: Optional[str] = None
    job_id: Optional[str] = None
    ep_reference: Optional[str] = None
    submission_subject: Optional[str] = None
    submission_received_at: Optional[str] = None
    interview_subject: Optional[str] = None
    interview_received_at: Optional[str] = None
    latest_interview_message_excerpt: Optional[str] = None
    latest_interview_message_sender: Optional[str] = None
    thread_messages: List[Dict[str, Any]] = Field(default_factory=list)


class SubmissionRecord(BaseModel):
    """Full record model for record workspace view."""
    id: str
    graph_immutable_id: str
    conversation_id: str
    job_id: Optional[str] = None
    ep_reference: Optional[str] = None
    candidate_name: Optional[str] = None
    skill: Optional[str] = None
    customer: Optional[str] = None
    location: Optional[str] = None
    tcs_eligibility: str = "eligible"
    domain_status: DomainStatus = DomainStatus.NEW_SUBMISSION
    received_at: str
    created_at: str
    record_version: int = 1
    interview_state: Optional[InterviewState] = None
    interview_datetime: Optional[str] = None
    interview_date: Optional[str] = None
    interview_time: Optional[str] = None
    interview_timezone: Optional[str] = None
    timezone_source: Optional[str] = None
    confidence_label: Optional[str] = None
    interview_updated_at: Optional[str] = None
    feedback_due_at: Optional[str] = None
    manager_notes: str = ""
    system_notes: str = ""
    close_reason: Optional[str] = None
    close_note: Optional[str] = None
    closed_at: Optional[str] = None
    latest_update: Optional[str] = None
    latest_sender: Optional[str] = None
    latest_logical_timestamp: Optional[str] = None
    latest_logical_author: Optional[str] = None
    logical_message_count: int = 0
    timeline: List[TimelineEntry] = []
    # --- Linked Conversations & Suggestions ---
    linked_conversations: List[LinkedConversation] = []
    interview_suggestions: List[LinkedInterviewSuggestion] = []
    # --- Evidence ---
    structured_evidence: Optional[StructuredEvidence] = None
    # --- M6 Retention Fields ---
    is_operational_record_only: bool = False
    retention_expired: bool = False
    expires_at: Optional[str] = None
    latest_real_message_at: Optional[str] = None
    attachment_count: int = 0
    attachment_hashes: List[str] = Field(default_factory=list)
    storage_size_bytes: int = 0
    source_content_warning: Optional[str] = None


class CloseAction(BaseModel):
    reason: CloseReason
    note: Optional[str] = None  # Required when reason is OTHER


class InterviewStateUpdate(BaseModel):
    state: InterviewState
    timestamp: Optional[str] = None


class DashboardSummary(BaseModel):
    awaiting_response: int = 0
    pending_follow_up: int = 0
    interview_awaiting_confirmation: int = 0
    interview_request_scheduled: int = 0
    awaiting_feedback: int = 0
    feedback_due: int = 0
    manager_action_required: int = 0
    in_evaluation: int = 0
    needs_review: int = 0
    incomplete: int = 0
    complete_records: int = 87
    closed: int = 0
    total: int = 0
    auth_status: str = "synthetic_test_data"
    records: List[SubmissionRecordHeader] = []


# --- Manager Local Action Models ---

class BaseManagerActionRequest(BaseModel):
    record_id: str
    graph_immutable_id: str
    conversation_id: str
    record_version: int = 1


class ManagerNoteRequest(BaseManagerActionRequest):
    note_text: str


class FollowUpDecisionRequest(BaseManagerActionRequest):
    decision: str = "Request Follow-up"


class InterviewConfirmationRequest(BaseManagerActionRequest):
    choice: str  # "completed", "rescheduled", "cancelled", "not_confirmed", "scheduled"
    new_date: Optional[str] = None
    new_time: Optional[str] = None
    timezone: Optional[str] = None
    source: Optional[str] = None


class InterviewScheduleRequest(BaseManagerActionRequest):
    """Manager-confirmed future interview schedule. Does not start feedback timing."""
    interview_date: str
    interview_time: str
    timezone: str = "America/New_York"


class ReviewDeferralRequest(BaseManagerActionRequest):
    """Explicit manager pause for a response expected later than the default timer."""
    review_after: str
    reason: str


class OutcomeDecisionRequest(BaseManagerActionRequest):
    outcome_category: str
    notes: Optional[str] = None


class CloseRecordRequest(BaseManagerActionRequest):
    reason: str  # "Position closed", "Candidate withdrawn", "Client rejected", "No follow-up needed", "Other"
    close_note: Optional[str] = None


class ReopenRecordRequest(BaseManagerActionRequest):
    reason: Optional[str] = None


class LinkInterviewConversationRequest(BaseManagerActionRequest):
    linked_conversation_id: str
    interview_subject: Optional[str] = None
    interview_received_at: Optional[str] = None
    thread_messages: List[Dict[str, Any]] = Field(default_factory=list)


class UnlinkInterviewConversationRequest(BaseManagerActionRequest):
    linked_conversation_id: str


# --- M4 Domain Models ---

class ServerStoredAdvisory(BaseModel):
    advisory_id: str
    record_id: str
    conversation_id: str
    graph_immutable_id: Optional[str] = None
    latest_entry_id: Optional[str] = None
    suggested_category: CategoryEnum
    target_domain_status: DomainStatus
    confidence: float
    created_at: str
    expires_at: str
    nonce: str
    consumed: bool = False


class LLMAdvisoryResult(BaseModel):
    advisory_id: Optional[str] = None
    category: CategoryEnum = CategoryEnum.NEEDS_REVIEW
    confidence: float = 0.0
    summary: str = ""
    evidence_entry_ids: List[str] = Field(default_factory=list)
    sanitized_evidence: List[str] = Field(default_factory=list)
    is_uncertain: bool = True
    reasoning: str = ""
    advisory_label: str = "Advisory"


class ReplySuggestionResult(BaseModel):
    is_eligible: bool = True
    suggested_text: str = ""
    recipient: str = "Recipients will be determined from the Outlook Reply All conversation."
    reasoning: str = ""
    eligibility_reason: Optional[str] = None
    advisory_label: str = "Advisory (Do NOT auto-send)"


class AIPreflightResult(BaseModel):
    is_available: bool = True
    reason: Optional[str] = None
    message: Optional[str] = None


class AdvisoryDecisionRequest(BaseModel):
    advisory_id: Optional[str] = None
    decision: str  # "apply" or "keep_needs_review"
    suggested_category: str = "NeedsReview"


class AdvisoryDecisionResponse(BaseModel):
    record_id: str
    domain_status: str
    audit_event_recorded: bool = True
    message: str = ""


# --- M5 Draft Workflow Models ---

class DraftRecipientPreview(BaseModel):
    record_id: str
    conversation_id: str
    source_message_id: str
    source_message_sender: str
    to: List[str] = Field(default_factory=list)
    cc: List[str] = Field(default_factory=list)
    bcc: List[str] = Field(default_factory=list)
    reply_to: Optional[str] = None
    default_text: str = ""


class DraftApprovalRecord(BaseModel):
    record_id: str
    conversation_id: str
    immutable_anchor_id: str
    manager_identity: str = "tarun@clifyx.com"
    canonical_to: List[str] = Field(default_factory=list)
    canonical_cc: List[str] = Field(default_factory=list)
    normalized_bcc: List[str] = Field(default_factory=list)
    content: str
    approval_hash: str
    approved_at: str
    idempotency_key: str
    is_active: bool = True

class DraftOperationState(str, Enum):
    APPROVED = "APPROVED"
    CREATING = "CREATING"
    RECOVERED_PENDING_FINALIZATION = "RECOVERED_PENDING_FINALIZATION"
    CREATED = "CREATED"
    FAILED_RECONCILABLE = "FAILED_RECONCILABLE"
    SUPERSEDED = "SUPERSEDED"

class DraftOperationRecord(BaseModel):
    idempotency_key: str
    record_id: str
    approval_hash: str
    record_version: int = 1
    state: DraftOperationState
    created_at: str
    updated_at: str
    # This holds conversation_id, anchor_id, to, cc, bcc, body, and potentially real Graph draft_id once created
    payload_data: Dict[str, Any]


class DraftApprovalRequest(BaseModel):
    record_id: str
    content: str
    to: Optional[List[str]] = None
    cc: Optional[List[str]] = None
    bcc: List[str] = Field(default_factory=list)
    conversation_id: Optional[str] = None
    source_message_id: Optional[str] = None
    record_version: int = 1


class DraftApprovalResponse(BaseModel):
    is_approved: bool
    approval_hash: str
    idempotency_key: str
    approved_at: str
    canonical_summary: str


class DraftCreateRequest(BaseModel):
    record_id: str
    content: str
    to: Optional[List[str]] = None
    cc: Optional[List[str]] = None
    bcc: List[str] = Field(default_factory=list)
    approval_hash: str
    idempotency_key: str
    conversation_id: Optional[str] = None
    source_message_id: Optional[str] = None
    record_version: int = 1


class DraftCreationResult(BaseModel):
    draft_id: str
    record_id: str
    conversation_id: str
    source_message_id: str
    status: str = "created"  # "created" or "reconciled_existing"
    message: str = "Draft created—not sent. Review and send in Outlook."
    to: List[str]
    cc: List[str]
    bcc: List[str]
    approval_hash: str
    idempotency_key: str
    created_at: str
    is_synthetic: bool = True
    verified: bool = False
    operation_state: str = "CREATED"


class DraftOperationStatusResponse(BaseModel):
    idempotency_key: str
    record_id: str
    approval_hash: str
    state: DraftOperationState
    can_create: bool = False
    can_reconcile: bool = False
    can_resume: bool = False
    can_reset: bool = False
    verified: bool = False
    message: str


class DraftOperationActionRequest(BaseModel):
    record_id: str
    idempotency_key: str
    approval_hash: str


# --- M6 Retention & Backup Models ---

class ExpiryReviewSummary(BaseModel):
    record_id: str
    candidate_name: Optional[str] = None
    job_id: Optional[str] = None
    ep_reference: Optional[str] = None
    latest_real_message_at: str
    expires_at: str
    message_count: int
    attachment_count: int
    storage_size_bytes: int


class DeletionStats(BaseModel):
    record_count: int
    message_count: int
    attachment_count: int
    bytes_freed: int


class DeletionApprovalRequest(BaseModel):
    record_ids: List[str]
    confirmed_by: str = "tarun@clifyx.com"
    final_confirmation: bool = False


class RetentionAuditEvent(BaseModel):
    audit_id: str
    record_ids: List[str]
    approved_by: str
    timestamp: str
    categories_removed: List[str] = Field(default_factory=list)
    stats: DeletionStats
    verification_result: str = "passed_integrity_check"


class BackupRequest(BaseModel):
    manager_identity: str = "tarun@clifyx.com"


class BackupResult(BaseModel):
    backup_id: str
    created_at: str
    record_count: int
    backup_file_path: str
    key_id: str
    backup_format_version: str = "2.0"
    source_db_sha256: Optional[str] = None
    encrypted_payload_sha256: Optional[str] = None
    schema_version: int = 1
    mac_limitation_notice: str = "Backup master key stored in local macOS Keychain. Restoration on another Mac requires key export."


class RestoreRequest(BaseModel):
    backup_file_path: str
    manager_identity: str = "tarun@clifyx.com"


class RestoreResult(BaseModel):
    restore_id: str
    quarantined_record_count: int
    expired_record_count: int
    requires_retention_action: bool
    status: str  # "quarantined_requires_retention_action" or "promoted_active"
    message: str
    backup_format_version: str = "2.0"
    fidelity_level: str = "full_database_fidelity"
    source_db_sha256: Optional[str] = None

class MessageDirection(str, Enum):
    ORIGINAL_SUBMISSION = "original_submission"
    SENT_MESSAGE = "sent_message"
    INBOUND_MESSAGE = "inbound_message"
    AUTOMATIC_REPLY = "automatic_reply"
    UNKNOWN = "unknown"

class MessageFact(BaseModel):
    graph_immutable_id: Optional[str] = None
    internet_message_id: Optional[str] = None
    duplicate_immutable_ids: List[str] = Field(default_factory=list)
    timestamp: datetime
    sender_email: str
    direction: MessageDirection
    is_meaningful: bool = False
    body_preview: str = ""

class ConversationFacts(BaseModel):
    messages: List[MessageFact] = Field(default_factory=list)
    latest_real_message: Optional[MessageFact] = None
    latest_inbound_message: Optional[MessageFact] = None
    latest_sent_message: Optional[MessageFact] = None
    has_meaningful_inbound_response: bool = False
    requires_classification: bool = False
    timer_anchor_message: Optional[MessageFact] = None
    followup_anchor_requires_review: bool = False
    logical_copy_requires_review: bool = False
    no_response_status: Optional[str] = None
    interview_status: Optional[str] = None
    interview_datetime: Optional[datetime] = None
    outcome_status: Optional[str] = None
    in_evaluation_timer_status: Optional[str] = None
