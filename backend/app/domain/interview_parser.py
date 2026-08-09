import re
from datetime import datetime, timedelta
from backend.app.domain.models import ConversationFacts, MessageFact
from backend.app.domain.text_cleaner import clean_email_text
from backend.app.domain.date_utils import TIMEZONE_NEW_YORK

def parse_explicit_datetime(text: str, message_timestamp: datetime) -> datetime | None:
    """
    Very conservative datetime parser supporting relative dates.
    Requires Time and explicit timezone (EST, EDT, Eastern Time).
    Anchors relative dates to the message_timestamp.
    Returns a timezone-aware datetime in America/New_York.
    """
    # 1. Base time pattern extraction (e.g. 3pm EST, 3:00 PM Eastern Time)
    time_pattern = r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM|am|pm)\s*(EST|EDT|Eastern\s+Time)"
    
    # 2. Date pattern extraction
    # Explicit dates: Month Day
    explicit_date_pattern = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?"
    # Relative dates
    relative_pattern = r"(today|tomorrow)"
    # Weekdays
    weekday_pattern = r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Wed|Thu|Fri|Sat|Sun)"
    
    # Let's count time matches to ensure only 1 unambiguous time
    time_matches = list(re.finditer(time_pattern, text, flags=re.IGNORECASE))
    if len(time_matches) != 1:
        return None
        
    time_match = time_matches[0]
    hour = int(time_match.group(1))
    minute = int(time_match.group(2) or 0)
    ampm = time_match.group(3).upper()
    
    if ampm == "PM" and hour < 12:
        hour += 12
    elif ampm == "AM" and hour == 12:
        hour = 0
        
    # Determine base date
    msg_local = message_timestamp.astimezone(TIMEZONE_NEW_YORK)
    target_date = None
    
    # Search for dates
    exp_dates = list(re.finditer(explicit_date_pattern, text, flags=re.IGNORECASE))
    rel_dates = list(re.finditer(relative_pattern, text, flags=re.IGNORECASE))
    wd_dates = list(re.finditer(weekday_pattern, text, flags=re.IGNORECASE))
    
    total_dates = len(exp_dates) + len(rel_dates) + len(wd_dates)
    if total_dates == 0:
        return None
    if total_dates > 1:
        # Conflicting/multiple dates
        return None
        
    if exp_dates:
        month_str = exp_dates[0].group(1).capitalize()
        day = int(exp_dates[0].group(2))
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        month = months.index(month_str) + 1
        year = msg_local.year
        if month < msg_local.month:
            year += 1 # Assume next year if month is in past
        target_date = msg_local.replace(year=year, month=month, day=day)
    elif rel_dates:
        rel = rel_dates[0].group(1).lower()
        if rel == "today":
            target_date = msg_local
        elif rel == "tomorrow":
            target_date = msg_local + timedelta(days=1)
    elif wd_dates:
        wd_str = wd_dates[0].group(1).lower()
        weekdays = {"monday":0, "mon":0, "tuesday":1, "tue":1, "wednesday":2, "wed":2, 
                    "thursday":3, "thu":3, "friday":4, "fri":4, "saturday":5, "sat":5, "sunday":6, "sun":6}
        target_wd = weekdays[wd_str]
        current_wd = msg_local.weekday()
        days_ahead = target_wd - current_wd
        if days_ahead <= 0: # Target is next week
            days_ahead += 7
        target_date = msg_local + timedelta(days=days_ahead)
        
    if not target_date:
        return None
        
    try:
        dt = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return dt
    except ValueError:
        return None

def evaluate_interview_status(facts: ConversationFacts, current_time: datetime) -> None:
    """
    Evaluates interview status deterministically.
    Modifies facts in place.
    """
    if not facts.latest_inbound_message:
        return
        
    raw_text = facts.latest_inbound_message.body_preview or ""
    clean_text = clean_email_text(raw_text)
    
    # Ambiguity check
    lower_text = clean_text.lower()
    ambiguous_terms = ["cancel", "reschedule", "conflict", "tentative"]
    if any(term in lower_text for term in ambiguous_terms):
        facts.interview_status = "Needs Review"
        return
        
    # Look for Scheduled
    parsed_dt = parse_explicit_datetime(clean_text, facts.latest_inbound_message.timestamp)
    if parsed_dt:
        # Require confirmation phrasing for scheduled
        conf_phrases = ["invite sent", "interview confirmed", "scheduled for", "calendar invite", "scheduled tomorrow", "today"]
        if any(p in lower_text for p in conf_phrases) or parse_explicit_datetime(clean_text, facts.latest_inbound_message.timestamp):
            # parse_explicit_datetime guarantees an explicit date and time and timezone.
            facts.interview_datetime = parsed_dt
            current_local = current_time.astimezone(TIMEZONE_NEW_YORK)
            if parsed_dt > current_local:
                facts.interview_status = "Interview Scheduled"
            else:
                facts.interview_status = "Interview Awaiting Confirmation"
            return
        
    # Look for Request
    request_terms = [
        "availability", "when are they free", "what times work", 
        "provide times", "available to interview", "time to speak"
    ]
    if any(term in lower_text for term in request_terms):
        facts.interview_status = "Interview Request"
        return
        
    # If it has dates/times but missing timezone, or multiple dates
    time_hints = [r"\d{1,2}:\d{2}", r"(today|tomorrow)", r"\d{1,2}\s*(am|pm)"]
    if any(re.search(hint, clean_text, flags=re.IGNORECASE) for hint in time_hints) and any(term in lower_text for term in ["interview", "speak", "call", "meet"]):
        facts.interview_status = "Needs Review"
        return

    pass
