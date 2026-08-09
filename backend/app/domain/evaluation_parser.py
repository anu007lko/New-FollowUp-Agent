from datetime import datetime, timedelta
from backend.app.domain.models import ConversationFacts
from backend.app.domain.text_cleaner import clean_email_text
from backend.app.domain.date_utils import TIMEZONE_NEW_YORK

def evaluate_in_evaluation_status(facts: ConversationFacts, current_time: datetime) -> None:
    """
    Evaluates In-Evaluation and Feedback outcomes deterministically.
    Modifies facts in place.
    """
    if not facts.latest_inbound_message:
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
        
    # 2. Extract matches
    in_eval_phrases = [
        "under review", "under evaluation", "awaiting feedback", 
        "awaiting client feedback", "awaiting manager feedback",
        "will update you", "share next steps", "profile under review"
    ]
    
    feedback_phrases = [
        "interview feedback", "candidate feedback", 
        "additional information", "more info needed", "need more info", "request for additional"
    ]
    
    has_eval = any(p in lower_text for p in in_eval_phrases)
    has_feedback = any(p in lower_text for p in feedback_phrases)
    
    if has_eval and has_feedback:
        # Conflicting outcomes (ambiguous meaning)
        facts.outcome_status = "Needs Review"
        return
        
    if has_eval:
        facts.outcome_status = "In Evaluation"
        # Calculate timer
        msg_local = facts.latest_inbound_message.timestamp.astimezone(TIMEZONE_NEW_YORK)
        current_local = current_time.astimezone(TIMEZONE_NEW_YORK)
        due_time = msg_local + timedelta(hours=48)
        
        if current_local >= due_time:
            facts.in_evaluation_timer_status = "Follow-up Due"
        else:
            facts.in_evaluation_timer_status = "In Evaluation"
            
    elif has_feedback:
        facts.outcome_status = "Feedback"
    else:
        # Generic acknowledgements fall here and stay None (which maps to Needs Review/Remainder)
        pass
