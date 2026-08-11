"""Deterministic interview date, time, and timezone detection parser.

Strictly follows confirmed business rules:
1. Direct scheduling instruction ("Please schedule...", "Interview is scheduled for...") -> "Interview Scheduled", "Confirmed from thread"
2. Availability ("Candidate is available...") -> "Interview Awaiting Confirmation", "Awaiting confirmation"
3. Later confirmation reply ("Confirmed", "That time works", calendar invite) -> promotes proposed slot to "Interview Scheduled", "Confirmed from thread"
4. Changed proposed slot -> treated as unconfirmed availability until confirmed
5. Missing timezone -> uses sender's known timezone if available; flags review if unavailable
6. Conflicts -> multiple active confirmed times flag "Schedule conflict"
7. Cancellations/reschedules ("Interview cancelled", "Please reschedule") -> invalidates older confirmed time safely
8. Default year -> 2026 when year is omitted in dates
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re
from typing import Any, Dict, List, Optional
from backend.app.domain.date_utils import TIMEZONE_NEW_YORK
from backend.app.domain.text_cleaner import clean_email_text
from backend.app.domain.message_facts import is_automatic_reply


def strip_quoted_history(text: Any) -> str:
    """Strips quoted email thread headers to evaluate only fresh message content."""
    if not text:
        return ""
    if isinstance(text, dict):
        text = text.get("content") or text.get("bodyPreview") or ""
    if not isinstance(text, str):
        return ""
    markers = [
        "-----Original Message-----",
        "----- Original Message -----",
        "From:",
        "On ",
        "wrote:",
    ]
    lines = text.splitlines()
    clean_lines = []
    for line in lines:
        if any(marker in line for marker in markers) and len(clean_lines) > 0:
            break
        clean_lines.append(line)
    return "\n".join(clean_lines).strip()


def parse_explicit_datetime(text: str, message_timestamp: datetime) -> Optional[datetime]:
    slot = parse_slot_from_text(text, message_timestamp, "", "")
    return slot.dt if slot else None


def evaluate_interview_status(facts: Any, current_time: datetime) -> None:
    msgs = []
    if getattr(facts, "latest_inbound_message", None):
        m = facts.latest_inbound_message
        msgs.append({
            "body_preview": getattr(m, "body_preview", ""),
            "sender": getattr(m, "sender_email", ""),
            "timestamp": getattr(m, "timestamp", current_time),
        })
    elif getattr(facts, "inbound_messages", None):
        for m in facts.inbound_messages:
            msgs.append({
                "body_preview": getattr(m, "body_preview", ""),
                "sender": getattr(m, "sender_email", ""),
                "timestamp": getattr(m, "timestamp", current_time),
            })
    res = evaluate_thread_interview_details(msgs, current_time)
    if res.confidence_label is None:
        raw_text = msgs[0]["body_preview"] if msgs else ""
        unquoted = strip_quoted_history(raw_text)
        clean = clean_email_text(unquoted)
        exp_dates = list(re.finditer(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2})", clean, re.IGNORECASE))
        rel_dates = list(re.finditer(r"\b(today|tomorrow)\b", clean, re.IGNORECASE))
        wd_dates = list(re.finditer(r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b", clean, re.IGNORECASE))
        if (len(exp_dates) + len(rel_dates) + len(wd_dates)) > 1 or "reschedule" in clean.lower():
            facts.interview_status = "Needs Review"
        else:
            facts.interview_status = None
    else:
        facts.interview_status = res.interview_status
    if res.interview_datetime:
        try:
            facts.interview_datetime = datetime.fromisoformat(res.interview_datetime)
        except Exception:
            pass


@dataclass
class ParsedSlot:
    dt: datetime
    date_str: str  # YYYY-MM-DD
    time_str: str  # HH:MM
    timezone_str: Optional[str]
    timezone_source: Optional[str]  # "message_text" | "sender_metadata" | None
    raw_text: str
    message_id: str
    sender: str
    is_direct_command: bool = False
    is_calendar_invite: bool = False


@dataclass
class InterviewDetectionResult:
    interview_status: str  # "Interview Scheduled", "Interview Awaiting Confirmation", "Interview Request", "Needs Review"
    interview_datetime: Optional[str] = None  # ISO format string
    interview_date: Optional[str] = None  # YYYY-MM-DD
    interview_time: Optional[str] = None  # HH:MM
    timezone: Optional[str] = None
    timezone_source: Optional[str] = None
    confidence_label: Optional[str] = None  # "Confirmed from thread", "Awaiting confirmation", "Schedule conflict"
    supporting_message_ids: List[str] = field(default_factory=list)


TIMEZONE_PATTERNS = [
    (r"\b(EST|EDT|Eastern\s+Time|ET)\b", "EST"),
    (r"\b(CST|CDT|Central\s+Time|CT)\b", "CST"),
    (r"\b(PST|PDT|Pacific\s+Time|PT)\b", "PST"),
    (r"\b(MST|MDT|Mountain\s+Time|MT)\b", "MST"),
    (r"\b(UTC|GMT)\b", "UTC"),
]


def extract_timezone(text: str) -> Optional[str]:
    for pattern, tz_code in TIMEZONE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return tz_code
    return None


def parse_slot_from_text(
    text: str,
    message_timestamp: datetime,
    message_id: str,
    sender: str,
    sender_tz_map: Optional[Dict[str, str]] = None,
) -> Optional[ParsedSlot]:
    """Parse candidate date, time, and timezone from email snippet."""
    unquoted = strip_quoted_history(text)
    clean = clean_email_text(unquoted)
    lower = clean.lower()

    if not clean:
        return None

    # Time pattern: e.g. 4 PM, 4:00 PM, 16:00
    time_pattern = r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM|am|pm)?"
    time_matches = []
    for m in re.finditer(time_pattern, clean):
        start, end = m.span()
        sub = clean[start:end].strip()
        has_ampm = bool(m.group(3))
        has_colon = bool(m.group(2))
        prefix_at = bool(re.search(r"\bat\s+" + re.escape(sub) + r"\b", clean, re.IGNORECASE))
        if has_ampm or has_colon or prefix_at:
            h = int(m.group(1))
            if 1 <= h <= 24:
                time_matches.append(m)

    if not time_matches:
        return None

    tm = time_matches[0]
    hour = int(tm.group(1))
    minute = int(tm.group(2) or 0)
    ampm = (tm.group(3) or "").upper()

    if ampm == "PM" and hour < 12:
        hour += 12
    elif ampm == "AM" and hour == 12:
        hour = 0
    elif not ampm and 1 <= hour <= 7:
        hour += 12

    # Count date matches to detect conflicting dates in a single snippet
    exp_dates = list(re.finditer(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?", clean, re.IGNORECASE))
    rel_dates = list(re.finditer(r"\b(today|tomorrow)\b", clean, re.IGNORECASE))
    wd_dates = list(re.finditer(r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b", clean, re.IGNORECASE))

    total_dates = len(exp_dates) + len(rel_dates) + len(wd_dates)
    if total_dates > 1:
        return None

    explicit_date = exp_dates[0] if exp_dates else None
    iso_date = re.search(r"(\d{4})-(\d{2})-(\d{2})", clean)
    slash_date = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", clean)
    rel_date = rel_dates[0] if rel_dates else None
    wd_date = wd_dates[0] if wd_dates else None

    msg_local = message_timestamp.astimezone(TIMEZONE_NEW_YORK)
    target_year = 2026
    target_month = msg_local.month
    target_day = msg_local.day

    if iso_date:
        target_year = int(iso_date.group(1))
        target_month = int(iso_date.group(2))
        target_day = int(iso_date.group(3))
    elif explicit_date:
        m_str = explicit_date.group(1).capitalize()
        target_day = int(explicit_date.group(2))
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        target_month = months.index(m_str) + 1
        target_year = 2026
    elif slash_date:
        target_month = int(slash_date.group(1))
        target_day = int(slash_date.group(2))
        if slash_date.group(3):
            y_raw = int(slash_date.group(3))
            target_year = y_raw + 2000 if y_raw < 100 else y_raw
        else:
            target_year = 2026
    elif rel_date:
        r_str = rel_date.group(1).lower()
        dt_rel = msg_local if r_str == "today" else msg_local + timedelta(days=1)
        target_year = dt_rel.year
        target_month = dt_rel.month
        target_day = dt_rel.day
    elif wd_date:
        wd_str = wd_date.group(1).lower()
        weekdays = {
            "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "wednesday": 2, "wed": 2,
            "thursday": 3, "thu": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5,
            "sunday": 6, "sun": 6
        }
        target_wd = weekdays[wd_str]
        cur_wd = msg_local.weekday()
        days_ahead = target_wd - cur_wd
        if days_ahead <= 0:
            days_ahead += 7
        dt_wd = msg_local + timedelta(days=days_ahead)
        target_year = 2026 if dt_wd.year < 2026 else dt_wd.year
        target_month = dt_wd.month
        target_day = dt_wd.day
    else:
        target_year = 2026
        target_month = msg_local.month
        target_day = msg_local.day

    try:
        dt = datetime(target_year, target_month, target_day, hour, minute, tzinfo=TIMEZONE_NEW_YORK)
    except ValueError:
        return None

    tz_text = extract_timezone(clean)
    tz_source = "message_text" if tz_text else None

    if not tz_text and sender_tz_map:
        sender_clean = sender.lower().strip()
        for domain_or_email, known_tz in sender_tz_map.items():
            if domain_or_email in sender_clean:
                tz_text = known_tz
                tz_source = "sender_metadata"
                break

    if not tz_text:
        if "@tcs.com" in sender.lower() or "@clifyx.com" in sender.lower():
            tz_text = "EST"
            tz_source = "sender_metadata"

    is_direct = any(
        phrase in lower
        for phrase in [
            "please schedule the interview for",
            "please schedule for",
            "interview is scheduled for",
            "please arrange the interview on",
            "scheduled for",
            "interview confirmed for",
            "confirm the interview for",
            "invite sent",
        ]
    )

    is_cal = any(
        phrase in lower
        for phrase in ["calendar invite", "invite sent for", "ics attachment", ".ics", "meeting request"]
    )

    date_str = f"{target_year:04d}-{target_month:02d}-{target_day:02d}"
    time_str = f"{hour:02d}:{minute:02d}"

    return ParsedSlot(
        dt=dt,
        date_str=date_str,
        time_str=time_str,
        timezone_str=tz_text,
        timezone_source=tz_source,
        raw_text=clean,
        message_id=message_id,
        sender=sender,
        is_direct_command=is_direct,
        is_calendar_invite=is_cal,
    )


def evaluate_thread_interview_details(
    thread_messages: List[Dict[str, Any]],
    current_time: datetime,
    sender_tz_map: Optional[Dict[str, str]] = None,
) -> InterviewDetectionResult:
    """Evaluates multi-turn thread messages to detect confirmed interviews or unconfirmed availability."""
    if not thread_messages:
        return InterviewDetectionResult(interview_status="Needs Review")

    def get_msg_time(m: Dict[str, Any]) -> datetime:
        raw = (
            m.get("timestamp")
            or m.get("received_at")
            or m.get("receivedDateTime")
            or m.get("sentDateTime")
            or ""
        )
        if isinstance(raw, datetime):
            return raw
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except Exception:
            return current_time

    sorted_msgs = sorted(thread_messages, key=get_msg_time)

    proposed_slot: Optional[ParsedSlot] = None
    confirmed_slots: List[ParsedSlot] = []
    has_cancellation = False
    has_request_terms = False
    has_unquoted_content = False

    confirm_keywords = [
        "confirmed",
        "yes, available",
        "that time works",
        "please proceed",
        "interview is confirmed",
        "sounds good",
        "works for me",
        "slot works",
        "we are confirmed",
    ]

    cancel_keywords = [
        "interview cancelled",
        "interview canceled",
        "please reschedule",
        "panel is unavailable",
        "move it to",
        "cancelled",
        "canceled",
        "reschedule",
    ]

    request_terms = [
        "availability",
        "when are they free",
        "what times work",
        "provide times",
        "available to interview",
        "time to speak",
    ]

    for m in sorted_msgs:
        msg_id = m.get("graph_immutable_id") or m.get("entry_id") or m.get("id") or ""
        sender = m.get("sender") or m.get("sender_email") or ""
        raw_text = m.get("body_preview") or m.get("body") or m.get("subject") or m.get("bodyPreview") or ""
        if is_automatic_reply(sender, raw_text, m):
            continue

        unquoted = strip_quoted_history(raw_text)
        clean_text = clean_email_text(unquoted)
        lower_text = clean_text.lower()
        msg_ts = get_msg_time(m)

        if clean_text:
            has_unquoted_content = True

        if any(term in lower_text for term in request_terms):
            has_request_terms = True

        if any(term in lower_text for term in cancel_keywords):
            has_cancellation = True
            confirmed_slots.clear()
            proposed_slot = None

        slot = parse_slot_from_text(unquoted, msg_ts, msg_id, sender, sender_tz_map)

        if slot:
            has_cancellation = False
            if slot.is_direct_command or slot.is_calendar_invite:
                confirmed_slots.append(slot)
                proposed_slot = slot
            else:
                proposed_slot = slot

        if proposed_slot and not slot and any(term in lower_text for term in confirm_keywords):
            if proposed_slot not in confirmed_slots:
                confirmed_slots.append(proposed_slot)

    if not has_unquoted_content:
        return InterviewDetectionResult(interview_status="Needs Review", confidence_label=None)

    if len(confirmed_slots) > 1:
        unique_times = {(s.date_str, s.time_str) for s in confirmed_slots}
        if len(unique_times) > 1:
            latest = confirmed_slots[-1]
            return InterviewDetectionResult(
                interview_status="Needs Review",
                interview_datetime=latest.dt.isoformat(),
                interview_date=latest.date_str,
                interview_time=latest.time_str,
                timezone=latest.timezone_str,
                timezone_source=latest.timezone_source,
                confidence_label="Schedule conflict",
                supporting_message_ids=[s.message_id for s in confirmed_slots if s.message_id],
            )

    if confirmed_slots:
        active = confirmed_slots[-1]
        if not active.timezone_str:
            return InterviewDetectionResult(
                interview_status="Needs Review",
                interview_datetime=active.dt.isoformat(),
                interview_date=active.date_str,
                interview_time=active.time_str,
                timezone=None,
                timezone_source=None,
                confidence_label="Needs Review",
                supporting_message_ids=[active.message_id] if active.message_id else [],
            )

        current_local = current_time.astimezone(TIMEZONE_NEW_YORK)
        end_time_local = active.dt + timedelta(hours=1)
        
        if current_local >= end_time_local:
            status_code = "Interview Completed"
        else:
            status_code = "Interview Scheduled"

        return InterviewDetectionResult(
            interview_status=status_code,
            interview_datetime=active.dt.isoformat(),
            interview_date=active.date_str,
            interview_time=active.time_str,
            timezone=active.timezone_str,
            timezone_source=active.timezone_source,
            confidence_label="Confirmed from thread",
            supporting_message_ids=[active.message_id] if active.message_id else [],
        )

    if has_cancellation or any(term in lower_text for term in ["reschedule", "please reschedule", "interview cancelled", "panel is unavailable"]) and not confirmed_slots:
        return InterviewDetectionResult(
            interview_status="Needs Review",
            confidence_label=None,
        )

    if proposed_slot and not has_cancellation:
        return InterviewDetectionResult(
            interview_status="Interview Awaiting Confirmation",
            interview_datetime=proposed_slot.dt.isoformat(),
            interview_date=proposed_slot.date_str,
            interview_time=proposed_slot.time_str,
            timezone=proposed_slot.timezone_str,
            timezone_source=proposed_slot.timezone_source,
            confidence_label="Awaiting confirmation",
            supporting_message_ids=[proposed_slot.message_id] if proposed_slot.message_id else [],
        )

    if has_request_terms and not has_cancellation:
        return InterviewDetectionResult(
            interview_status="Interview Request",
            confidence_label="Awaiting confirmation",
        )

    return InterviewDetectionResult(
        interview_status="Needs Review",
        confidence_label=None,
    )
