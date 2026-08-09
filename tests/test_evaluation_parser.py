import pytest
from datetime import datetime, timezone
from backend.app.domain.models import MessageDirection, MessageFact, ConversationFacts
from backend.app.domain.evaluation_parser import evaluate_in_evaluation_status

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

def test_in_evaluation_within_48_hours():
    facts = ConversationFacts()
    msg_ts = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
    facts.latest_inbound_message = create_inbound_fact("We will update you on the status.", msg_ts)
    
    current = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)
    evaluate_in_evaluation_status(facts, current)
    assert facts.outcome_status == "In Evaluation"
    assert facts.in_evaluation_timer_status == "In Evaluation"

def test_in_evaluation_over_48_hours():
    facts = ConversationFacts()
    msg_ts = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
    facts.latest_inbound_message = create_inbound_fact("Awaiting client feedback.", msg_ts)
    
    current = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc) # exactly 48 hours later
    evaluate_in_evaluation_status(facts, current)
    assert facts.outcome_status == "In Evaluation"
    assert facts.in_evaluation_timer_status == "Follow-up Due"

def test_in_evaluation_dst_boundary():
    facts = ConversationFacts()
    msg_ts = datetime(2026, 3, 7, 15, 0, tzinfo=timezone.utc) # 10 AM EST
    facts.latest_inbound_message = create_inbound_fact("Profile under review.", msg_ts)
    
    # 48 local hours later = Mar 9, 10 AM EDT = 14:00 UTC (47 UTC hours elapsed)
    current = datetime(2026, 3, 9, 14, 0, tzinfo=timezone.utc) 
    evaluate_in_evaluation_status(facts, current)
    assert facts.outcome_status == "In Evaluation"
    assert facts.in_evaluation_timer_status == "Follow-up Due"

def test_feedback():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("Can you provide candidate feedback?")
    evaluate_in_evaluation_status(facts, datetime.now(timezone.utc))
    assert facts.outcome_status == "Feedback"

def test_additional_info():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("We need more info on this candidate.")
    evaluate_in_evaluation_status(facts, datetime.now(timezone.utc))
    assert facts.outcome_status == "Feedback"

def test_conflicting_outcomes():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("We are under evaluation but need interview feedback.")
    evaluate_in_evaluation_status(facts, datetime.now(timezone.utc))
    assert facts.outcome_status == "Needs Review"

def test_conditional_wording():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("We will update you unless they cancel.")
    evaluate_in_evaluation_status(facts, datetime.now(timezone.utc))
    assert facts.outcome_status == "Needs Review"

def test_generic_acknowledgement():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("Thanks, message received.")
    evaluate_in_evaluation_status(facts, datetime.now(timezone.utc))
    assert facts.outcome_status is None

def test_quoted_history_false_positive():
    text = """Thanks.
-----Original Message-----
From: Recruiter
We are awaiting client feedback."""
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact(text)
    evaluate_in_evaluation_status(facts, datetime.now(timezone.utc))
    assert facts.outcome_status is None

def test_signature_false_positive():
    text = """Got it.
--
Alice
Awaiting Feedback Dept"""
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact(text)
    evaluate_in_evaluation_status(facts, datetime.now(timezone.utc))
    assert facts.outcome_status is None
