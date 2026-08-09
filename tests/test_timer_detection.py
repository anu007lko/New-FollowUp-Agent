import pytest
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from backend.app.domain.models import MessageDirection, MessageFact, ConversationFacts
from backend.app.domain.message_facts import evaluate_no_response_timers
from backend.app.domain.date_utils import TIMEZONE_NEW_YORK

def create_fact(direction, timestamp_str, msg_id="id"):
    return MessageFact(
        graph_immutable_id=msg_id,
        timestamp=datetime.fromisoformat(timestamp_str),
        sender_email="test@test.com",
        direction=direction,
        is_meaningful=(direction in [MessageDirection.ORIGINAL_SUBMISSION, MessageDirection.SENT_MESSAGE, MessageDirection.INBOUND_MESSAGE])
    )

def test_evaluate_no_response_timers_inbound_priority():
    facts = ConversationFacts()
    facts.has_meaningful_inbound_response = True
    
    evaluate_no_response_timers(facts, datetime.now(timezone.utc), [])
    
    assert facts.no_response_status == "Requires Classification"
    assert facts.timer_anchor_message is None

def test_evaluate_no_response_timers_no_original_submission():
    facts = ConversationFacts()
    facts.messages = [create_fact(MessageDirection.SENT_MESSAGE, "2026-08-01T10:00:00+00:00")]
    
    evaluate_no_response_timers(facts, datetime.now(timezone.utc), [])
    
    assert facts.timer_anchor_message is None
    assert facts.no_response_status is None

def test_evaluate_no_response_timers_under_and_over_48h():
    # 2026-08-01 10:00:00 EDT is 2026-08-01 14:00:00 UTC
    anchor_dt_str = "2026-08-01T14:00:00+00:00"
    original = create_fact(MessageDirection.ORIGINAL_SUBMISSION, anchor_dt_str)
    
    facts = ConversationFacts()
    facts.messages = [original]
    
    # 47 hours later -> Awaiting Response
    current_time_47 = datetime.fromisoformat("2026-08-03T13:00:00+00:00")
    evaluate_no_response_timers(facts, current_time_47, [])
    assert facts.timer_anchor_message == original
    assert facts.no_response_status == "Awaiting Response"
    
    # Exactly 48 hours later -> Follow-up Due
    current_time_48 = datetime.fromisoformat("2026-08-03T14:00:00+00:00")
    evaluate_no_response_timers(facts, current_time_48, [])
    assert facts.no_response_status == "Follow-up Due"
    
    # 49 hours later -> Follow-up Due
    current_time_49 = datetime.fromisoformat("2026-08-03T15:00:00+00:00")
    evaluate_no_response_timers(facts, current_time_49, [])
    assert facts.no_response_status == "Follow-up Due"

def test_evaluate_no_response_timers_dst_boundary():
    # March 8, 2026 is DST start in US. 2:00 AM becomes 3:00 AM.
    # So if anchor is March 7 10:00 AM EST, 48 calendar hours is March 9 10:00 AM EDT.
    # March 7 10:00 EST = 15:00 UTC
    # March 9 10:00 EDT = 14:00 UTC
    # Total elapsed UTC hours = 47. But local time elapsed is 48.
    
    original = create_fact(MessageDirection.ORIGINAL_SUBMISSION, "2026-03-07T15:00:00+00:00")
    facts = ConversationFacts()
    facts.messages = [original]
    
    # 47 UTC hours later = March 9 10:00 EDT
    current_time_dst = datetime.fromisoformat("2026-03-09T14:00:00+00:00")
    evaluate_no_response_timers(facts, current_time_dst, [])
    assert facts.no_response_status == "Follow-up Due"

def test_evaluate_no_response_timers_uncertain_follow_up():
    original = create_fact(MessageDirection.ORIGINAL_SUBMISSION, "2026-08-01T14:00:00+00:00")
    sent = create_fact(MessageDirection.SENT_MESSAGE, "2026-08-02T14:00:00+00:00", msg_id="uncertain_id")
    
    facts = ConversationFacts()
    facts.messages = [original, sent]
    
    # current time is 48h after original, but only 24h after sent.
    # since 'uncertain_id' is NOT in authoritative followup ids, we ignore it for anchor, but flag it
    current_time = datetime.fromisoformat("2026-08-03T14:00:00+00:00")
    evaluate_no_response_timers(facts, current_time, [])
    
    assert facts.timer_anchor_message == original
    assert facts.followup_anchor_requires_review == True
    assert facts.no_response_status == "Follow-up Due"

def test_evaluate_no_response_timers_authoritative_follow_up():
    original = create_fact(MessageDirection.ORIGINAL_SUBMISSION, "2026-08-01T14:00:00+00:00")
    sent = create_fact(MessageDirection.SENT_MESSAGE, "2026-08-02T14:00:00+00:00", msg_id="auth_id")
    
    facts = ConversationFacts()
    facts.messages = [original, sent]
    
    # 'auth_id' is an authoritative follow-up, so it becomes the anchor.
    # current time is 48h after original, but only 24h after authoritative anchor.
    current_time = datetime.fromisoformat("2026-08-03T14:00:00+00:00")
    evaluate_no_response_timers(facts, current_time, ["auth_id"])
    
    assert facts.timer_anchor_message == sent
    assert facts.followup_anchor_requires_review == False
    assert facts.no_response_status == "Awaiting Response"

def test_evaluate_no_response_timers_auto_reply_ignored():
    original = create_fact(MessageDirection.ORIGINAL_SUBMISSION, "2026-08-01T14:00:00+00:00")
    auto_reply = create_fact(MessageDirection.AUTOMATIC_REPLY, "2026-08-01T14:05:00+00:00")
    
    facts = ConversationFacts()
    facts.messages = [original, auto_reply]
    
    current_time = datetime.fromisoformat("2026-08-03T14:00:00+00:00")
    evaluate_no_response_timers(facts, current_time, [])
    
    assert facts.timer_anchor_message == original
    assert facts.no_response_status == "Follow-up Due"
