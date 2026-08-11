from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from backend.app.domain.models import MessageDirection, MessageFact, ConversationFacts

def parse_graph_timestamp(ts_str: str) -> datetime:
    """Parse a Graph API ISO 8601 timestamp."""
    try:
        # Some Graph timestamps end in Z, some have +00:00. Replace Z to use fromisoformat.
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except ValueError:
        # Fallback to current UTC if completely unparseable
        return datetime.now(timezone.utc)

def is_automatic_reply(sender: Any, body_preview: Any, msg: dict) -> bool:
    """
    Conservatively detect automatic replies and delivery failures.
    Does not use content similarity, relies on deterministic patterns in headers/body.
    """
    if isinstance(sender, dict):
        sender = sender.get("address") or sender.get("emailAddress", {}).get("address") or ""
    if not isinstance(sender, str):
        sender = str(sender or "")
    if isinstance(body_preview, dict):
        body_preview = body_preview.get("content") or body_preview.get("bodyPreview") or ""
    if not isinstance(body_preview, str):
        body_preview = str(body_preview or "")

    sender = sender.lower()
    body = body_preview.lower()
    
    # Check sender
    if "noreply" in sender or "no-reply" in sender:
        return True
    if "mailer-daemon" in sender or "postmaster" in sender:
        return True
    if "microsoftexchange" in sender or "microsoft exchange" in sender:
        return True
        
    # Check item class for bounce
    item_class = msg.get("itemClass", "").lower()
    if "ipm.report" in item_class or "ndr" in item_class or "report." in item_class:
        return True
        
    # Check deterministic body strings typical of auto-replies and delivery failures
    auto_phrases = [
        "out of office",
        "automatic reply",
        "auto-reply",
        "i am currently away",
        "delivery has failed",
        "undeliverable:",
        "couldn't be delivered",
        "could not be delivered",
        "wasn't found at",
        "was not found at",
        "delivery failure",
        "delivery status notification",
        "returned to sender",
        "message could not be sent",
        "undelivered mail",
    ]
    if any(phrase in body for phrase in auto_phrases):
        return True
        
    return False

def analyze_conversation(
    source_immutable_id: str,
    thread_messages: List[Dict[str, Any]]
) -> ConversationFacts:
    """
    Analyze raw Graph thread messages and extract deterministic message facts.
    Groups messages into logical events based on internetMessageId.
    """
    messages_sorted = sorted(
        thread_messages,
        key=lambda m: parse_graph_timestamp(m.get("sentDateTime") or m.get("receivedDateTime") or "1970-01-01T00:00:00Z")
    )
    
    facts = ConversationFacts()
    logical_messages: Dict[str, MessageFact] = {}
    missing_id_messages: List[MessageFact] = []
    
    for msg in messages_sorted:
        msg_id = msg.get("id")
        ts_str = msg.get("sentDateTime") or msg.get("receivedDateTime") or "1970-01-01T00:00:00Z"
        timestamp = parse_graph_timestamp(ts_str)
        
        sender_info = msg.get("from", {}).get("emailAddress", {})
        sender_email = sender_info.get("address", "").lower()
        
        body_preview = msg.get("bodyPreview", "")
        internet_msg_id = msg.get("internetMessageId", "")
        
        direction = MessageDirection.UNKNOWN
        is_meaningful = False
        
        # Determine direction
        if msg_id and msg_id == source_immutable_id:
            direction = MessageDirection.ORIGINAL_SUBMISSION
            is_meaningful = True
        elif sender_email:
            # Check for automatic replies BEFORE declaring it a valid sent/inbound
            if is_automatic_reply(sender_email, body_preview, msg):
                direction = MessageDirection.AUTOMATIC_REPLY
            elif sender_email.endswith("@clifyx.com"):
                direction = MessageDirection.SENT_MESSAGE
                is_meaningful = True
            else:
                direction = MessageDirection.INBOUND_MESSAGE
                is_meaningful = True
                
        # Validate internetMessageId
        is_valid_imid = bool(internet_msg_id and internet_msg_id.strip() and internet_msg_id.startswith("<") and internet_msg_id.endswith(">"))
        
        if not is_valid_imid:
            facts.logical_copy_requires_review = True
            fact = MessageFact(
                graph_immutable_id=msg_id,
                internet_message_id=internet_msg_id if internet_msg_id else None,
                timestamp=timestamp,
                sender_email=sender_email,
                direction=direction,
                is_meaningful=is_meaningful,
                body_preview=body_preview
            )
            missing_id_messages.append(fact)
        else:
            if internet_msg_id in logical_messages:
                existing = logical_messages[internet_msg_id]
                existing.duplicate_immutable_ids.append(msg_id)
                # If the new one is the original submission, upgrade the existing one
                if direction == MessageDirection.ORIGINAL_SUBMISSION:
                    existing.direction = MessageDirection.ORIGINAL_SUBMISSION
                    existing.is_meaningful = True
                    # Swap primary ID to match source
                    if existing.graph_immutable_id:
                        existing.duplicate_immutable_ids.append(existing.graph_immutable_id)
                    existing.graph_immutable_id = msg_id
            else:
                fact = MessageFact(
                    graph_immutable_id=msg_id,
                    internet_message_id=internet_msg_id,
                    timestamp=timestamp,
                    sender_email=sender_email,
                    direction=direction,
                    is_meaningful=is_meaningful,
                    body_preview=body_preview
                )
                logical_messages[internet_msg_id] = fact
                
    # Combine back to facts.messages in timestamp order
    all_facts = list(logical_messages.values()) + missing_id_messages
    all_facts.sort(key=lambda m: m.timestamp)
    
    for fact in all_facts:
        facts.messages.append(fact)
        
        if fact.is_meaningful:
            facts.latest_real_message = fact
            if fact.direction == MessageDirection.INBOUND_MESSAGE:
                facts.latest_inbound_message = fact
                facts.has_meaningful_inbound_response = True
                facts.requires_classification = True
            elif fact.direction == MessageDirection.SENT_MESSAGE:
                facts.latest_sent_message = fact
                
    return facts

def evaluate_no_response_timers(
    facts: ConversationFacts,
    current_time: datetime,
    authoritative_followup_ids: List[str]
) -> None:
    """
    Evaluates follow-up timers based on exact timezone boundaries and anchor rules.
    Modifies ConversationFacts in place.
    """
    from datetime import timedelta
    from backend.app.domain.date_utils import TIMEZONE_NEW_YORK
    
    # 1. Inbound Priority
    if facts.has_meaningful_inbound_response:
        facts.no_response_status = "Requires Classification"
        return
        
    # 2. Anchor Selection
    original_sub = next((m for m in facts.messages if m.direction == MessageDirection.ORIGINAL_SUBMISSION), None)
    if not original_sub:
        # Cannot determine a timer without an original submission anchor
        return
        
    anchor = original_sub
    
    # Check later sent messages
    for msg in facts.messages:
        if msg.direction == MessageDirection.SENT_MESSAGE:
            all_ids = [msg.graph_immutable_id] + msg.duplicate_immutable_ids
            all_ids = [i for i in all_ids if i]
            
            if any(i in authoritative_followup_ids for i in all_ids):
                # Valid authoritative follow-up becomes the new anchor
                anchor = msg
            else:
                # Uncertain later sent message does NOT reset the timer but flags for review
                facts.followup_anchor_requires_review = True
                
    facts.timer_anchor_message = anchor
    
    # 3. Timer Calculation
    # Convert anchor timestamp to America/New_York local datetime, then add 48 hours
    anchor_local = anchor.timestamp.astimezone(TIMEZONE_NEW_YORK)
    current_local = current_time.astimezone(TIMEZONE_NEW_YORK)
    
    due_time_local = anchor_local + timedelta(hours=48)
    
    if current_local >= due_time_local:
        facts.no_response_status = "Follow-up Due"
    else:
        facts.no_response_status = "Awaiting Response"
