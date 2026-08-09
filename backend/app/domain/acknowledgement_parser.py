from backend.app.domain.models import ConversationFacts
from backend.app.domain.text_cleaner import clean_email_text

def evaluate_acknowledgement_status(facts: ConversationFacts) -> None:
    """
    Evaluates Acknowledgement and Unrelated outcomes deterministically.
    Modifies facts in place.
    """
    if not facts.latest_inbound_message:
        return
        
    # Exclude auto replies / bounces
    # We assume transport events are either not meaningful or have specific flags.
    # If it's an auto-reply, it shouldn't be here, but we enforce it:
    if not facts.latest_inbound_message.is_meaningful:
        return
        
    raw_text = facts.latest_inbound_message.body_preview or ""
    clean_text = clean_email_text(raw_text)
    lower_text = clean_text.lower()
    
    # 1. Negation, conditional, hypothetical checks
    conditionals = [
        " if ", "unless", "might", "would be", "could be", "assuming"
    ]
    if any(cond in lower_text for cond in conditionals):
        facts.outcome_status = "Needs Review"
        return
        
    # 2. Check for substantive outcomes to prevent false positives
    substantive_phrases = [
        "interview", "speak", "call", "meet", "today", "tomorrow", "am", "pm",
        "position closed", "cancelled", "filled", "on hold", "no longer active",
        "reject", "not a fit", "moving forward with other", "will not proceed", "pass on",
        "already submitted", "duplicate", "existing ownership", "already represented",
        "under review", "under evaluation", "awaiting feedback", "will update you",
        "share next steps", "candidate feedback", "additional information", "more info needed"
    ]
    
    if any(p in lower_text for p in substantive_phrases):
        facts.outcome_status = "Needs Review"
        return
        
    # 3. Extract matches
    ack_phrases = [
        "received", "noted", "thank you for sharing", "thank you for submitting", 
        "we received the profile", "thanks for sharing", "thanks for submitting",
        "we have received"
    ]
    
    unrelated_phrases = [
        "wrong email", "please remove", "wrong person", "not responsible for",
        "stop emailing", "unsubscribe", "wrong address"
    ]
    
    has_ack = any(p in lower_text for p in ack_phrases)
    has_unrelated = any(p in lower_text for p in unrelated_phrases)
    
    if has_ack and has_unrelated:
        # Conflicting outcomes
        facts.outcome_status = "Needs Review"
        return
        
    if has_ack:
        facts.outcome_status = "Acknowledgement"
    elif has_unrelated:
        facts.outcome_status = "Unrelated"
    else:
        pass
