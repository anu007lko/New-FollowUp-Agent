import re
from backend.app.domain.models import ConversationFacts
from backend.app.domain.text_cleaner import clean_email_text

def evaluate_outcome_status(facts: ConversationFacts) -> None:
    """
    Evaluates outcome status deterministically (Position Closed, Rejection, Duplicate).
    Modifies facts in place.
    """
    if not facts.latest_inbound_message:
        return
        
    raw_text = facts.latest_inbound_message.body_preview or ""
    clean_text = clean_email_text(raw_text)
    lower_text = clean_text.lower()
    
    # 1. Negation, conditional, hypothetical checks
    # If the text contains conditionals near the keywords or generally, we flag as Needs Review.
    conditionals = [
        " if ", "unless", "might", "would be", "could be", "not closed", 
        "not a rejection", "not rejected", "not duplicate", "assuming"
    ]
    if any(cond in lower_text for cond in conditionals):
        facts.outcome_status = "Needs Review"
        return
        
    # 2. Extract matches
    closed_phrases = [
        "position closed", "cancelled", "filled", "on hold indefinitely", 
        "no longer active", "role is closed", "req is closed", "position is closed"
    ]
    
    reject_phrases = [
        "reject", "not a fit", "moving forward with other", "will not proceed", 
        "pass on", "passing on", "not moving forward", "decline",
        "cannot consider the associate", "cannot consider the candidate",
        "cannot consider this associate", "cannot consider this candidate"
    ]
    
    duplicate_phrases = [
        "already submitted", "duplicate submission", "existing ownership", 
        "already represented", "already in process", "duplicate candidate"
    ]
    
    has_closed = any(p in lower_text for p in closed_phrases)
    has_reject = any(p in lower_text for p in reject_phrases)
    has_duplicate = any(p in lower_text for p in duplicate_phrases)
    
    matches = sum([has_closed, has_reject, has_duplicate])
    
    if matches > 1:
        # Conflicting outcomes
        facts.outcome_status = "Needs Review"
        return
        
    if has_closed:
        facts.outcome_status = "Position Closed"
    elif has_reject:
        facts.outcome_status = "Rejection"
    elif has_duplicate:
        facts.outcome_status = "Duplicate / Already Submitted"
    else:
        # No clear match
        pass
