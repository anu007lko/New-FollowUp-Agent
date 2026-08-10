from typing import Dict, Any, Optional, List
from datetime import datetime
import re
from pydantic import BaseModel, Field
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
    "Feedback Due": DomainStatus.FEEDBACK_DUE,
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
                
            if event_type == "MANAGER_OUTCOME_DECISION" or "MANAGER_OUTCOME_DECISION" in str(event_type):
                if "Rejection" in body_preview:
                    return RecordClassificationResult(
                        category="Rejection",
                        proposed_status="ManagerActionRequired",
                        reason_code="manager_override"
                    )
                if "In Evaluation" in body_preview:
                    due_match = re.search(r"evaluation due at ([^|]+)$", body_preview)
                    if due_match:
                        try:
                            due_at = datetime.fromisoformat(due_match.group(1).strip())
                            if due_at.tzinfo is None:
                                due_at = due_at.replace(tzinfo=current_time.tzinfo)
                            if current_time >= due_at:
                                return RecordClassificationResult(category="In Evaluation", proposed_status="Follow-up Due", reason_code="manager_evaluation_expired")
                        except ValueError:
                            pass
                    return RecordClassificationResult(category="In Evaluation", proposed_status="In Evaluation", reason_code="manager_override")
            elif event_type == "INTERVIEW_CONFIRMATION_DECISION" or "INTERVIEW_CONFIRMATION_DECISION" in str(event_type):
                if "Interview confirmed" in body_preview:
                    return RecordClassificationResult(
                        category="Interview",
                        proposed_status="AwaitingFeedback",
                        reason_code="manager_override"
                    )

    if authoritative_followup_ids is None:
        authoritative_followup_ids = []
        
    facts = analyze_conversation(source_immutable_id, thread_messages)
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
    all_msgs = list(thread_messages or [])
    det = evaluate_thread_interview_details(all_msgs, current_time)
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
