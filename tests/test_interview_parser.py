import pytest
from datetime import datetime, timezone, timedelta
from backend.app.domain.models import MessageDirection, MessageFact, ConversationFacts
from backend.app.domain.interview_parser import evaluate_interview_status, parse_explicit_datetime

def create_inbound_fact(text: str, timestamp: datetime = None) -> MessageFact:
    if not timestamp:
        timestamp = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
    return MessageFact(
        graph_immutable_id="id",
        timestamp=timestamp,
        sender_email="candidate@test.com",
        direction=MessageDirection.INBOUND_MESSAGE,
        is_meaningful=True,
        body_preview=text
    )

def test_parse_explicit_datetime_relative():
    # Message sent Aug 1 at 10 AM UTC = Aug 1 at 6 AM EDT
    msg_ts = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
    
    # "today 3pm EST"
    dt = parse_explicit_datetime("Invite sent for today 3pm EST", msg_ts)
    assert dt is not None
    assert dt.month == 8
    assert dt.day == 1
    assert dt.hour == 15
    
    # "tomorrow at 10 AM EDT"
    dt2 = parse_explicit_datetime("Interview scheduled tomorrow at 10 AM EDT", msg_ts)
    assert dt2 is not None
    assert dt2.month == 8
    assert dt2.day == 2
    assert dt2.hour == 10

def test_parse_explicit_datetime_month_boundary():
    # Message sent Aug 31 at 10 AM UTC = Aug 31 at 6 AM EDT
    msg_ts = datetime(2026, 8, 31, 10, 0, tzinfo=timezone.utc)
    dt = parse_explicit_datetime("Invite sent for tomorrow 3pm EST", msg_ts)
    assert dt is not None
    assert dt.month == 9
    assert dt.day == 1

def test_parse_explicit_datetime_dst_boundary():
    # Message sent Mar 7, 2026 at 15:00 UTC = 10:00 AM EST
    msg_ts = datetime(2026, 3, 7, 15, 0, tzinfo=timezone.utc)
    dt = parse_explicit_datetime("Tomorrow at 3pm EDT", msg_ts)
    assert dt is not None
    assert dt.month == 3
    assert dt.day == 8
    assert dt.hour == 15

def test_availability_request():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("Please provide times you are available to interview next week.")
    
    current = datetime(2026, 8, 3, tzinfo=timezone.utc)
    evaluate_interview_status(facts, current)
    assert facts.interview_status == "Interview Request"

def test_invite_sent_today():
    facts = ConversationFacts()
    msg_ts = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc) # Aug 1
    facts.latest_inbound_message = create_inbound_fact("Invite sent for today 3pm EST", msg_ts)
    
    # Current time Aug 1 12:00 UTC = 8 AM EDT. Interview is at 3 PM EDT (future)
    current = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    evaluate_interview_status(facts, current)
    assert facts.interview_status == "Interview Scheduled"
    
def test_past_scheduled_interview():
    facts = ConversationFacts()
    msg_ts = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc) # Aug 1
    facts.latest_inbound_message = create_inbound_fact("Invite sent for today 3pm EST", msg_ts)
    
    # Current time Aug 3. Interview was Aug 1 at 3 PM EDT (past)
    current = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    evaluate_interview_status(facts, current)
    assert facts.interview_status == "Interview Completed"

def test_reschedule_ambiguity():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("We need to reschedule the interview for tomorrow at 10 AM EDT.")
    
    current = datetime(2026, 8, 3, tzinfo=timezone.utc)
    evaluate_interview_status(facts, current)
    assert facts.interview_status == "Needs Review"

def test_missing_timezone_needs_review():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("The interview is scheduled for tomorrow at 10 AM.")
    
    current = datetime(2026, 8, 3, tzinfo=timezone.utc)
    evaluate_interview_status(facts, current)
    assert facts.interview_status == "Needs Review"

def test_conflicting_dates():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("Are we meeting today or tomorrow at 10 AM EDT?")
    
    current = datetime(2026, 8, 3, tzinfo=timezone.utc)
    evaluate_interview_status(facts, current)
    assert facts.interview_status == "Needs Review"

def test_quoted_history_false_positive():
    text = """Yes I can do that.
-----Original Message-----
From: Recruiter
Invite sent for today 3pm EST"""
    
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact(text)
    
    current = datetime(2026, 8, 3, tzinfo=timezone.utc)
    evaluate_interview_status(facts, current)
    assert facts.interview_status is None
