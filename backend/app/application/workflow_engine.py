"""
Deterministic Workflow Engine for M3.

INVARIANTS:
1. 48 calendar-hour feedback timer, computed in America/New_York.
2. Timer starts ONLY when interview state transitions to COMPLETED.
3. Rescheduled/Cancelled/Not Confirmed do NOT start the timer.
4. No automatic closure — only explicit manager close action.
5. Reopen: if a closed record's exact conversationId receives a newer message, reopen to NeedsReview.
6. Manager notes: NEVER overwritten — only appended with timestamp.
7. System notes: separate, automatically maintained.
8. Job ID, EP reference, subject, candidate name NEVER used for conversation linking.
   Only conversationId and graph_immutable_id are identity keys.
"""

from datetime import datetime, timedelta
from typing import Any, List, Optional, Tuple
from backend.app.domain.models import (
    DomainStatus, InterviewState, CloseReason, CloseAction
)
from backend.app.domain.date_utils import TIMEZONE_NEW_YORK, TIMEZONE_UTC

# 48 calendar hours
FEEDBACK_WINDOW_HOURS = 48

# Valid interview state transitions
VALID_INTERVIEW_TRANSITIONS: dict[Optional[InterviewState], set[InterviewState]] = {
    None: {InterviewState.REQUESTED, InterviewState.SCHEDULED},
    InterviewState.REQUESTED: {InterviewState.SCHEDULED, InterviewState.CANCELLED, InterviewState.NOT_CONFIRMED},
    InterviewState.SCHEDULED: {InterviewState.COMPLETED, InterviewState.RESCHEDULED, InterviewState.CANCELLED, InterviewState.NOT_CONFIRMED},
    InterviewState.COMPLETED: set(),  # terminal for interview sub-state
    InterviewState.RESCHEDULED: {InterviewState.SCHEDULED, InterviewState.CANCELLED},
    InterviewState.CANCELLED: set(),  # terminal
    InterviewState.NOT_CONFIRMED: set(),  # terminal
}

# Interview states that start the 48h feedback timer
TIMER_STARTING_STATES = {InterviewState.COMPLETED}


def compute_feedback_due_at(completed_at_iso: str) -> str:
    """Compute 48-calendar-hour deadline from interview completion time.
    48 calendar hours = exactly 48h wall-clock, added in UTC to avoid DST drift."""
    completed_dt = datetime.fromisoformat(completed_at_iso)
    if completed_dt.tzinfo is None:
        completed_dt = completed_dt.replace(tzinfo=TIMEZONE_UTC)
    completed_utc = completed_dt.astimezone(TIMEZONE_UTC)
    due_utc = completed_utc + timedelta(hours=FEEDBACK_WINDOW_HOURS)
    return due_utc.isoformat()


def is_feedback_overdue(feedback_due_at_iso: str, now: Optional[datetime] = None) -> bool:
    """Check if the 48h feedback window has expired."""
    if not feedback_due_at_iso:
        return False
    now = now or datetime.now(TIMEZONE_UTC)
    due_dt = datetime.fromisoformat(feedback_due_at_iso)
    if due_dt.tzinfo is None:
        due_dt = due_dt.replace(tzinfo=TIMEZONE_UTC)
    return now > due_dt


def validate_interview_transition(
    current_state: Optional[InterviewState],
    new_state: InterviewState
) -> Tuple[bool, str]:
    """Validate an interview state transition. Returns (is_valid, reason)."""
    allowed = VALID_INTERVIEW_TRANSITIONS.get(current_state, set())
    if new_state in allowed:
        return True, "ok"
    if current_state is None:
        return False, f"Cannot transition from no interview state to {new_state.value}"
    return False, f"Cannot transition from {current_state.value} to {new_state.value}"


def compute_domain_status_after_interview(
    interview_state: InterviewState,
    current_status: DomainStatus
) -> DomainStatus:
    """Determine domain status based on interview state change."""
    if interview_state == InterviewState.COMPLETED:
        return DomainStatus.AWAITING_FEEDBACK
    if interview_state in (InterviewState.CANCELLED, InterviewState.NOT_CONFIRMED):
        return DomainStatus.NEEDS_REVIEW
    if interview_state == InterviewState.RESCHEDULED:
        return DomainStatus.IN_EVALUATION
    if interview_state in (InterviewState.REQUESTED, InterviewState.SCHEDULED):
        return DomainStatus.IN_EVALUATION
    return current_status


def evaluate_status_on_timer_check(
    current_status: DomainStatus,
    feedback_due_at: Optional[str],
    now: Optional[datetime] = None
) -> DomainStatus:
    """
    Check if 48h feedback timer has expired without response.
    Transitions AwaitingFeedback / PendingFollowUp to FeedbackDue when expired.
    """
    if current_status in (DomainStatus.AWAITING_FEEDBACK, DomainStatus.PENDING_FOLLOW_UP, DomainStatus.IN_EVALUATION):
        if feedback_due_at and is_feedback_overdue(feedback_due_at, now):
            return DomainStatus.FEEDBACK_DUE
    return current_status


def validate_close_action(action: CloseAction) -> Tuple[bool, str]:
    """Validate a close action. Other reason requires a note."""
    if action.reason == CloseReason.OTHER and not (action.note and action.note.strip()):
        return False, "Close reason 'Other' requires a note"
    return True, "ok"


def should_reopen_on_new_message(
    current_status: DomainStatus,
    existing_latest_timestamp: Optional[str],
    new_message_timestamp: str
) -> bool:
    """
    Determine if a closed record should reopen when a newer exact-conversation message arrives.
    Only conversationId matching triggers this — never Job ID, EP ref, subject, or candidate name.
    """
    if current_status != DomainStatus.CLOSED:
        return False
    if not existing_latest_timestamp:
        return True  # no prior message, new one reopens
    try:
        existing_dt = datetime.fromisoformat(existing_latest_timestamp)
        new_dt = datetime.fromisoformat(new_message_timestamp)
        if existing_dt.tzinfo is None:
            existing_dt = existing_dt.replace(tzinfo=TIMEZONE_UTC)
        if new_dt.tzinfo is None:
            new_dt = new_dt.replace(tzinfo=TIMEZONE_UTC)
        return new_dt > existing_dt
    except (ValueError, TypeError):
        return False


def format_system_note(event: str, timestamp: Optional[str] = None) -> str:
    """Format a system note entry with timestamp."""
    ts = timestamp or datetime.now(TIMEZONE_UTC).isoformat()
    return f"[{ts}] {event}"


def append_manager_note(existing_notes: str, new_note: str) -> str:
    """
    Append a manager note. NEVER overwrites existing notes.
    Each note is timestamped and separated by newline.
    """
    ts = datetime.now(TIMEZONE_UTC).isoformat()
    entry = f"[{ts}] {new_note}"
    if existing_notes and existing_notes.strip():
        return f"{existing_notes}\n{entry}"
    return entry


# --- Draft Suggestion Safety & Recipient Validation ---

import re

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def is_valid_email(email_str: Optional[str]) -> bool:
    """Check if a string is a valid authentic email address."""
    if not email_str or not isinstance(email_str, str):
        return False
    email_str = email_str.strip()
    return bool(EMAIL_REGEX.match(email_str))


def validate_recipient(recipient_candidate: Optional[str]) -> Tuple[bool, str]:
    """
    Validate that a recipient string is an authentic email address and not a
    system note, manager action, display label, or non-email string.
    """
    if not recipient_candidate or not recipient_candidate.strip():
        return False, "Recipient is empty"
    val = recipient_candidate.strip()
    # Reject strings that represent internal system notes or manager actions
    lowered = val.lower()
    if any(keyword in lowered for keyword in [
        "manager action", "system note", "manual confirmation",
        "recruitment system", "follow up agent", "internal", "action required"
    ]):
        return False, f"String '{val}' is an internal system/manager action, not an email recipient"
    if not is_valid_email(val):
        return False, f"String '{val}' is not a valid email address"
    return True, "ok"


def check_suggestion_eligibility(
    domain_status: DomainStatus,
    feedback_due_at: Optional[str] = None,
    now: Optional[datetime] = None
) -> Tuple[bool, str]:
    """
    Deterministic eligibility check for generating follow-up suggestions.
    
    RULES:
    1. AwaitingFeedback is NOT eligible while the 48-hour feedback timer still has time remaining.
    2. Post-interview follow-up is enabled ONLY when status becomes FeedbackDue.
    3. PendingFollowUp is eligible for submission follow-up.
    4. Closed, ClientRejected, PositionClosed records are NOT eligible.
    5. NeedsReview, ManagerActionRequired, InEvaluation are NOT eligible until reviewed.
    """
    if domain_status == DomainStatus.AWAITING_FEEDBACK:
        if feedback_due_at and not is_feedback_overdue(feedback_due_at, now):
            return False, "Record is Awaiting Feedback with 48h timer active. Follow-up is not yet due."
        return False, "Record is Awaiting Feedback. Status must transition to Feedback Due before follow-up can be generated."

    if domain_status == DomainStatus.FEEDBACK_DUE:
        return True, "Eligible for post-interview feedback follow-up."

    if domain_status == DomainStatus.PENDING_FOLLOW_UP:
        return True, "Eligible for submission follow-up."

    if domain_status in (DomainStatus.CLOSED, DomainStatus.CLIENT_REJECTED, DomainStatus.POSITION_CLOSED):
        return False, f"Record is closed ({domain_status.value}). Follow-up suggestions are disabled."

    return False, f"Record status '{domain_status.value}' is not eligible for automatic follow-up suggestion."


def build_professional_followup_draft(
    domain_status: DomainStatus,
    candidate_name: Optional[str],
    requirement_name: Optional[str],
    job_id: Optional[str] = None,
    ep_reference: Optional[str] = None,
    interview_datetime: Optional[str] = None,
    interview_invite_found: Optional[bool] = None,
) -> str:
    """Return a concise, deterministic manager-editable draft; never sends mail."""
    candidate = (candidate_name or "the candidate").strip()
    requirement = (requirement_name or "the position").strip()
    references = []
    if job_id:
        references.append(f"Job ID {job_id}")
    # EP identifies candidate ownership, not a requirement or conversation.  It
    # must never drive reply routing and is intentionally omitted from drafts.
    reference_line = f" ({' · '.join(references)})" if references else ""

    if domain_status == DomainStatus.FEEDBACK_DUE:
        interview_reference = f" on {interview_datetime}" if interview_datetime else ""
        purpose = f"Could you please share the interview feedback for {candidate}?"
        if interview_datetime:
            interview_context = (
                f"{candidate} completed the interview{interview_reference} for the "
                f"{requirement} position{reference_line}."
            )
        elif interview_invite_found is False:
            interview_context = (
                f"The interview was requested for {candidate} for the {requirement} "
                f"position{reference_line}, but we have not received the calendar invite."
            )
        else:
            interview_context = (
                f"This is regarding the interview for {candidate} for the "
                f"{requirement} position{reference_line}."
            )
        request = f"{interview_context} Please also advise us on the next steps."
    else:
        purpose = (
            f"I am following up to check whether you had a chance to review the profile of "
            f"{candidate} for the {requirement} position{reference_line}."
        )
        request = "Please let us know if you need the candidate's interview availability or any additional information."

    return (
        "Hi Team,\n\n"
        "Hope you are doing well.\n\n"
        f"{purpose}\n\n"
        f"{request}\n\n"
        "Thank you,\n"
        "Tarun Srivastava\n"
        "ClifyX"
    )


# --- M5 Deterministic Reply All, Anchor Selection & Approval Hashing ---

import hashlib
import json
from backend.app.domain.models import TimelineEntry

SELF_MANAGER_EMAIL = "tarun@clifyx.com"


def select_reply_anchor_message(
    timeline: List[TimelineEntry],
    record_immutable_id: Optional[str] = None,
    original_conversation_id: Optional[str] = None
) -> Optional[TimelineEntry]:
    """
    Select the latest real Outlook mailbox message belonging to the exact original conversation.
    
    INVARIANTS:
    1. Must have a valid immutable Graph message ID.
    2. Never selects a system note, manager confirmation, synthetic display event,
       local note, Job ID, EP reference, subject, or candidate metadata.
    3. Strictly ignores messages from separate interview coordination chains.
    4. For a no-response conversation, the latest sent submission/follow-up message is the anchor.
    5. For a conversation with an incoming response, uses the latest real mailbox message.
    """
    if not timeline:
        return None

    # Scan in reverse chronological order (latest message first)
    for entry in reversed(timeline):
        # Must not be a system note or manager confirmation
        if entry.is_system_note:
            continue
        # Strict boundary: never select a message belonging to a separate interview coordination chain
        if getattr(entry, "role", None) == "interview_coordination":
            continue
        if original_conversation_id and getattr(entry, "conversation_id", None) and entry.conversation_id != original_conversation_id:
            continue
        # Sender must be a valid authentic email address (not display label / system action)
        is_valid, _ = validate_recipient(entry.sender)
        if not is_valid:
            continue
        # Must have an immutable Graph message ID
        msg_id = entry.graph_immutable_id or (record_immutable_id if entry.sender.lower() == SELF_MANAGER_EMAIL.lower() else None)
        if msg_id and msg_id.strip():
            # Found real Outlook mailbox message in original submission conversation
            return entry

    return None


INTERVIEW_REPLY_STATUSES = {
    DomainStatus.INTERVIEW_REQUEST_SCHEDULED,
    DomainStatus.INTERVIEW_AWAITING_CONFIRMATION,
}


def derive_interview_draft_context(record) -> Tuple[Optional[str], Optional[bool]]:
    """Derive interview date and invite presence from stored mailbox evidence only."""
    from backend.app.domain.interview_parser import parse_explicit_datetime

    parsed_dates: List[datetime] = []
    invite_found = False
    messages: List[dict[str, Any]] = []
    for linked in record.linked_conversations:
        if linked.role == "interview_coordination":
            messages.extend(linked.thread_messages)

    for message in messages:
        text = message.get("bodyPreview") or ((message.get("body") or {}).get("content") or "")
        lowered = text.lower()
        if any(term in lowered for term in ("invite sent", "calendar invite", "meeting invitation")):
            invite_found = True
        timestamp_raw = message.get("sentDateTime") or message.get("receivedDateTime")
        if not timestamp_raw:
            continue
        try:
            timestamp = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
            parsed = parse_explicit_datetime(text, timestamp)
            if parsed:
                parsed_dates.append(parsed)
        except (TypeError, ValueError):
            continue

    if parsed_dates:
        latest = max(parsed_dates)
        return latest.strftime("%B %-d, %Y at %-I:%M %p %Z"), invite_found
    return None, (invite_found if messages else None)


def _linked_message_to_timeline(record_id: str, message: dict[str, Any]) -> Optional[TimelineEntry]:
    """Convert an explicitly linked Graph message into an anchor candidate."""
    message_id = message.get("id") or message.get("graph_immutable_id")
    conversation_id = message.get("conversationId") or message.get("conversation_id")
    sender = (
        ((message.get("from") or {}).get("emailAddress") or {}).get("address")
        or message.get("sender")
        or ""
    )
    timestamp = message.get("sentDateTime") or message.get("receivedDateTime") or message.get("timestamp")
    if not message_id or not conversation_id or not timestamp or not validate_recipient(sender)[0]:
        return None

    def recipients(key: str) -> List[str]:
        return [
            ((item.get("emailAddress") or {}).get("address") or "").strip()
            for item in (message.get(key) or [])
            if ((item.get("emailAddress") or {}).get("address") or "").strip()
        ]

    reply_to_items = recipients("replyTo")
    return TimelineEntry(
        entry_id=f"linked-{message_id}", record_id=record_id, sender=sender,
        timestamp=timestamp,
        body_preview=message.get("bodyPreview") or ((message.get("body") or {}).get("content") or ""),
        to_recipients=recipients("toRecipients"), cc_recipients=recipients("ccRecipients"),
        reply_to=reply_to_items[0] if reply_to_items else None,
        graph_immutable_id=message_id, conversation_id=conversation_id,
        role="interview_coordination",
    )


def select_record_reply_context(record) -> Tuple[Optional[TimelineEntry], Optional[str]]:
    """Select a reply anchor only from immutable mailbox identity.

    First/no-response follow-ups use the original submission conversation. Interview
    workflows use the latest genuine message in a manager-linked interview
    conversation, falling back to the original conversation when none is linked.
    Metadata such as subject, Job ID, EP reference, and candidate name is never used.
    """
    if record.domain_status in INTERVIEW_REPLY_STATUSES:
        linked_candidates: List[TimelineEntry] = []
        for linked in record.linked_conversations:
            if linked.role != "interview_coordination":
                continue
            for raw in linked.thread_messages:
                candidate = _linked_message_to_timeline(record.id, raw)
                if candidate and candidate.conversation_id == linked.conversation_id:
                    linked_candidates.append(candidate)
        if linked_candidates:
            anchor = max(linked_candidates, key=lambda entry: entry.timestamp)
            return anchor, anchor.conversation_id

    if record.domain_status == DomainStatus.PENDING_FOLLOW_UP:
        for entry in record.timeline:
            if (
                not entry.is_system_note
                and entry.graph_immutable_id == record.graph_immutable_id
                and (not entry.conversation_id or entry.conversation_id == record.conversation_id)
            ):
                return entry, record.conversation_id

    anchor = select_reply_anchor_message(
        record.timeline, record.graph_immutable_id, record.conversation_id
    )
    return anchor, record.conversation_id if anchor else None


def compute_reply_all_recipients(
    source_message: TimelineEntry,
    self_email: str = SELF_MANAGER_EMAIL
) -> Tuple[List[str], List[str], List[str], Optional[str]]:
    """
    Deterministically compute Reply All recipients (To, CC, BCC, reply_to) from source message metadata.
    
    INVARIANTS:
    1. To and CC preserve Reply All participants.
    2. Honors replyTo when present on the source message.
    3. Excludes the manager's own address (tarun@clifyx.com) to avoid self-reply.
    4. BCC starts strictly empty [].
    """
    self_lower = self_email.strip().lower()
    to_list: List[str] = []
    cc_list: List[str] = []
    bcc_list: List[str] = []  # Starts strictly empty

    # 1. Check reply_to
    reply_to_addr = source_message.reply_to.strip() if source_message.reply_to else None
    if reply_to_addr and is_valid_email(reply_to_addr) and reply_to_addr.lower() != self_lower:
        to_list.append(reply_to_addr)
    else:
        reply_to_addr = None

    # 2. If reply_to is not present, sender is primary To recipient (if not self)
    if not reply_to_addr:
        sender = source_message.sender.strip()
        if is_valid_email(sender) and sender.lower() != self_lower:
            to_list.append(sender)
        elif sender.lower() == self_lower:
            # If the manager sent the anchor (e.g. initial submission with no reply yet),
            # the recipient of the reply is the original To recipient(s)
            for r in source_message.to_recipients:
                r_clean = r.strip()
                if is_valid_email(r_clean) and r_clean.lower() != self_lower and r_clean not in to_list:
                    to_list.append(r_clean)

    # 3. Add other original To recipients (excluding self and existing)
    for r in source_message.to_recipients:
        r_clean = r.strip()
        if is_valid_email(r_clean) and r_clean.lower() != self_lower and r_clean not in to_list:
            to_list.append(r_clean)

    # 4. Add original CC recipients (excluding self and existing)
    for r in source_message.cc_recipients:
        r_clean = r.strip()
        if is_valid_email(r_clean) and r_clean.lower() != self_lower and r_clean not in to_list and r_clean not in cc_list:
            cc_list.append(r_clean)

    return to_list, cc_list, bcc_list, reply_to_addr


def validate_bcc_list(bcc_list: List[str]) -> Tuple[bool, List[str], Optional[str]]:
    """
    Validate and normalize BCC list.
    
    RULES:
    1. Every BCC address must end exactly in '@clifyx.com'.
    2. Rejects external domains (e.g. '@tcs.com', '@gmail.com').
    3. Rejects malformed email addresses or non-email strings.
    4. Normalizes case (lower) and trims whitespace.
    """
    if not bcc_list:
        return True, [], None

    normalized: List[str] = []
    seen = set()

    for addr in bcc_list:
        if not addr or not isinstance(addr, str):
            continue
        cleaned = addr.strip().lower()
        if not cleaned:
            continue

        if not is_valid_email(cleaned):
            return False, [], f"BCC address '{addr}' is not a valid email address"

        if not cleaned.endswith("@clifyx.com"):
            return False, [], f"BCC address '{addr}' is rejected: all BCC recipients must end exactly in @clifyx.com"

        if cleaned not in seen:
            seen.add(cleaned)
            normalized.append(cleaned)

    return True, normalized, None


import hashlib
import json
import uuid
from backend.app.domain.models import DraftApprovalRecord, DraftOperationRecord, DraftOperationState
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine



def compute_draft_approval_hash(
    record_id: str,
    conversation_id: str,
    source_message_id: str,
    content: str,
    to_list: List[str],
    cc_list: List[str],
    bcc_list: List[str],
    manager_identity: str = SELF_MANAGER_EMAIL
) -> str:
    """
    Compute a deterministic SHA-256 approval hash bound to:
    1. record_id
    2. exact conversation_id
    3. immutable source_message_id (reply anchor)
    4. content
    5. canonical To recipients
    6. canonical CC recipients
    7. normalized BCC recipients
    8. manager identity (tarun@clifyx.com)
    
    Any edit or cross-record replay will produce a different hash, invalidating prior approval.
    """
    canonical_data = {
        "record_id": record_id.strip(),
        "conversation_id": conversation_id.strip(),
        "source_message_id": source_message_id.strip(),
        "content": content.strip(),
        "to": sorted([e.strip().lower() for e in to_list if e.strip()]),
        "cc": sorted([e.strip().lower() for e in cc_list if e.strip()]),
        "bcc": sorted([e.strip().lower() for e in bcc_list if e.strip()]),
        "manager_identity": manager_identity.strip().lower()
    }
    canonical_str = json.dumps(canonical_data, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


def create_and_store_approval(
    record_id: str,
    conversation_id: str,
    immutable_anchor_id: str,
    canonical_to: List[str],
    canonical_cc: List[str],
    normalized_bcc: List[str],
    content: str,
    record_version: int,
    engine: EncryptedPersistenceEngine,
    manager_identity: str = SELF_MANAGER_EMAIL
) -> DraftOperationRecord:
    """
    Stage 1: Create and store a persistent server-side draft operation record.
    Generates a server-authoritative UUID idempotency key.
    """
    approval_hash = compute_draft_approval_hash(
        record_id=record_id,
        conversation_id=conversation_id,
        source_message_id=immutable_anchor_id,
        content=content,
        to_list=canonical_to,
        cc_list=canonical_cc,
        bcc_list=normalized_bcc,
        manager_identity=manager_identity
    )
    
    now_iso = datetime.now(TIMEZONE_UTC).isoformat()
    idempotency_key = f"idemp-{uuid.uuid4().hex}"

    payload_data = {
        "conversation_id": conversation_id,
        "immutable_anchor_id": immutable_anchor_id,
        "manager_identity": manager_identity,
        "canonical_to": canonical_to,
        "canonical_cc": canonical_cc,
        "normalized_bcc": normalized_bcc,
        "content": content,
        "approval_expires_at": (datetime.now(TIMEZONE_UTC) + timedelta(minutes=15)).isoformat(),
        "generation": uuid.uuid4().hex,
        "reconciliation_attempts": 0,
    }

    op = DraftOperationRecord(
        idempotency_key=idempotency_key,
        record_id=record_id,
        approval_hash=approval_hash,
        record_version=record_version,
        state=DraftOperationState.APPROVED,
        created_at=now_iso,
        updated_at=now_iso,
        payload_data=payload_data
    )
    
    engine.supersede_active_draft_operations(record_id)
    engine.store_draft_operation(op)
    return op


def get_draft_operation(idempotency_key: str, engine: EncryptedPersistenceEngine) -> Optional[DraftOperationRecord]:
    """Retrieve draft operation by idempotency key."""
    return engine.get_draft_operation(idempotency_key)

def invalidate_server_approval(idempotency_key: str, engine: EncryptedPersistenceEngine):
    """Invalidate approval by marking it failed/reconcilable."""
    engine.update_draft_operation_state(idempotency_key, DraftOperationState.FAILED_RECONCILABLE)


def validate_draft_operation_match(
    op: DraftOperationRecord,
    current_conversation_id: str,
    current_anchor_id: str,
    client_approval_hash: str,
    content: str,
    to_list: List[str],
    cc_list: List[str],
    bcc_list: List[str],
    manager_identity: str = SELF_MANAGER_EMAIL
) -> Tuple[bool, Optional[str]]:
    """
    Stage 2: Look up persistent server-side draft operation record and validate current server state against it.
    """
    if op.state not in (
        DraftOperationState.APPROVED,
        DraftOperationState.CREATING,
        DraftOperationState.RECOVERED_PENDING_FINALIZATION,
        DraftOperationState.CREATED,
    ):
        return False, f"Draft operation cannot create or resume from state {op.state.value}"

    expires_at = op.payload_data.get("approval_expires_at")
    if expires_at and datetime.fromisoformat(expires_at) <= datetime.now(TIMEZONE_UTC):
        return False, "Draft approval expired. Review and approve the current conversation again."

    if op.approval_hash != client_approval_hash:
        return False, "Approval hash mismatch. The client approval hash is invalid."

    if op.payload_data.get("conversation_id") != current_conversation_id:
        return False, "Conversation ID has changed since approval."

    if op.payload_data.get("immutable_anchor_id") != current_anchor_id:
        return False, "Source message (reply anchor) has changed since approval."

    recomputed_hash = compute_draft_approval_hash(
        record_id=op.record_id,
        conversation_id=current_conversation_id,
        source_message_id=current_anchor_id,
        content=content,
        to_list=to_list,
        cc_list=cc_list,
        bcc_list=bcc_list,
        manager_identity=manager_identity
    )

    if op.approval_hash != recomputed_hash:
        return False, "Approval hash mismatch. The draft content, recipients, or metadata have changed."

    return True, None
