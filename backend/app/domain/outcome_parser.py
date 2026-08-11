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
    
    # 1. Negation / hypothetical outcome checks.
    # Keep this narrow: normal business phrasing like "if it reopens" or
    # "submit other profiles if you have any" should not block clear outcomes.
    conditionals = [
        "unless", "would be rejected", "could be rejected", "might reject",
        "might be rejected", "might get rejected", "not closed",
        "not a rejection", "not rejected", "not duplicate", "assuming"
    ]
    if any(cond in lower_text for cond in conditionals):
        facts.outcome_status = "Needs Review"
        return
        
    # 2. Extract matches
    on_hold_phrases = [
        "position is on hold", "position on hold", "role is on hold",
        "requirement is on hold", "req is on hold", "on hold for now",
        "will update if it reopens", "if it reopens"
    ]

    selected_phrases = [
        "candidate is selected", "is selected", "selected, please share the application",
        "please share the application", "share the application",
        "completed and submitted her application", "completed and submitted his application",
        "application form"
    ]

    closed_phrases = [
        "position closed", "cancelled", "filled", "on hold indefinitely", 
        "no longer active", "role is closed", "req is closed", "position is closed",
        "requirement is closed"
    ]
    
    reject_phrases = [
        "reject", "not a fit", "moving forward with other", "will not proceed", 
        "pass on", "passing on", "not moving forward", "decline",
        "cannot consider the associate", "cannot consider the candidate",
        "cannot consider this associate", "cannot consider this candidate",
        "can not consider him", "can not consider her", "can not consider further",
        "cannot consider him", "cannot consider her", "cannot consider further",
        "won't be able to consider", "wont be able to consider",
        "not suitable", "not having required", "not having much experience",
        "submit other profiles", "please submit other profiles"
    ]
    
    duplicate_phrases = [
        "already submitted", "duplicate submission", "existing ownership", 
        "already represented", "already in process", "duplicate candidate",
        "thanks but duplicate", "but duplicate"
    ]
    
    has_on_hold = any(p in lower_text for p in on_hold_phrases)
    has_selected = any(p in lower_text for p in selected_phrases)
    has_closed = any(p in lower_text for p in closed_phrases)
    has_reject = any(p in lower_text for p in reject_phrases)
    has_duplicate = any(p in lower_text for p in duplicate_phrases)
    
    matches = sum([has_on_hold, has_selected, has_closed, has_reject, has_duplicate])
    
    if matches > 1:
        # Conflicting outcomes
        facts.outcome_status = "Needs Review"
        return
        
    if has_on_hold:
        facts.outcome_status = "On Hold"
    elif has_selected:
        facts.outcome_status = "Selected"
    elif has_closed:
        facts.outcome_status = "Position Closed"
    elif has_reject:
        facts.outcome_status = "Rejection"
    elif has_duplicate:
        facts.outcome_status = "Duplicate / Already Submitted"
    else:
        # No clear match
        pass
