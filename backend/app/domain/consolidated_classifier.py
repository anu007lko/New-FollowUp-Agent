from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone
import re
from pydantic import BaseModel, Field
from backend.app.domain.date_utils import TIMEZONE_NEW_YORK
from backend.app.domain.models import MessageDirection, MessageFact, ConversationFacts, DomainStatus
from backend.app.domain.message_facts import analyze_conversation, evaluate_no_response_timers
from backend.app.domain.interview_parser import evaluate_interview_status, evaluate_thread_interview_details
from backend.app.domain.outcome_parser import evaluate_outcome_status
from backend.app.domain.evaluation_parser import evaluate_in_evaluation_status
from backend.app.domain.acknowledgement_parser import evaluate_acknowledgement_status

PROPOSED_TO_DOMAIN_STATUS = {
    "Interview Scheduled": DomainStatus.INTERVIEW_REQUEST_SCHEDULED,
    "Interview Awaiting Confirmation": DomainStatus.INTERVIEW_AWAITING_CONFIRMATION,
    "Interview Request": DomainStatus.NEEDS_REVIEW,
    "Follow-up Due": DomainStatus.PENDING_FOLLOW_UP,
    "Awaiting Response": DomainStatus.AWAITING_RESPONSE,
    "Manager Action Required": DomainStatus.MANAGER_ACTION_REQUIRED,
    "In Evaluation": DomainStatus.IN_EVALUATION,
    "Needs Review": DomainStatus.NEEDS_REVIEW,
    "Awaiting Feedback": DomainStatus.AWAITING_FEEDBACK,
    "AwaitingFeedback": DomainStatus.AWAITING_FEEDBACK,
    "Feedback Due": DomainStatus.FEEDBACK_DUE,
    "FeedbackDue": DomainStatus.FEEDBACK_DUE,
    "Closed": DomainStatus.CLOSED,
    "New Submission": DomainStatus.NEW_SUBMISSION,
}

class RecordClassificationResult(BaseModel):
    category: str
    proposed_status: str
    reason_code: str
    timer_anchor_type: Optional[str] = None
    interview_datetime: Optional[str] = None
    interview_date: Optional[str] = None
    interview_time: Optional[str] = None
    timezone: Optional[str] = None
    timezone_source: Optional[str] = None
    confidence_label: Optional[str] = None
    supporting_message_ids: List[str] = Field(default_factory=list)


def _is_delivery_failure_message(message: Dict[str, Any]) -> bool:
    sub = str(message.get("subject") or "").lower()
    sender = str(message.get("from", {}).get("emailAddress", {}).get("address") or "").lower()
    body = str(message.get("bodyPreview") or message.get("body_preview") or message.get("uniqueBody", {}).get("content") or "").lower()
    return (
        "undeliverable:" in sub or
        "microsoftexchange" in sender or
        "postmaster" in sender or
        "mailer-daemon" in sender or
        "couldn't be delivered" in body or
        "wasn't found at" in body or
        "550 5.1.1" in body or
        "550 5.1.10" in body or
        "unknown to address" in body or
        "delivery failure" in body or
        "recipientnotfound" in body
    )


def classify_record(
    source_immutable_id: str,
    thread_messages: List[Dict[str, Any]],
    current_time: datetime,
    authoritative_followup_ids: Optional[List[str]] = None,
    timeline: Optional[List[Any]] = None,
    linked_conversations: Optional[List[Any]] = None
) -> RecordClassificationResult:
    """
    Consolidated deterministic classification pipeline for a single submission record.
    Follows fixed precedence hierarchy:
    1. Interview (including confirmed linked interview chains & multi-turn evaluation)
    2. Position Closed
    3. Rejection
    4. Duplicate / Already Submitted
    5. Feedback
    6. In Evaluation
    7. Acknowledgement
    8. No Response
    9. Unrelated
    10. Needs Review
    """
    if timeline:
        for entry in reversed(timeline):
            event_type = None
            body_preview = ""
            if isinstance(entry, dict):
                event_type = entry.get("event_type")
                body_preview = entry.get("body_preview", "")
            else:
                event_type = getattr(entry, "event_type", None) or getattr(entry, "entry_id", "")
                body_preview = getattr(entry, "body_preview", "")
                
            if event_type in ("MANAGER_RECORD_CLOSED", "MANAGER_OUTCOME_DECISION") or "MANAGER_RECORD_CLOSED" in str(event_type) or "MANAGER_OUTCOME_DECISION" in str(event_type):
                if any(t in body_preview for t in ["to Closed", "Closed", "Position Closed", "Rejection", "Client Rejected", "Candidate Withdrawn", "Duplicate", "Placed", "No Longer Available"]):
                    cat = "Position Closed" if "Position Closed" in body_preview else ("Rejection" if "Rejection" in body_preview else "Closed")
                    return RecordClassificationResult(
                        category=cat,
                        proposed_status="Closed",
                        reason_code="manager_closed"
                    )
                if "In Evaluation" in body_preview or "On Hold" in body_preview:
                    due_match = re.search(r"evaluation due at ([^|]+)$", body_preview)
                    if due_match:
                        try:
                            due_at = datetime.now(timezone.utc)
                            due_at = datetime.fromisoformat(due_match.group(1).strip())
                            if due_at.tzinfo is None:
                                due_at = due_at.replace(tzinfo=current_time.tzinfo)
                            if current_time >= due_at:
                                return RecordClassificationResult(category="In Evaluation", proposed_status="Follow-up Due", reason_code="manager_evaluation_expired")
                        except ValueError:
                            pass
                    return RecordClassificationResult(category="In Evaluation", proposed_status="In Evaluation", reason_code="manager_override")
            elif event_type in ("INTERVIEW_SCHEDULE_CONFIRMED", "MANAGER_INTERVIEW_SCHEDULE_CONFIRMED") or "INTERVIEW_SCHEDULE_CONFIRMED" in str(event_type):
                sched_match = re.search(r"interview schedule:\s*([0-9T:\-+.]+)", body_preview, re.IGNORECASE)
                if not sched_match:
                    sched_match = re.search(r"(202\d-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[^\s\)]*)", body_preview)
                if sched_match:
                    try:
                        iv_dt = datetime.fromisoformat(sched_match.group(1).strip())
                        if iv_dt.tzinfo is None:
                            iv_dt = iv_dt.replace(tzinfo=current_time.tzinfo)
                        end_dt = iv_dt + timedelta(hours=1)
                        if current_time >= end_dt:
                            iv_local = end_dt.astimezone(TIMEZONE_NEW_YORK)
                            next_morning_9am = (iv_local + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
                            curr_local = current_time.astimezone(TIMEZONE_NEW_YORK)
                            
                            target_status = "FeedbackDue" if curr_local >= next_morning_9am else "AwaitingFeedback"
                            reason_code = "INTERVIEW_ELAPSED_FEEDBACK_DUE" if curr_local >= next_morning_9am else "INTERVIEW_ELAPSED_AWAITING_FEEDBACK"
                            return RecordClassificationResult(
                                category="Interview Completed",
                                proposed_status=target_status,
                                reason_code=reason_code,
                                interview_datetime=sched_match.group(1).strip()
                            )
                        else:
                            return RecordClassificationResult(
                                category="Interview Scheduled",
                                proposed_status="Interview Scheduled",
                                reason_code="DETERMINISTIC_INTERVIEW_SCHEDULED",
                                interview_datetime=sched_match.group(1).strip()
                            )
                    except Exception:
                        pass
            elif event_type == "INTERVIEW_CONFIRMATION_DECISION" or "INTERVIEW_CONFIRMATION_DECISION" in str(event_type):
                if "Interview confirmed" in body_preview:
                    due_match = re.search(r"due\s*([0-9T:\-+.]+)", body_preview, re.IGNORECASE)
                    if due_match:
                        try:
                            due_at = datetime.fromisoformat(due_match.group(1).strip())
                            if due_at.tzinfo is None:
                                due_at = due_at.replace(tzinfo=current_time.tzinfo)
                            if current_time >= due_at:
                                return RecordClassificationResult(
                                    category="Interview Completed",
                                    proposed_status="FeedbackDue",
                                    reason_code="INTERVIEW_FEEDBACK_TIMER_EXPIRED"
                                )
                        except Exception:
                            pass
                    return RecordClassificationResult(
                        category="Interview Completed",
                        proposed_status="AwaitingFeedback",
                        reason_code="manager_override"
                    )

    if authoritative_followup_ids is None:
        authoritative_followup_ids = []
        
    all_thread_messages = list(thread_messages or [])
    if linked_conversations:
        for lc in linked_conversations:
            lc_role = getattr(lc, "role", None) if not isinstance(lc, dict) else lc.get("role")
            if lc_role == "client_response":
                lc_msgs = getattr(lc, "thread_messages", None) if not isinstance(lc, dict) else lc.get("thread_messages")
                if lc_msgs:
                    all_thread_messages.extend(lc_msgs)

    # Sort messages chronologically after merging
    all_thread_messages.sort(key=lambda m: m.get("sentDateTime") or m.get("receivedDateTime") or "")

    # Delivery failures are transport noise: remove them from evidence and keep
    # tracking the underlying submission/conversation normally.
    all_thread_messages = [m for m in all_thread_messages if not _is_delivery_failure_message(m)]

    facts = analyze_conversation(source_immutable_id, all_thread_messages)
    evaluate_no_response_timers(facts, current_time, authoritative_followup_ids)
    
    timer_anchor_type = None
    if facts.timer_anchor_message:
        if facts.timer_anchor_message.direction == MessageDirection.ORIGINAL_SUBMISSION:
            timer_anchor_type = "ORIGINAL_SUBMISSION"
        elif facts.timer_anchor_message.direction == MessageDirection.SENT_MESSAGE:
            timer_anchor_type = "MANAGER_FOLLOWUP"

    # Check 1b: Interview Activity from Confirmed Linked Conversations
    if linked_conversations:
        for lc in linked_conversations:
            lc_role = getattr(lc, "role", None) if not isinstance(lc, dict) else lc.get("role")
            lc_subject = getattr(lc, "subject", "") if not isinstance(lc, dict) else (lc.get("subject") or lc.get("interview_subject") or "")
            if lc_role == "interview_coordination" or "interview" in str(lc_subject).lower():
                lc_msgs = getattr(lc, "thread_messages", None) if not isinstance(lc, dict) else lc.get("thread_messages")
                if lc_msgs:
                    lc_det = evaluate_thread_interview_details(lc_msgs, current_time)
                    if lc_det.interview_status == "Interview Scheduled":
                        return RecordClassificationResult(
                            category="Interview Scheduled",
                            proposed_status="Interview Scheduled",
                            reason_code="LINKED_CONVERSATION_INTERVIEW_SCHEDULED",
                            timer_anchor_type=timer_anchor_type
                        )
                    elif lc_det.interview_status == "Interview Awaiting Confirmation":
                        return RecordClassificationResult(
                            category="Interview Scheduled",
                            proposed_status="Interview Awaiting Confirmation",
                            reason_code="LINKED_CONVERSATION_INTERVIEW_AWAITING_CONFIRMATION",
                            timer_anchor_type=timer_anchor_type
                        )
                if "interview scheduled" in str(lc_subject).lower():
                    return RecordClassificationResult(
                        category="Interview Scheduled",
                        proposed_status="Interview Awaiting Confirmation",
                        reason_code="LINKED_CONVERSATION_INTERVIEW_AWAITING_CONFIRMATION",
                        timer_anchor_type=timer_anchor_type
                    )

    # Check 1: Multi-turn Interview Evaluation
    det = evaluate_thread_interview_details(all_thread_messages, current_time)
    if det.confidence_label == "Schedule conflict":
        return RecordClassificationResult(
            category="Needs Review",
            proposed_status="Needs Review",
            reason_code="SCHEDULE_CONFLICT",
            timer_anchor_type=timer_anchor_type,
            interview_datetime=det.interview_datetime,
            interview_date=det.interview_date,
            interview_time=det.interview_time,
            timezone=det.timezone,
            timezone_source=det.timezone_source,
            confidence_label=det.confidence_label,
            supporting_message_ids=det.supporting_message_ids,
        )

    if det.interview_status in ("Interview Scheduled", "Interview Completed"):
        # Check if interview end-time has elapsed
        if det.interview_datetime:
            try:
                iv_dt = datetime.fromisoformat(det.interview_datetime)
                if iv_dt.tzinfo is None:
                    iv_dt = iv_dt.replace(tzinfo=current_time.tzinfo)
                end_dt = iv_dt + timedelta(hours=1)
                if current_time >= end_dt:
                    # Check next business morning 9 AM EDT
                    iv_local = end_dt.astimezone(TIMEZONE_NEW_YORK)
                    next_morning_9am = (iv_local + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
                    curr_local = current_time.astimezone(TIMEZONE_NEW_YORK)
                    
                    target_status = "FeedbackDue" if curr_local >= next_morning_9am else "AwaitingFeedback"
                    reason_code = "INTERVIEW_ELAPSED_FEEDBACK_DUE" if curr_local >= next_morning_9am else "INTERVIEW_ELAPSED_AWAITING_FEEDBACK"
                    
                    return RecordClassificationResult(
                        category="Interview Completed",
                        proposed_status=target_status,
                        reason_code=reason_code,
                        timer_anchor_type=timer_anchor_type,
                        interview_datetime=det.interview_datetime,
                        interview_date=det.interview_date,
                        interview_time=det.interview_time,
                        timezone=det.timezone,
                        timezone_source=det.timezone_source,
                        confidence_label=det.confidence_label,
                        supporting_message_ids=det.supporting_message_ids,
                    )
            except Exception:
                pass

        if det.interview_status == "Interview Scheduled":
            return RecordClassificationResult(
                category="Interview Scheduled",
                proposed_status="Interview Scheduled",
                reason_code="DETERMINISTIC_INTERVIEW_SCHEDULED",
                timer_anchor_type=timer_anchor_type,
                interview_datetime=det.interview_datetime,
                interview_date=det.interview_date,
                interview_time=det.interview_time,
                timezone=det.timezone,
                timezone_source=det.timezone_source,
                confidence_label=det.confidence_label,
                supporting_message_ids=det.supporting_message_ids,
            )

    if det.interview_status == "Interview Awaiting Confirmation":
        return RecordClassificationResult(
            category="Interview Scheduled",
            proposed_status="Interview Awaiting Confirmation",
            reason_code="DETERMINISTIC_INTERVIEW_AWAITING_CONFIRMATION",
            timer_anchor_type=timer_anchor_type,
            interview_datetime=det.interview_datetime,
            interview_date=det.interview_date,
            interview_time=det.interview_time,
            timezone=det.timezone,
            timezone_source=det.timezone_source,
            confidence_label=det.confidence_label,
            supporting_message_ids=det.supporting_message_ids,
        )

            
    # Check 2: Outcome Status (Position Closed, Rejection, Duplicate)
    if facts.no_response_status == "Requires Classification":
        evaluate_outcome_status(facts)
        if facts.outcome_status == "Position Closed":
            return RecordClassificationResult(
                category="Position Closed",
                proposed_status="Manager Action Required",
                reason_code="DETERMINISTIC_POSITION_CLOSED",
                timer_anchor_type=timer_anchor_type
            )
        elif facts.outcome_status == "Rejection":
            return RecordClassificationResult(
                category="Rejection",
                proposed_status="Manager Action Required",
                reason_code="DETERMINISTIC_REJECTION",
                timer_anchor_type=timer_anchor_type
            )
        elif facts.outcome_status == "Duplicate / Already Submitted":
            return RecordClassificationResult(
                category="Duplicate / Already Submitted",
                proposed_status="Manager Action Required",
                reason_code="DETERMINISTIC_DUPLICATE",
                timer_anchor_type=timer_anchor_type
            )
        elif facts.outcome_status == "On Hold":
            return RecordClassificationResult(
                category="On Hold",
                proposed_status="In Evaluation",
                reason_code="DETERMINISTIC_POSITION_ON_HOLD",
                timer_anchor_type=timer_anchor_type
            )
        elif facts.outcome_status == "Selected":
            return RecordClassificationResult(
                category="Selected",
                proposed_status="Manager Action Required",
                reason_code="DETERMINISTIC_SELECTED_APPLICATION_REQUESTED",
                timer_anchor_type=timer_anchor_type
            )
            
    # Check 3: In Evaluation & Feedback
    if facts.no_response_status == "Requires Classification" and facts.outcome_status in [None, "Needs Review"]:
        facts.outcome_status = None
        evaluate_in_evaluation_status(facts, current_time)
        if facts.outcome_status == "In Evaluation":
            if facts.in_evaluation_timer_status == "Follow-up Due":
                return RecordClassificationResult(
                    category="In Evaluation",
                    proposed_status="Follow-up Due",
                    reason_code="DETERMINISTIC_IN_EVALUATION_EXPIRED_48H",
                    timer_anchor_type=timer_anchor_type
                )
            else:
                return RecordClassificationResult(
                    category="In Evaluation",
                    proposed_status="In Evaluation",
                    reason_code="DETERMINISTIC_IN_EVALUATION_WITHIN_48H",
                    timer_anchor_type=timer_anchor_type
                )
        elif facts.outcome_status == "Feedback":
            return RecordClassificationResult(
                category="Feedback",
                proposed_status="Manager Action Required",
                reason_code="DETERMINISTIC_FEEDBACK_REQUESTED",
                timer_anchor_type=timer_anchor_type
            )
        elif facts.outcome_status == "Candidate Coordination":
            return RecordClassificationResult(
                category="Candidate Coordination",
                proposed_status="Manager Action Required",
                reason_code="DETERMINISTIC_CANDIDATE_COORDINATION_REQUIRED",
                timer_anchor_type=timer_anchor_type
            )
            
    # Check 4: Acknowledgement & Unrelated
    if facts.no_response_status == "Requires Classification" and facts.outcome_status in [None, "Needs Review"]:
        facts.outcome_status = None
        evaluate_acknowledgement_status(facts)
        if facts.outcome_status == "Acknowledgement":
            if facts.followup_anchor_requires_review:
                return RecordClassificationResult(
                    category="Acknowledgement",
                    proposed_status="Needs Review",
                    reason_code="UNCERTAIN_FOLLOWUP_ANCHOR",
                    timer_anchor_type=timer_anchor_type
                )
            elif facts.no_response_status == "Follow-up Due":
                return RecordClassificationResult(
                    category="Acknowledgement",
                    proposed_status="Follow-up Due",
                    reason_code="DETERMINISTIC_ACKNOWLEDGEMENT_FOLLOWUP_DUE",
                    timer_anchor_type=timer_anchor_type
                )
            else:
                return RecordClassificationResult(
                    category="Acknowledgement",
                    proposed_status="Awaiting Response",
                    reason_code="DETERMINISTIC_ACKNOWLEDGEMENT_AWAITING_RESPONSE",
                    timer_anchor_type=timer_anchor_type
                )
        elif facts.outcome_status == "Unrelated":
            return RecordClassificationResult(
                category="Unrelated",
                proposed_status="Needs Review",
                reason_code="DETERMINISTIC_UNRELATED_MESSAGE",
                timer_anchor_type=timer_anchor_type
            )
            
    # Check 5: No Response & Inbound Needs Review Fallback
    if facts.has_meaningful_inbound_response:
        # Meaningful inbound was received but remained unclassified by rules
        return RecordClassificationResult(
            category="Needs Review",
            proposed_status="Needs Review",
            reason_code="UNCLASSIFIED_INBOUND_MESSAGE",
            timer_anchor_type=timer_anchor_type
        )
    else:
        # No inbound response at all
        if facts.followup_anchor_requires_review:
            return RecordClassificationResult(
                category="No Response",
                proposed_status="Needs Review",
                reason_code="UNCERTAIN_FOLLOWUP_ANCHOR",
                timer_anchor_type=timer_anchor_type
            )
        elif facts.no_response_status == "Follow-up Due":
            return RecordClassificationResult(
                category="No Response",
                proposed_status="Follow-up Due",
                reason_code="NO_INBOUND_FOLLOWUP_DUE_48H",
                timer_anchor_type=timer_anchor_type
            )
        else:
            return RecordClassificationResult(
                category="No Response",
                proposed_status="Awaiting Response",
                reason_code="NO_INBOUND_AWAITING_RESPONSE_WITHIN_48H",
                timer_anchor_type=timer_anchor_type
            )


def refresh_classification_snapshot(
    payload: Dict[str, Any],
    graph_immutable_id: Optional[str] = None,
    evaluation_time: Optional[datetime] = None,
    authoritative_followup_ids: Optional[List[str]] = None,
    classifier_version: str = "v1.0",
    classify_fn: Optional[Any] = None
) -> RecordClassificationResult:
    """
    Explicit write-side classification service.
    Executes classify_record and persists classification_category,
    classification_updated_at, and classifier_version onto the payload dict.

    Permitted callers ONLY:
    - Record ingestion/import (import_service.py)
    - Controlled daily refresh/review (daily_review_engine.py)
    - Explicit reconciliation actions such as interview link/unlink (routes.py)
    - One-time migration/backfill (migrate_legacy_reasons.py)
    """
    graph_id = graph_immutable_id or payload.get("graph_immutable_id") or f"graph-{payload.get('id', 'unknown')}"
    eval_time = evaluation_time or datetime.now(timezone.utc)
    thread_msgs = payload.get("thread_messages", [])
    timeline_entries = payload.get("timeline", [])
    linked_convs = payload.get("linked_conversations", [])

    fn = classify_fn or classify_record
    res = fn(
        source_immutable_id=graph_id,
        thread_messages=thread_msgs,
        current_time=eval_time,
        authoritative_followup_ids=authoritative_followup_ids,
        timeline=timeline_entries,
        linked_conversations=linked_convs
    )

    if res and res.category:
        payload["classification_category"] = res.category
        payload["classification_updated_at"] = eval_time.isoformat()
        payload["classifier_version"] = classifier_version

    return res
