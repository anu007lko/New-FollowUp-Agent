"""
FastAPI route definitions for Recruitment Follow-Up Agent.
Exposes health, config status, session security, import preview/execution,
daily review, dashboard, records, interview, close/reopen, and notes endpoints.
"""

from typing import List, Optional, Dict
from datetime import datetime, timezone, timedelta
import uuid
import hashlib
from fastapi import APIRouter, Query, HTTPException
from backend.app.domain.models import (
    HealthStatus, ConfigStatus, ImportReport, SubmissionRecordHeader,
    DashboardSummary, SubmissionRecord, CloseAction, InterviewStateUpdate,
    DomainStatus, InterviewState, LLMAdvisoryResult, ReplySuggestionResult,
    DraftRecipientPreview, DraftApprovalRequest, DraftApprovalResponse,
    DraftCreateRequest, DraftCreationResult, ExpiryReviewSummary,
    DeletionApprovalRequest, RetentionAuditEvent, BackupRequest, BackupResult,
    RestoreRequest, RestoreResult, AIPreflightResult, AdvisoryDecisionRequest,
    AdvisoryDecisionResponse, ServerStoredAdvisory, CategoryEnum,
    BaseManagerActionRequest, ManagerNoteRequest, FollowUpDecisionRequest,
    InterviewConfirmationRequest, InterviewScheduleRequest, ReviewDeferralRequest,
    OutcomeDecisionRequest, CloseRecordRequest,
    ReopenRecordRequest, LinkInterviewConversationRequest, UnlinkInterviewConversationRequest,
    DraftOperationStatusResponse, DraftOperationActionRequest
)
from backend.app.domain.date_utils import TIMEZONE_NEW_YORK, TIMEZONE_UTC
from backend.app.application.services import ConfigService, SecurityService
from backend.app.application.import_service import ImportService
from backend.app.application.daily_review_engine import DailyReviewEngine
from backend.app.application.workflow_engine import (
    validate_interview_transition, compute_domain_status_after_interview,
    compute_feedback_due_at, validate_close_action, append_manager_note,
    format_system_note, TIMER_STARTING_STATES, check_suggestion_eligibility,
    select_reply_anchor_message, select_record_reply_context, compute_reply_all_recipients,
    validate_bcc_list, compute_draft_approval_hash, validate_draft_operation_match,
    create_and_store_approval, get_draft_operation, invalidate_server_approval,
    build_professional_followup_draft, derive_interview_draft_context
)
from backend.app.domain.models import DraftOperationState
from backend.app.infrastructure.live_graph_draft_adapter import LiveGraphDraftAdapter
from backend.app.application.retention_engine import (
    get_expiry_review_list, execute_approved_deletion, get_retention_audit_log
)
from backend.app.application.backup_engine import (
    create_encrypted_backup, restore_backup_to_quarantine
)
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.infrastructure.synthetic_data import (
    get_synthetic_dashboard_summary, get_synthetic_record_by_id,
    get_synthetic_records
)
from backend.app.infrastructure.ollama_client import OllamaAdvisoryClient
from backend.app.infrastructure.fake_graph_adapter import FakeGraphDraftAdapter
from backend.app.infrastructure.live_graph_draft_adapter import LiveGraphDraftAdapter
import os
import logging as _logging
_routes_logger = _logging.getLogger("routes")

router = APIRouter()
config_service = ConfigService()
security_service = SecurityService()
import_service = ImportService()
daily_review_engine = DailyReviewEngine()
persistence = EncryptedPersistenceEngine()
ollama_client = OllamaAdvisoryClient()
fake_graph_draft_adapter = None
try:
    fake_graph_draft_adapter = FakeGraphDraftAdapter()
except RuntimeError:
    pass
live_graph_draft_adapter = LiveGraphDraftAdapter()


def _require_live_draft_capability() -> None:
    if os.environ.get("MAIL_SEND_ENABLED", "False").lower() == "true":
        raise HTTPException(status_code=503, detail="Draft capability failed closed because email sending is enabled")
    if os.environ.get("GRAPH_ENABLED", "False").lower() != "true" or os.environ.get("DRAFTS_ENABLED", "False").lower() != "true":
        raise HTTPException(status_code=503, detail="Microsoft Graph draft capability is disabled")


def _use_synthetic() -> bool:
    """Return True only when explicitly opted-in via USE_SYNTHETIC_DATA env var."""
    return os.environ.get("USE_SYNTHETIC_DATA", "False").lower() in ("true", "1", "yes")


def _get_record(record_id: str):
    """Fetch record from authoritative DB or synthetic fixture. Fail closed on error."""
    if _use_synthetic():
        return get_synthetic_record_by_id(record_id)
    try:
        return persistence.get_record_by_id(record_id)
    except Exception as e:
        _routes_logger.error("Authoritative DB access failed (fail-closed)")
        raise HTTPException(status_code=500, detail="Authoritative database unavailable — fail closed")


def _get_dashboard():
    """Fetch dashboard from authoritative DB or synthetic fixture. Fail closed on error."""
    if _use_synthetic():
        return get_synthetic_dashboard_summary()
    try:
        return persistence.get_dashboard_summary()
    except Exception as e:
        _routes_logger.error("Authoritative DB dashboard failed (fail-closed)")
        raise HTTPException(status_code=500, detail="Authoritative database unavailable — fail closed")


def _get_all_records():
    """Fetch all full records from authoritative DB or synthetic fixture. Fail closed on error."""
    if _use_synthetic():
        return get_synthetic_records()
    try:
        headers = persistence.list_records()
        records = []
        for h in headers:
            rec = persistence.get_record_by_id(h.id)
            if rec:
                records.append(rec)
        return records
    except Exception as e:
        _routes_logger.error("Authoritative DB record list failed (fail-closed)")
        raise HTTPException(status_code=500, detail="Authoritative database unavailable — fail closed")


@router.get("/health", response_model=HealthStatus, tags=["Diagnostic"])
@router.get("/api/v1/health", response_model=HealthStatus, tags=["Diagnostic"])
def get_health():
    """Minimal liveness health check."""
    return config_service.get_health_status()


@router.get("/config/status", response_model=ConfigStatus, tags=["Diagnostic"])
@router.get("/api/v1/config/status", response_model=ConfigStatus, tags=["Diagnostic"])
def get_config_status():
    """Redacted readiness and permission configuration status."""
    return config_service.get_config_status()


@router.post("/api/v1/session/csrf-token", tags=["Security"])
def obtain_csrf_token():
    """Obtain a valid CSRF token for local mutating requests."""
    token = security_service.generate_csrf_token()
    return {"csrf_token": token, "type": "Bearer"}


@router.post("/api/v1/imports/submissions/preview", response_model=ImportReport, tags=["Import"])
def preview_manual_import():
    """
    Manager-triggered read-only import dry-run preview.
    Returns preview counts and exclusions without writing domain records.
    """
    return import_service.run_import(preview=True)


@router.post("/api/v1/imports/submissions", response_model=ImportReport, tags=["Import"])
def execute_manual_import(dry_run: bool = Query(False, description="If true, execute read-only preview")):
    """
    Manager-triggered manual import from Submissions folder starting July 10, 2026.
    Idempotent write operation.
    """
    return import_service.run_import(preview=dry_run)


@router.post("/api/v1/daily-review/run", tags=["Daily Review"])
def run_daily_review():
    """
    Trigger Daily Review Now.
    Imports new eligible submissions and reviews active exact conversations across all mailbox folders.
    Enforces overlap prevention.
    """
    result = daily_review_engine.run_daily_review(is_catchup=False)
    return result.to_dict()


@router.get("/api/v1/daily-review/status", tags=["Daily Review"])
def get_daily_review_status():
    """Check status of Daily Review Engine with next scheduled run."""
    now_ny = datetime.now(TIMEZONE_NEW_YORK)
    next_run = now_ny.replace(hour=8, minute=0, second=0, microsecond=0)
    if now_ny >= next_run:
        from datetime import timedelta
        next_run = next_run + timedelta(days=1)

    return {
        "is_running": daily_review_engine.is_running(),
        "scheduler_active": daily_review_engine.is_scheduler_active(),
        "schedule": "8:00 AM America/New_York daily",
        "last_review_at": daily_review_engine._get_last_review_timestamp(),
        "next_run_at": daily_review_engine.next_scheduled_run(now_ny).isoformat(),
        "auth_status": "authoritative_encrypted_database" if not _use_synthetic() else "synthetic_test_data"
    }


@router.get("/api/v1/records", response_model=List[SubmissionRecordHeader], tags=["Records"])
def list_records():
    """List operational submission records headers."""
    return persistence.list_records()


# --- M3 Dashboard & Record Endpoints ---

@router.get("/api/v1/dashboard", response_model=DashboardSummary, tags=["Dashboard"])
def get_dashboard():
    """
    Dashboard action queue summary.
    Returns counts per status bucket and record headers.
    Uses synthetic test data when Graph auth is unavailable.
    """
    return _get_dashboard()


@router.get("/api/v1/records/{record_id}", response_model=SubmissionRecord, tags=["Records"])
def get_record_by_id(record_id: str):
    """
    Fetch a single record by ID. Fail-closed: returns 500 if database or decryption unavailable.
    Never exposes raw graph_immutable_id or conversation_id in public payloads.
    """
    record = _get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record





# --- M4 LLM Advisory Endpoints ---

@router.get("/api/v1/ai/preflight", response_model=AIPreflightResult, tags=["Advisory LLM"])
def get_ai_preflight():
    """Check local resource preflight before enabling AI analysis in UI."""
    return ollama_client.check_preflight()


# In-memory registry for server-stored AI advisories
_advisory_registry: Dict[str, ServerStoredAdvisory] = {}


def _parse_iso_datetime(dt_str: str) -> datetime:
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


@router.post("/api/v1/records/{record_id}/analyze", response_model=LLMAdvisoryResult, tags=["Advisory LLM"])
def analyze_record(record_id: str):
    """
    Manager-triggered local Ollama AI advisory analysis (llama3.2:latest).
    Categorizes conversation, extracts evidence IDs, provides summary.
    Stores server-authoritative advisory token with 15-minute expiration.
    Does NOT modify deterministic record status or trigger actions.
    Output is strictly ADVISORY.
    """
    record = _get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    result = ollama_client.analyze_conversation(
        timeline=record.timeline,
        candidate_name=record.candidate_name,
        job_id=record.job_id
    )

    # Map category to server-authoritative target status (NO AUTO-CLOSE, ALWAYS REVIEW/ACTION)
    cat = result.category
    if cat in (CategoryEnum.POSITION_CLOSED, CategoryEnum.REJECTION, CategoryEnum.INTERVIEW_REQUEST_SCHEDULED):
        target_status = DomainStatus.MANAGER_ACTION_REQUIRED
    elif cat in (CategoryEnum.IN_EVALUATION, CategoryEnum.ACKNOWLEDGEMENT):
        target_status = DomainStatus.IN_EVALUATION
    elif cat == CategoryEnum.NO_RESPONSE:
        target_status = DomainStatus.PENDING_FOLLOW_UP
    else:
        target_status = DomainStatus.NEEDS_REVIEW

    latest_entry_id = record.timeline[-1].entry_id if record.timeline else None
    nonce = uuid.uuid4().hex
    advisory_id = f"adv_{hashlib.sha256((record.id + record.conversation_id + nonce).encode()).hexdigest()[:16]}"
    now_dt = datetime.now(timezone.utc)
    expires_dt = now_dt + timedelta(minutes=15)

    server_advisory = ServerStoredAdvisory(
        advisory_id=advisory_id,
        record_id=record.id,
        conversation_id=record.conversation_id,
        graph_immutable_id=record.graph_immutable_id,
        latest_entry_id=latest_entry_id,
        suggested_category=cat,
        target_domain_status=target_status,
        confidence=result.confidence,
        created_at=now_dt.isoformat(),
        expires_at=expires_dt.isoformat(),
        nonce=nonce,
        consumed=False
    )
    _advisory_registry[advisory_id] = server_advisory

    # Build sanitized evidence descriptions hiding raw Graph IDs
    sanitized_evidence: List[str] = []
    if record.timeline:
        for idx, entry in enumerate(record.timeline, 1):
            if entry.entry_id in result.evidence_entry_ids:
                sender_desc = "Inbound message" if "clifyx" not in entry.sender.lower() else "Outbound message"
                ts_desc = entry.timestamp.split("T")[0] if entry.timestamp else "N/A"
                sanitized_evidence.append(f"{sender_desc} from {entry.sender} ({ts_desc})")

    result.advisory_id = advisory_id
    result.sanitized_evidence = sanitized_evidence
    return result


@router.post("/api/v1/records/{record_id}/advisory-decision", response_model=AdvisoryDecisionResponse, tags=["Advisory LLM"])
def apply_advisory_decision(record_id: str, request: AdvisoryDecisionRequest):
    """
    Record manager approval or rejection of AI advisory suggestion.
    Requires valid server-stored advisory token.
    Rejects forged, expired, replayed, cross-record, or stale advisories.
    Applies safe status transitions without auto-sending or auto-closing.
    """
    record = _get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    adv_id = request.advisory_id
    if not adv_id or adv_id not in _advisory_registry:
        raise HTTPException(
            status_code=400,
            detail="Valid server advisory token required. Browser-supplied category parameters are not accepted."
        )

    advisory = _advisory_registry[adv_id]

    # Validate 1: Cross-record reuse check
    if advisory.record_id != record_id:
        raise HTTPException(status_code=400, detail="Advisory token does not match target record (cross-record reuse rejected)")

    # Validate 2: Replay attack check
    if advisory.consumed:
        raise HTTPException(status_code=400, detail="Advisory token has already been applied or used (replay attack rejected)")

    # Validate 3: Expiry check (15 minutes)
    now_dt = datetime.now(timezone.utc)
    exp_dt = _parse_iso_datetime(advisory.expires_at)
    if now_dt > exp_dt:
        raise HTTPException(status_code=400, detail="Advisory token has expired (15-minute window exceeded). Re-analysis required.")

    # Validate 4: Exact conversationId match
    if record.conversation_id != advisory.conversation_id:
        raise HTTPException(status_code=400, detail="Conversation identity mismatch against stored advisory token")

    # Validate 5: Stale timeline anchor / newer message invalidation
    current_latest_entry_id = record.timeline[-1].entry_id if record.timeline else None
    if current_latest_entry_id != advisory.latest_entry_id:
        advisory.consumed = True
        raise HTTPException(
            status_code=400,
            detail="Timeline has changed since analysis. Stale advisory token invalidated. Re-analysis required."
        )

    # Mark advisory as consumed to prevent replay
    advisory.consumed = True

    if request.decision == "apply":
        # APPLY SERVER-AUTHORITATIVE TARGET STATUS ONLY! (Ignore client-supplied suggested_category)
        new_status = advisory.target_domain_status
        record.domain_status = new_status
        audit_msg = (
            f"[AUDIT] Manager accepted server-verified AI advisory (Token: {adv_id}, "
            f"Category: {advisory.suggested_category.value}). Status set to {new_status.value}. "
            f"No auto-send or auto-close performed."
        )
        record.system_notes = append_manager_note(record.system_notes, audit_msg)
        return AdvisoryDecisionResponse(
            record_id=record_id,
            domain_status=new_status.value,
            audit_event_recorded=True,
            message="Manager accepted verified AI suggestion. Status updated safely without sending or auto-closing."
        )
    else:
        audit_msg = f"[AUDIT] Manager rejected server-verified AI advisory (Token: {adv_id}). Record retained in NeedsReview."
        record.system_notes = append_manager_note(record.system_notes, audit_msg)
        record.domain_status = DomainStatus.NEEDS_REVIEW
        return AdvisoryDecisionResponse(
            record_id=record_id,
            domain_status=DomainStatus.NEEDS_REVIEW.value,
            audit_event_recorded=True,
            message="Manager retained record in NeedsReview. Decision audited."
        )


@router.post("/api/v1/records/{record_id}/suggest-reply", response_model=ReplySuggestionResult, tags=["Advisory LLM"])
def suggest_reply(record_id: str):
    """
    Manager-triggered reply draft text suggestion using local Ollama.
    
    SAFETY & INVARIANTS:
    1. Deterministic rules decide eligibility — LLM cannot override eligibility.
    2. Awaiting Feedback is NOT eligible while timer has time remaining.
    3. Feedback Due enables post-interview follow-up suggestion.
    4. Recipients are NOT determined by LLM — displayed as Outlook Reply All notice.
    5. Does NOT create an Outlook draft or send emails.
    6. Output is strictly ADVISORY.
    """
    record = _get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    is_eligible, reason = check_suggestion_eligibility(
        domain_status=record.domain_status,
        feedback_due_at=record.feedback_due_at
    )

    if not is_eligible:
        return ReplySuggestionResult(
            is_eligible=False,
            suggested_text="",
            recipient="Recipients will be determined from the Outlook Reply All conversation.",
            reasoning="Record is not currently eligible for follow-up suggestion.",
            eligibility_reason=reason,
            advisory_label="Advisory (Do NOT auto-send)"
        )

    req_name = record.skill or record.customer or "the position"
    return ollama_client.suggest_reply(
        timeline=record.timeline,
        candidate_name=record.candidate_name,
        requirement_name=req_name,
        status=record.domain_status
    )


# --- M5 Draft Workflow Endpoints ---

@router.get("/api/v1/records/{record_id}/draft-preview", response_model=DraftRecipientPreview, tags=["Draft Workflow"])
def get_draft_preview(record_id: str):
    """
    Get deterministic Reply All recipient preview and anchor metadata from actual conversation.
    
    SAFETY & INVARIANTS:
    1. Selects latest real mailbox message with immutable Graph ID.
    2. Preserves To and CC according to Reply All and replyTo rules.
    3. Excludes tarun@clifyx.com to prevent self-reply.
    4. BCC starts empty.
    5. Never uses Job ID, EP reference, subject, or candidate name as anchor.
    """
    record = _get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    anchor_message, target_conversation_id = select_record_reply_context(record)
    if not anchor_message:
        raise HTTPException(
            status_code=400,
            detail="No valid real mailbox message with an immutable ID was found in this conversation timeline"
        )

    to_list, cc_list, bcc_list, reply_to = compute_reply_all_recipients(anchor_message)
    source_msg_id = anchor_message.graph_immutable_id or record.graph_immutable_id

    interview_datetime, interview_invite_found = derive_interview_draft_context(record)
    default_text = build_professional_followup_draft(
        domain_status=record.domain_status,
        candidate_name=record.candidate_name,
        requirement_name=record.skill or record.customer,
        job_id=record.job_id,
        ep_reference=record.ep_reference,
        interview_datetime=interview_datetime,
        interview_invite_found=interview_invite_found,
    )

    return DraftRecipientPreview(
        record_id=record.id,
        conversation_id=target_conversation_id,
        source_message_id=source_msg_id,
        source_message_sender=anchor_message.sender,
        to=to_list,
        cc=cc_list,
        bcc=bcc_list,
        reply_to=reply_to,
        default_text=default_text
    )


@router.post("/api/v1/records/{record_id}/draft-approve", response_model=DraftApprovalResponse, tags=["Draft Workflow"])
def approve_draft(record_id: str, request: DraftApprovalRequest):
    """
    Stage 1: Manager approves draft content and recipient preview.
    
    SERVER INTEGRITY INVARIANTS:
    1. Server independently selects immutable reply anchor and recomputes canonical Reply All To/CC.
    2. Rejects forged client To/CC, conversation_id, or source_message_id.
    3. Validates all BCC addresses end strictly in @clifyx.com.
    4. Creates and stores a server-side approval record containing bound SHA-256 hash and UUID idempotency key.
    """
    _require_live_draft_capability()
    if record_id != request.record_id:
        raise HTTPException(status_code=400, detail="Mismatched record ID in approval request")

    record = _get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    if not request.content or not request.content.strip():
        raise HTTPException(status_code=400, detail="Draft content cannot be empty")
    if request.record_version != record.record_version:
        raise HTTPException(status_code=409, detail="Record version changed. Refresh the record and review the draft again.")

    # Select server-authoritative reply anchor message
    anchor_message, target_conversation_id = select_record_reply_context(record)
    if not anchor_message:
        raise HTTPException(
            status_code=400,
            detail="No valid real mailbox message with an immutable ID was found in this conversation timeline"
        )

    source_msg_id = anchor_message.graph_immutable_id or record.graph_immutable_id

    # Compute server canonical To and CC
    canonical_to, canonical_cc, _, _ = compute_reply_all_recipients(anchor_message)

    # Reject forged client To/CC if supplied
    if request.to is not None:
        if sorted([t.strip().lower() for t in request.to]) != sorted([t.strip().lower() for t in canonical_to]):
            raise HTTPException(status_code=400, detail="Client-supplied To recipients do not match server-authoritative recipients")

    if request.cc is not None:
        if sorted([c.strip().lower() for c in request.cc]) != sorted([c.strip().lower() for c in canonical_cc]):
            raise HTTPException(status_code=400, detail="Client-supplied CC recipients do not match server-authoritative recipients")

    if request.conversation_id is not None and request.conversation_id != target_conversation_id:
        raise HTTPException(status_code=400, detail="Client-supplied conversation_id does not match server record identity")

    if request.source_message_id is not None and request.source_message_id != source_msg_id:
        raise HTTPException(status_code=400, detail="Client-supplied source_message_id does not match server reply anchor")

    is_valid_bcc, normalized_bcc, bcc_err = validate_bcc_list(request.bcc)
    if not is_valid_bcc:
        raise HTTPException(status_code=400, detail=bcc_err or "Invalid BCC list")

    # Create and store server-side approval record
    op = create_and_store_approval(
        record_id=record.id,
        conversation_id=target_conversation_id,
        immutable_anchor_id=source_msg_id,
        canonical_to=canonical_to,
        canonical_cc=canonical_cc,
        normalized_bcc=normalized_bcc,
        content=request.content,
        record_version=record.record_version,
        engine=persistence
    )

    summary = f"Approved for {len(canonical_to)} To, {len(canonical_cc)} CC, {len(normalized_bcc)} BCC"

    return DraftApprovalResponse(
        is_approved=True,
        approval_hash=op.approval_hash,
        idempotency_key=op.idempotency_key,
        approved_at=op.created_at,
        canonical_summary=summary
    )


@router.post("/api/v1/records/{record_id}/draft-create", response_model=DraftCreationResult, tags=["Draft Workflow"])
def create_draft(record_id: str, request: DraftCreateRequest):
    """
    Stage 2: Manager executes final confirmation to create draft in Outlook via Fake Graph Adapter.
    
    SERVER INTEGRITY INVARIANTS:
    1. Looks up server-side approval record. Fails closed if missing, modified, or invalidated.
    2. Re-evaluates current server-computed reply anchor and canonical recipients.
    3. Rejects forged client To/CC, conversation_id, source_message_id, or idempotency key.
    4. Uses stored server-authoritative idempotency key to prevent duplicate drafts on retry/double-click.
    5. Returns confirmation: 'Draft created—not sent. Review and send in Outlook.'
    """
    _require_live_draft_capability()
    if record_id != request.record_id:
        raise HTTPException(status_code=400, detail="Mismatched record ID in creation request")

    record = _get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if request.record_version != record.record_version:
        raise HTTPException(status_code=409, detail="Record version changed. Refresh and approve again.")

    # Select server-authoritative reply anchor message
    anchor_message, target_conversation_id = select_record_reply_context(record)
    if not anchor_message:
        raise HTTPException(
            status_code=400,
            detail="No valid real mailbox message with an immutable ID was found in this conversation timeline"
        )

    source_msg_id = anchor_message.graph_immutable_id or record.graph_immutable_id
    canonical_to, canonical_cc, _, _ = compute_reply_all_recipients(anchor_message)

    # Reject forged client To/CC if supplied
    if request.to is not None:
        if sorted([t.strip().lower() for t in request.to]) != sorted([t.strip().lower() for t in canonical_to]):
            raise HTTPException(status_code=400, detail="Client-supplied To recipients do not match server-authoritative recipients")

    if request.cc is not None:
        if sorted([c.strip().lower() for c in request.cc]) != sorted([c.strip().lower() for c in canonical_cc]):
            raise HTTPException(status_code=400, detail="Client-supplied CC recipients do not match server-authoritative recipients")

    if request.conversation_id is not None and request.conversation_id != target_conversation_id:
        raise HTTPException(status_code=400, detail="Client-supplied conversation_id does not match server record identity")

    if request.source_message_id is not None and request.source_message_id != source_msg_id:
        raise HTTPException(status_code=400, detail="Client-supplied source_message_id does not match server reply anchor")

    if not request.idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency key required")
        
    op = get_draft_operation(request.idempotency_key, persistence)
    if not op:
        raise HTTPException(status_code=400, detail="Approval record missing or invalid")
        
    # Validate against server-side approval record
    is_valid, validation_err = validate_draft_operation_match(
        op=op,
        current_conversation_id=target_conversation_id,
        current_anchor_id=source_msg_id,
        client_approval_hash=request.approval_hash,
        content=request.content,
        to_list=canonical_to,
        cc_list=canonical_cc,
        bcc_list=request.bcc
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail=validation_err)

    if op.record_version != record.record_version:
        raise HTTPException(status_code=409, detail="Stored approval is stale. Refresh and approve again.")
    if op.state in (DraftOperationState.CREATING, DraftOperationState.FAILED_RECONCILABLE, DraftOperationState.RECOVERED_PENDING_FINALIZATION):
        raise HTTPException(status_code=409, detail=f"Draft operation requires recovery from state {op.state.value}; creation will not be retried")
    if op.state == DraftOperationState.CREATED:
        draft_id = op.payload_data.get("draft_id")
        if not draft_id:
            raise HTTPException(status_code=409, detail="Created operation has no verified draft identity")
        verification_adapter = fake_graph_draft_adapter if fake_graph_draft_adapter is not None else live_graph_draft_adapter
        try:
            verification_adapter.verify_draft(
                draft_id, target_conversation_id, request.content, canonical_to, canonical_cc,
                op.payload_data.get("normalized_bcc", []),
                live_graph_draft_adapter.marker(op.idempotency_key, op.approval_hash),
            )
        except Exception:
            raise HTTPException(status_code=409, detail="Stored draft could not be re-verified in Outlook")
        return DraftCreationResult(
            draft_id=draft_id,
            record_id=record.id,
            conversation_id=target_conversation_id,
            source_message_id=source_msg_id,
            status="reconciled_existing",
            message="Draft created—not sent. Review and send in Outlook.",
            to=canonical_to,
            cc=canonical_cc,
            bcc=op.payload_data.get("normalized_bcc", []),
            approval_hash=op.approval_hash,
            idempotency_key=op.idempotency_key,
            created_at=op.created_at,
            is_synthetic=False, verified=True, operation_state=DraftOperationState.CREATED.value
        )

    if op.state != DraftOperationState.APPROVED:
        raise HTTPException(status_code=409, detail=f"Draft operation cannot create from state {op.state.value}")
    creating_payload = dict(op.payload_data)
    creating_payload["creation_started_at"] = datetime.now(timezone.utc).isoformat()
    if not persistence.compare_and_set_draft_operation(
        op.idempotency_key, [DraftOperationState.APPROVED], DraftOperationState.CREATING,
        creating_payload,
    ):
        raise HTTPException(status_code=409, detail="Another draft operation request is already in progress")

    def persist_graph_id(draft_id: str) -> None:
        current = persistence.get_draft_operation(op.idempotency_key)
        if not current or current.state != DraftOperationState.CREATING:
            raise RuntimeError("Draft operation state changed before Graph identity persistence")
        payload = dict(current.payload_data)
        payload["draft_id"] = draft_id
        payload["graph_id_persisted_at"] = datetime.now(timezone.utc).isoformat()
        if not persistence.compare_and_set_draft_operation(
            op.idempotency_key, [DraftOperationState.CREATING],
            DraftOperationState.RECOVERED_PENDING_FINALIZATION, payload
        ):
            raise RuntimeError("Graph draft identity could not be persisted atomically")

    try:
        is_test = os.environ.get("ENVIRONMENT", "").lower() == "test"
        if is_test and fake_graph_draft_adapter:
            result, was_new = fake_graph_draft_adapter.create_reply_all_draft(
                record_id=record.id,
                conversation_id=target_conversation_id,
                source_message_id=source_msg_id,
                content=request.content,
                to_recipients=canonical_to,
                cc_recipients=canonical_cc,
                bcc_recipients=op.payload_data["normalized_bcc"],
                approval_hash=op.approval_hash,
                idempotency_key=op.idempotency_key,
                persist_created_id=persist_graph_id,
            )
        else:
            result, was_new = live_graph_draft_adapter.create_reply_all_draft(
                record_id=record.id,
                conversation_id=target_conversation_id,
                source_message_id=source_msg_id,
                content=request.content,
                to_recipients=canonical_to,
                cc_recipients=canonical_cc,
                bcc_recipients=op.payload_data["normalized_bcc"],
                approval_hash=op.approval_hash,
                idempotency_key=op.idempotency_key,
                persist_created_id=persist_graph_id,
            )
        latest = persistence.get_draft_operation(op.idempotency_key)
        if not latest or not persistence.compare_and_set_draft_operation(
            op.idempotency_key, [DraftOperationState.RECOVERED_PENDING_FINALIZATION],
            DraftOperationState.CREATED, latest.payload_data if latest else None
        ):
            raise RuntimeError("Verified draft could not be finalized locally")
        result.verified = True
        result.operation_state = DraftOperationState.CREATED.value
        return result
    except HTTPException:
        raise
    except Exception:
        latest = persistence.get_draft_operation(op.idempotency_key)
        if latest and latest.state == DraftOperationState.CREATING:
            persistence.compare_and_set_draft_operation(
                op.idempotency_key, [DraftOperationState.CREATING], DraftOperationState.FAILED_RECONCILABLE
            )
        raise HTTPException(status_code=502, detail="Draft outcome is uncertain. Use Reconcile; creation will not be retried.")


def _draft_status(op) -> DraftOperationStatusResponse:
    state = op.state
    return DraftOperationStatusResponse(
        idempotency_key=op.idempotency_key, record_id=op.record_id,
        approval_hash=op.approval_hash, state=state,
        can_create=state == DraftOperationState.APPROVED,
        can_reconcile=state in (DraftOperationState.CREATING, DraftOperationState.FAILED_RECONCILABLE),
        can_resume=state == DraftOperationState.RECOVERED_PENDING_FINALIZATION,
        can_reset=state == DraftOperationState.FAILED_RECONCILABLE and op.payload_data.get("last_reconciliation_count") == 0,
        verified=state == DraftOperationState.CREATED,
        message={
            DraftOperationState.APPROVED: "Approved and ready to create.",
            DraftOperationState.CREATING: "Creation outcome is uncertain. Reconcile before any further action.",
            DraftOperationState.RECOVERED_PENDING_FINALIZATION: "A matching Outlook draft was recovered. Resume finalization explicitly.",
            DraftOperationState.CREATED: "Draft is verified in Outlook.",
            DraftOperationState.FAILED_RECONCILABLE: "Reconciliation needs manager review.",
            DraftOperationState.SUPERSEDED: "This approval was superseded; create a fresh approval.",
        }[state],
    )


@router.get("/api/v1/records/{record_id}/draft-status/{idempotency_key}", response_model=DraftOperationStatusResponse, tags=["Draft Workflow"])
def get_draft_status(record_id: str, idempotency_key: str):
    op = persistence.get_draft_operation(idempotency_key)
    if not op or op.record_id != record_id:
        raise HTTPException(status_code=404, detail="Draft operation not found")
    return _draft_status(op)


@router.get("/api/v1/records/{record_id}/draft-status", response_model=DraftOperationStatusResponse, tags=["Draft Workflow"])
def get_latest_draft_status(record_id: str):
    op = persistence.get_latest_draft_operation_for_record(record_id)
    if not op:
        raise HTTPException(status_code=404, detail="Draft operation not found")
    return _draft_status(op)


@router.post("/api/v1/records/{record_id}/draft-reconcile", response_model=DraftOperationStatusResponse, tags=["Draft Workflow"])
def reconcile_draft(record_id: str, request: DraftOperationActionRequest):
    _require_live_draft_capability()
    op = persistence.get_draft_operation(request.idempotency_key)
    if not op or op.record_id != record_id or request.record_id != record_id or op.approval_hash != request.approval_hash:
        raise HTTPException(status_code=400, detail="Draft operation binding is invalid")
    if op.state not in (DraftOperationState.CREATING, DraftOperationState.FAILED_RECONCILABLE):
        raise HTTPException(status_code=409, detail=f"Reconciliation is not allowed from state {op.state.value}")
    started_at = op.payload_data.get("creation_started_at")
    if not started_at:
        raise HTTPException(status_code=409, detail="Creation start evidence is missing; automatic reconciliation is unsafe")
    candidates = live_graph_draft_adapter.find_reconciliation_candidates(op.payload_data["conversation_id"], started_at)
    payload = dict(op.payload_data)
    payload["last_reconciliation_count"] = len(candidates)
    payload["last_reconciled_at"] = datetime.now(timezone.utc).isoformat()
    payload["reconciliation_attempts"] = int(payload.get("reconciliation_attempts", 0)) + 1
    if len(candidates) == 1:
        payload["draft_id"] = candidates[0]
        persistence.compare_and_set_draft_operation(
            op.idempotency_key, [op.state], DraftOperationState.RECOVERED_PENDING_FINALIZATION, payload
        )
    else:
        persistence.compare_and_set_draft_operation(
            op.idempotency_key, [op.state], DraftOperationState.FAILED_RECONCILABLE, payload
        )
    return _draft_status(persistence.get_draft_operation(op.idempotency_key))


@router.post("/api/v1/records/{record_id}/draft-resume", response_model=DraftCreationResult, tags=["Draft Workflow"])
def resume_draft(record_id: str, request: DraftOperationActionRequest):
    _require_live_draft_capability()
    record = _get_record(record_id)
    op = persistence.get_draft_operation(request.idempotency_key)
    if not record or not op or op.record_id != record_id or request.record_id != record_id or op.approval_hash != request.approval_hash:
        raise HTTPException(status_code=400, detail="Draft operation binding is invalid")
    if op.state != DraftOperationState.RECOVERED_PENDING_FINALIZATION or not op.payload_data.get("draft_id"):
        raise HTTPException(status_code=409, detail="Draft is not ready for explicit finalization")
    if op.record_version != record.record_version:
        raise HTTPException(status_code=409, detail="Record changed after approval; this draft cannot be finalized")
    data = op.payload_data
    try:
        live_graph_draft_adapter.finalize_existing(
            data["draft_id"], data["conversation_id"], data["content"], data["canonical_to"],
            data["canonical_cc"], data["normalized_bcc"], op.approval_hash, op.idempotency_key
        )
    except Exception:
        raise HTTPException(status_code=502, detail="Recovered draft could not be verified; no email was sent")
    if not persistence.compare_and_set_draft_operation(
        op.idempotency_key, [DraftOperationState.RECOVERED_PENDING_FINALIZATION], DraftOperationState.CREATED, data
    ):
        raise HTTPException(status_code=409, detail="Draft operation changed while finalizing")
    return DraftCreationResult(
        draft_id=data["draft_id"], record_id=record_id, conversation_id=data["conversation_id"],
        source_message_id=data["immutable_anchor_id"], status="reconciled_existing",
        message="Draft created—not sent. Review and send in Outlook.", to=data["canonical_to"],
        cc=data["canonical_cc"], bcc=data["normalized_bcc"], approval_hash=op.approval_hash,
        idempotency_key=op.idempotency_key, created_at=op.created_at, is_synthetic=False,
        verified=True, operation_state=DraftOperationState.CREATED.value,
    )


@router.post("/api/v1/records/{record_id}/draft-reset", response_model=DraftOperationStatusResponse, tags=["Draft Workflow"])
def reset_draft(record_id: str, request: DraftOperationActionRequest):
    op = persistence.get_draft_operation(request.idempotency_key)
    if not op or op.record_id != record_id or request.record_id != record_id or op.approval_hash != request.approval_hash:
        raise HTTPException(status_code=400, detail="Draft operation binding is invalid")
    if op.state != DraftOperationState.FAILED_RECONCILABLE or op.payload_data.get("last_reconciliation_count") != 0:
        raise HTTPException(status_code=409, detail="Reset requires a fresh reconciliation proving zero matching Outlook drafts")
    if not persistence.compare_and_set_draft_operation(
        op.idempotency_key, [DraftOperationState.FAILED_RECONCILABLE], DraftOperationState.SUPERSEDED
    ):
        raise HTTPException(status_code=409, detail="Draft operation changed while resetting")
    return _draft_status(persistence.get_draft_operation(op.idempotency_key))


# --- M6 Retention & Backup Endpoints ---

@router.get("/api/v1/retention/expiry-review", response_model=List[ExpiryReviewSummary], tags=["Retention & Operations"])
def get_retention_expiry_review():
    """
    Get list of expired records ready for manager retention review.
    PRIVACY GUARANTEE: Returns metadata, dates, message/attachment counts, and storage size ONLY.
    Never includes expired message bodies or attachment contents.
    """
    records = _get_all_records()
    return get_expiry_review_list(records)


@router.post("/api/v1/retention/delete-approved", response_model=RetentionAuditEvent, tags=["Retention & Operations"])
def post_approved_retention_deletion(request: DeletionApprovalRequest):
    """
    Execute manager-approved content deletion on selected expired records.
    Requires request.final_confirmation == True.
    Deletes message bodies, content headers, attachment bytes, extracted text, and raw LLM outputs.
    Transforms record state to Operational Record Only.
    """
    if not request.final_confirmation:
        raise HTTPException(status_code=400, detail="Deletion rejected: final_confirmation must be explicitly True.")
    
    records = _get_all_records()
    updated_records, audit_event = execute_approved_deletion(records, request)
    return audit_event


@router.get("/api/v1/retention/audit-log", response_model=List[RetentionAuditEvent], tags=["Retention & Operations"])
def get_retention_audit_log_endpoint():
    """Retrieve full retention audit log history."""
    return get_retention_audit_log()


@router.post("/api/v1/backup/create", response_model=BackupResult, tags=["Retention & Operations"])
def post_create_encrypted_backup(request: BackupRequest):
    """
    Create a manager-triggered encrypted local backup using Fernet authenticated encryption.
    Keychain protected master key. Contains zero plaintext secrets or tokens.
    """
    if _use_synthetic():
        records = _get_all_records()
        return create_encrypted_backup(records, request.manager_identity)
    return create_encrypted_backup(manager_identity=request.manager_identity)


@router.post("/api/v1/backup/restore", response_model=RestoreResult, tags=["Retention & Operations"])
def post_restore_backup_quarantine(request: RestoreRequest):
    """
    Restore encrypted backup into Quarantine first.
    Identifies expired content and requires manager retention review/deletion before active promotion.
    """
    try:
        result, quarantined_records = restore_backup_to_quarantine(request.backup_file_path, request.manager_identity)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


import os

@router.post("/api/v1/synthetic/reset", tags=["Synthetic Data"])
def reset_synthetic_data_endpoint():
    """Reset synthetic in-memory records cache for clean UI testing. Disabled in release mode."""
    env_mode = os.getenv("ENVIRONMENT", "production").lower()
    allow_reset = os.getenv("ALLOW_SYNTHETIC_RESET", "false").lower()
    if env_mode != "test" or allow_reset != "true":
        raise HTTPException(status_code=403, detail="Synthetic data reset endpoint is disabled in production release mode.")
    
    from backend.app.infrastructure.synthetic_data import reset_synthetic_records_cache
    reset_synthetic_records_cache()
    return {"status": "reset", "message": "Synthetic records cache reset to initial state"}


# --- Manager Local Action Endpoints ---


from fastapi import Depends

def get_trusted_manager_identity() -> str:
    # In a real system, extract from session/JWT.
    return "tarun@clifyx.com"

def _validate_and_get_record_payload(record_id: str, req: BaseManagerActionRequest) -> Tuple[SubmissionRecord, Dict[str, Any]]:
    if req.record_id != record_id:
        raise HTTPException(status_code=400, detail="Record ID mismatch between path and request body.")
    
    rec = _get_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found.")

    if rec.graph_immutable_id != req.graph_immutable_id:
        raise HTTPException(status_code=400, detail="Graph immutable ID binding mismatch.")

    if rec.conversation_id != req.conversation_id:
        raise HTTPException(status_code=400, detail="Conversation ID binding mismatch.")

    if req.record_version != rec.record_version:
        raise HTTPException(status_code=409, detail="Record version token is stale or mismatched.")

    if not rec.timeline or len(rec.timeline) == 0:
        raise HTTPException(status_code=400, detail="This record is incomplete and cannot be actioned until its conversation is recovered.")

    with persistence._get_connection() as conn:
        cursor = conn.execute("SELECT payload_ciphertext FROM submission_records WHERE id = ?", (record_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Raw record payload not found.")
        payload = persistence._decrypt_payload(row["payload_ciphertext"])

    return rec, payload


@router.post("/api/v1/records/{record_id}/notes", response_model=SubmissionRecord, tags=["Manager Actions"])
def post_manager_note(record_id: str, req: ManagerNoteRequest, manager_identity: str = Depends(get_trusted_manager_identity)):
    """Add a local manager note. Notes never reset timers or overwrite message history."""
    if not req.note_text.strip():
        raise HTTPException(status_code=400, detail="Note text cannot be empty.")

    rec, payload = _validate_and_get_record_payload(record_id, req)
    now_iso = datetime.now(TIMEZONE_UTC).isoformat()

    existing_notes = payload.get("manager_notes", "")
    note_line = f"[{now_iso}] ({manager_identity}) {req.note_text.strip()}\n"
    if isinstance(existing_notes, list):
        payload["manager_notes"] = [*existing_notes, note_line.rstrip("\n")]
    else:
        payload["manager_notes"] = f"{existing_notes or ''}{note_line}"

    timeline = payload.get("timeline", [])
    timeline.append({
        "entry_id": f"audit_note_{uuid.uuid4().hex[:8]}",
        "event_type": "MANAGER_NOTE_ADDED",
        "sender": manager_identity,
        "timestamp": now_iso,
        "is_system_note": True,
        "body_preview": f"Manager note added: {req.note_text.strip()[:100]}"
    })
    payload["timeline"] = timeline

    try:
        persistence.update_record_optimistically(record_id, payload, rec.domain_status.value, req.record_version)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _get_record(record_id)


@router.post("/api/v1/records/{record_id}/follow-up-decision", response_model=SubmissionRecord, tags=["Manager Actions"])
def post_followup_decision(record_id: str, req: FollowUpDecisionRequest, manager_identity: str = Depends(get_trusted_manager_identity)):
    """Record manager's local decision to request follow-up. Does NOT call Graph or create drafts."""
    rec, payload = _validate_and_get_record_payload(record_id, req)
    now_iso = datetime.now(TIMEZONE_UTC).isoformat()

    timeline = payload.get("timeline", [])
    timeline.append({
        "entry_id": f"audit_followup_{uuid.uuid4().hex[:8]}",
        "event_type": "MANAGER_FOLLOWUP_DECISION",
        "sender": manager_identity,
        "timestamp": now_iso,
        "is_system_note": True,
        "body_preview": f"Manager recorded decision: {req.decision}"
    })
    payload["timeline"] = timeline

    try:
        persistence.update_record_optimistically(record_id, payload, rec.domain_status.value, req.record_version)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _get_record(record_id)


@router.post("/api/v1/records/{record_id}/interview-confirmation", response_model=SubmissionRecord, tags=["Manager Actions"])
def post_interview_confirmation(record_id: str, req: InterviewConfirmationRequest, manager_identity: str = Depends(get_trusted_manager_identity)):
    """Record manager interview confirmation decision (completed, rescheduled, cancelled, not_confirmed)."""
    valid_choices = {"completed", "rescheduled", "cancelled", "not_confirmed"}
    if req.choice not in valid_choices:
        raise HTTPException(status_code=400, detail=f"Invalid choice '{req.choice}'. Must be one of {valid_choices}")

    rec, payload = _validate_and_get_record_payload(record_id, req)
    now_iso = datetime.now(TIMEZONE_UTC).isoformat()

    target_status = rec.domain_status.value

    if req.choice == "completed":
        payload["interview_state"] = InterviewState.COMPLETED.value
        payload["interview_updated_at"] = now_iso
        due_at = compute_feedback_due_at(now_iso)
        payload["feedback_due_at"] = due_at
        target_status = DomainStatus.AWAITING_FEEDBACK.value
        audit_msg = f"Interview confirmed completed. 48h feedback timer started (due {due_at})."
    elif req.choice == "rescheduled":
        if not req.new_date or not req.new_time:
            raise HTTPException(status_code=400, detail="Rescheduled choice requires new_date and new_time.")
        payload["interview_state"] = InterviewState.RESCHEDULED.value
        payload["interview_updated_at"] = now_iso
        tz = req.timezone or "America/New_York"
        audit_msg = f"Interview rescheduled for {req.new_date} {req.new_time} ({tz})."
    elif req.choice == "cancelled":
        payload["interview_state"] = InterviewState.CANCELLED.value
        payload["interview_updated_at"] = now_iso
        # Cancelled does NOT close record automatically
        target_status = DomainStatus.NEEDS_REVIEW.value
        audit_msg = "Interview marked cancelled by manager. Submission remains open."
    elif req.choice == "not_confirmed":
        payload["interview_state"] = InterviewState.NOT_CONFIRMED.value
        payload["interview_updated_at"] = now_iso
        target_status = DomainStatus.NEEDS_REVIEW.value
        audit_msg = "Interview marked not confirmed by manager. Submission remains open."

    timeline = payload.get("timeline", [])
    timeline.append({
        "entry_id": f"audit_int_{uuid.uuid4().hex[:8]}",
        "event_type": "INTERVIEW_CONFIRMATION_DECISION",
        "sender": manager_identity,
        "timestamp": now_iso,
        "is_system_note": True,
        "body_preview": audit_msg
    })
    payload["timeline"] = timeline

    try:
        persistence.update_record_optimistically(record_id, payload, target_status, req.record_version)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _get_record(record_id)


@router.post("/api/v1/records/{record_id}/interview-schedule", response_model=SubmissionRecord, tags=["Manager Actions"])
def post_interview_schedule(record_id: str, req: InterviewScheduleRequest, manager_identity: str = Depends(get_trusted_manager_identity)):
    """Persist a manager-confirmed future interview date without starting a feedback timer."""
    rec, payload = _validate_and_get_record_payload(record_id, req)
    try:
        scheduled_at = datetime.fromisoformat(f"{req.interview_date}T{req.interview_time}:00")
    except ValueError:
        raise HTTPException(status_code=400, detail="Interview date and time must use YYYY-MM-DD and HH:MM formats.")
    if scheduled_at.tzinfo is None:
        from zoneinfo import ZoneInfo
        scheduled_at = scheduled_at.replace(tzinfo=ZoneInfo(req.timezone))
    if scheduled_at <= datetime.now(scheduled_at.tzinfo):
        raise HTTPException(status_code=400, detail="A confirmed schedule must be in the future; use interview confirmation for a completed interview.")
    now_iso = datetime.now(TIMEZONE_UTC).isoformat()
    payload["interview_state"] = InterviewState.SCHEDULED.value
    payload["interview_datetime"] = scheduled_at.isoformat()
    payload["interview_updated_at"] = now_iso
    payload["feedback_due_at"] = None
    payload["manager_outcome_category"] = "Interview Scheduled"
    payload.setdefault("timeline", []).append({
        "entry_id": f"audit_schedule_{uuid.uuid4().hex[:8]}", "event_type": "INTERVIEW_SCHEDULE_CONFIRMED",
        "sender": manager_identity, "timestamp": now_iso, "is_system_note": True,
        "body_preview": f"Manager confirmed interview schedule: {scheduled_at.isoformat()}."
    })
    try:
        persistence.update_record_optimistically(record_id, payload, DomainStatus.INTERVIEW_REQUEST_SCHEDULED.value, req.record_version)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _get_record(record_id)


@router.post("/api/v1/records/{record_id}/review-deferral", response_model=SubmissionRecord, tags=["Manager Actions"])
def post_review_deferral(record_id: str, req: ReviewDeferralRequest, manager_identity: str = Depends(get_trusted_manager_identity)):
    """Record a manager-approved review deadline that supersedes the default response timer."""
    rec, payload = _validate_and_get_record_payload(record_id, req)
    try:
        review_after = datetime.fromisoformat(req.review_after)
    except ValueError:
        raise HTTPException(status_code=400, detail="review_after must be an ISO-8601 timestamp.")
    if review_after.tzinfo is None:
        review_after = review_after.replace(tzinfo=TIMEZONE_UTC)
    if review_after <= datetime.now(TIMEZONE_UTC):
        raise HTTPException(status_code=400, detail="review_after must be in the future.")
    now_iso = datetime.now(TIMEZONE_UTC).isoformat()
    payload["feedback_due_at"] = review_after.astimezone(TIMEZONE_UTC).isoformat()
    payload["manager_review_deferral"] = {"review_after": payload["feedback_due_at"], "reason": req.reason, "set_at": now_iso}
    payload.setdefault("timeline", []).append({
        "entry_id": f"audit_deferral_{uuid.uuid4().hex[:8]}", "event_type": "MANAGER_REVIEW_DEFERRAL",
        "sender": manager_identity, "timestamp": now_iso, "is_system_note": True,
        "body_preview": f"Manager deferred follow-up review until {payload['feedback_due_at']}: {req.reason}"
    })
    try:
        persistence.update_record_optimistically(record_id, payload, DomainStatus.IN_EVALUATION.value, req.record_version)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _get_record(record_id)


@router.post("/api/v1/records/{record_id}/outcome-decision", response_model=SubmissionRecord, tags=["Manager Actions"])
def post_outcome_decision(record_id: str, req: OutcomeDecisionRequest, manager_identity: str = Depends(get_trusted_manager_identity)):
    """Set manager outcome decision."""
    rec, payload = _validate_and_get_record_payload(record_id, req)
    now_iso = datetime.now(TIMEZONE_UTC).isoformat()

    cat = req.outcome_category.strip()
    status_map = {
        "Position Closed": DomainStatus.MANAGER_ACTION_REQUIRED.value,
        "Rejection": DomainStatus.MANAGER_ACTION_REQUIRED.value,
        "Client Rejected": DomainStatus.MANAGER_ACTION_REQUIRED.value,
        "In Evaluation": DomainStatus.IN_EVALUATION.value,
        "Interview Request": DomainStatus.NEEDS_REVIEW.value,
        "Interview Scheduled": DomainStatus.INTERVIEW_AWAITING_CONFIRMATION.value,
        "Acknowledgement": DomainStatus.NEEDS_REVIEW.value,
        "No Response": DomainStatus.PENDING_FOLLOW_UP.value,
        "Unrelated": DomainStatus.NEEDS_REVIEW.value,
        "Keep in Needs Review": DomainStatus.NEEDS_REVIEW.value,
        "Keep Open": DomainStatus.NEEDS_REVIEW.value,
        "Move to Needs Review": DomainStatus.NEEDS_REVIEW.value,
    }
    target_status = status_map.get(cat, DomainStatus.MANAGER_ACTION_REQUIRED.value)
    payload["manager_outcome_category"] = cat
    payload.pop("closed_at", None)
    payload.pop("close_reason", None)
    payload.pop("close_note", None)

    timeline = payload.get("timeline", [])
    evaluation_due_at = None
    if cat == "In Evaluation":
        for entry in reversed(timeline):
            if not isinstance(entry, dict) or entry.get("is_system_note"):
                continue
            sender = (entry.get("sender") or "").lower()
            if not sender or "@clifyx.com" in sender:
                continue
            try:
                response_at = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                if response_at.tzinfo is None:
                    response_at = response_at.replace(tzinfo=TIMEZONE_UTC)
                evaluation_due = response_at + timedelta(hours=48)
                evaluation_due_at = evaluation_due.isoformat()
                payload["evaluation_response_at"] = response_at.isoformat()
                payload["evaluation_due_at"] = evaluation_due_at
                target_status = DomainStatus.PENDING_FOLLOW_UP.value if datetime.now(TIMEZONE_UTC) >= evaluation_due else DomainStatus.IN_EVALUATION.value
                break
            except (KeyError, TypeError, ValueError):
                continue
    timeline.append({
        "entry_id": f"audit_outcome_{uuid.uuid4().hex[:8]}",
        "event_type": "MANAGER_OUTCOME_DECISION",
        "sender": manager_identity,
        "timestamp": now_iso,
        "is_system_note": True,
        "body_preview": f"Manager set outcome decision: {cat}" + (f" | evaluation due at {evaluation_due_at}" if evaluation_due_at else "")
    })
    payload["timeline"] = timeline

    if req.notes:
        existing_notes = payload.get("manager_notes", "")
        formatted_note = f"[{now_iso}] ({manager_identity}) {req.notes.strip()}"
        if isinstance(existing_notes, list):
            payload["manager_notes"] = [*existing_notes, formatted_note]
        else:
            existing_text = str(existing_notes or "")
            separator = "" if not existing_text or existing_text.endswith("\n") else "\n"
            payload["manager_notes"] = f"{existing_text}{separator}{formatted_note}\n"

    try:
        persistence.update_record_optimistically(record_id, payload, target_status, req.record_version)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _get_record(record_id)


@router.post("/api/v1/records/{record_id}/close", response_model=SubmissionRecord, tags=["Manager Actions"])
def post_close_record(record_id: str, req: CloseRecordRequest, manager_identity: str = Depends(get_trusted_manager_identity)):
    """Close record with required reason and optional/required note."""
    valid_reasons = {"Position closed", "Candidate withdrawn", "Client rejected", "No follow-up needed", "Other"}
    if req.reason not in valid_reasons:
        raise HTTPException(status_code=400, detail=f"Invalid close reason '{req.reason}'. Must be one of {valid_reasons}")

    if req.reason == "Other" and (not req.close_note or not req.close_note.strip()):
        raise HTTPException(status_code=400, detail="Close reason 'Other' requires a close note.")

    rec, payload = _validate_and_get_record_payload(record_id, req)
    now_iso = datetime.now(TIMEZONE_UTC).isoformat()

    payload["close_reason"] = req.reason
    payload["close_note"] = req.close_note.strip() if req.close_note else None
    payload["closed_at"] = now_iso

    timeline = payload.get("timeline", [])
    timeline.append({
        "entry_id": f"audit_close_{uuid.uuid4().hex[:8]}",
        "event_type": "MANAGER_RECORD_CLOSED",
        "sender": manager_identity,
        "timestamp": now_iso,
        "is_system_note": True,
        "body_preview": f"Record closed by manager. Reason: {req.reason}"
    })
    payload["timeline"] = timeline

    try:
        persistence.update_record_optimistically(record_id, payload, DomainStatus.CLOSED.value, req.record_version)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _get_record(record_id)


@router.post("/api/v1/records/{record_id}/reopen", response_model=SubmissionRecord, tags=["Manager Actions"])
def post_reopen_record(record_id: str, req: ReopenRecordRequest, manager_identity: str = Depends(get_trusted_manager_identity)):
    """Reopen a closed record."""
    rec, payload = _validate_and_get_record_payload(record_id, req)
    now_iso = datetime.now(TIMEZONE_UTC).isoformat()

    payload["close_reason"] = None
    payload["close_note"] = None
    payload["closed_at"] = None

    timeline = payload.get("timeline", [])
    timeline.append({
        "entry_id": f"audit_reopen_{uuid.uuid4().hex[:8]}",
        "event_type": "MANAGER_RECORD_REOPENED",
        "sender": manager_identity,
        "timestamp": now_iso,
        "is_system_note": True,
        "body_preview": f"Record reopened by manager. Reason: {req.reason or 'Manager request'}"
    })
    payload["timeline"] = timeline

    try:
        persistence.update_record_optimistically(record_id, payload, DomainStatus.NEEDS_REVIEW.value, req.record_version)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _get_record(record_id)


@router.post("/api/v1/records/{record_id}/link-interview", response_model=SubmissionRecord, tags=["Manager Actions"])
def post_link_interview(record_id: str, req: LinkInterviewConversationRequest, manager_identity: str = Depends(get_trusted_manager_identity)):
    """Link a separate interview conversation to a submission record upon explicit manager confirmation."""
    rec, payload = _validate_and_get_record_payload(record_id, req)
    now_iso = datetime.now(TIMEZONE_UTC).isoformat()

    linked_convs = payload.get("linked_conversations", [])
    suggestions = payload.get("interview_suggestions", [])

    # Check if already linked (idempotent)
    for lc in linked_convs:
        lc_id = lc.get("conversation_id") if isinstance(lc, dict) else getattr(lc, "conversation_id", None)
        if lc_id == req.linked_conversation_id:
            return _get_record(record_id)

    # Find if matching suggestion exists to grab thread_messages/metadata
    thread_msgs = req.thread_messages or []
    subject = req.interview_subject
    received_at = req.interview_received_at

    remaining_suggestions = []
    for s in suggestions:
        s_dict = s if isinstance(s, dict) else s.dict()
        if s_dict.get("conversation_id") == req.linked_conversation_id:
            if not thread_msgs:
                thread_msgs = s_dict.get("thread_messages", [])
            if not subject:
                subject = s_dict.get("interview_subject")
            if not received_at:
                received_at = s_dict.get("interview_received_at")
        else:
            remaining_suggestions.append(s_dict)
    payload["interview_suggestions"] = remaining_suggestions

    new_linked = {
        "conversation_id": req.linked_conversation_id,
        "role": "interview_coordination",
        "subject": subject,
        "received_at": received_at,
        "linked_at": now_iso,
        "linked_by": manager_identity,
        "thread_messages": thread_msgs
    }
    linked_convs.append(new_linked)
    payload["linked_conversations"] = linked_convs

    timeline = payload.get("timeline", [])
    timeline.append({
        "entry_id": f"audit_link_{uuid.uuid4().hex[:8]}",
        "event_type": "MANAGER_LINKED_INTERVIEW_CONVERSATION",
        "sender": manager_identity,
        "timestamp": now_iso,
        "is_system_note": True,
        "body_preview": "Manager confirmed linking interview coordination conversation."
    })
    payload["timeline"] = timeline

    # Reclassify to determine updated domain status
    new_domain_status = rec.domain_status
    try:
        from backend.app.domain.consolidated_classifier import classify_record, PROPOSED_TO_DOMAIN_STATUS
        res = classify_record(
            rec.graph_immutable_id,
            payload.get("thread_messages", []),
            datetime.now(TIMEZONE_UTC),
            timeline=payload.get("timeline", []),
            linked_conversations=payload.get("linked_conversations", [])
        )
        if res.proposed_status in PROPOSED_TO_DOMAIN_STATUS:
            new_domain_status = PROPOSED_TO_DOMAIN_STATUS[res.proposed_status]
        elif res.proposed_status in [ds.value for ds in DomainStatus]:
            new_domain_status = DomainStatus(res.proposed_status)
    except Exception as e:
        logger.error(f"Failed to reclassify record during link: {e}")

    try:
        persistence.update_record_optimistically(record_id, payload, new_domain_status.value, req.record_version)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _get_record(record_id)


@router.post("/api/v1/records/{record_id}/unlink-interview", response_model=SubmissionRecord, tags=["Manager Actions"])
def post_unlink_interview(record_id: str, req: UnlinkInterviewConversationRequest, manager_identity: str = Depends(get_trusted_manager_identity)):
    """Unlink an associated interview conversation upon explicit manager confirmation."""
    rec, payload = _validate_and_get_record_payload(record_id, req)
    now_iso = datetime.now(TIMEZONE_UTC).isoformat()

    linked_convs = payload.get("linked_conversations", [])
    updated_linked = []
    found = False
    for lc in linked_convs:
        lc_id = lc.get("conversation_id") if isinstance(lc, dict) else getattr(lc, "conversation_id", None)
        if lc_id == req.linked_conversation_id:
            found = True
        else:
            updated_linked.append(lc if isinstance(lc, dict) else lc.dict())

    if not found:
        return _get_record(record_id)

    payload["linked_conversations"] = updated_linked

    timeline = payload.get("timeline", [])
    timeline.append({
        "entry_id": f"audit_unlink_{uuid.uuid4().hex[:8]}",
        "event_type": "MANAGER_UNLINKED_INTERVIEW_CONVERSATION",
        "sender": manager_identity,
        "timestamp": now_iso,
        "is_system_note": True,
        "body_preview": "Manager unlinked interview conversation."
    })
    payload["timeline"] = timeline

    # Reclassify to determine updated domain status
    new_domain_status = rec.domain_status
    try:
        from backend.app.domain.consolidated_classifier import classify_record, PROPOSED_TO_DOMAIN_STATUS
        res = classify_record(
            rec.graph_immutable_id,
            payload.get("thread_messages", []),
            datetime.now(TIMEZONE_UTC),
            timeline=payload.get("timeline", []),
            linked_conversations=payload.get("linked_conversations", [])
        )
        if res.proposed_status in PROPOSED_TO_DOMAIN_STATUS:
            new_domain_status = PROPOSED_TO_DOMAIN_STATUS[res.proposed_status]
        elif res.proposed_status in [ds.value for ds in DomainStatus]:
            new_domain_status = DomainStatus(res.proposed_status)
    except Exception as e:
        logger.error(f"Failed to reclassify record during unlink: {e}")

    try:
        persistence.update_record_optimistically(record_id, payload, new_domain_status.value, req.record_version)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _get_record(record_id)
