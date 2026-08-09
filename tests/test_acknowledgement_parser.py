import pytest
from datetime import datetime, timezone
from backend.app.domain.models import MessageDirection, MessageFact, ConversationFacts
from backend.app.domain.acknowledgement_parser import evaluate_acknowledgement_status

def create_inbound_fact(text: str, is_meaningful: bool = True) -> MessageFact:
    return MessageFact(
        graph_immutable_id="id",
        timestamp=datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc),
        sender_email="candidate@test.com",
        direction=MessageDirection.INBOUND_MESSAGE,
        is_meaningful=is_meaningful,
        body_preview=text
    )

def test_receipt_only():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("Received, thank you.")
    evaluate_acknowledgement_status(facts)
    assert facts.outcome_status == "Acknowledgement"

def test_thank_you_acknowledgement():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("Thank you for sharing this profile.")
    evaluate_acknowledgement_status(facts)
    assert facts.outcome_status == "Acknowledgement"

def test_substantive_outcome():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("Received, but we will pass on this candidate.")
    evaluate_acknowledgement_status(facts)
    # Substantive keyword "pass on" overrides acknowledgement
    assert facts.outcome_status == "Needs Review"

def test_unrelated():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("Wrong email, please remove me.")
    evaluate_acknowledgement_status(facts)
    assert facts.outcome_status == "Unrelated"

def test_auto_reply_exclusion():
    facts = ConversationFacts()
    # E.g. OOO message, not meaningful
    facts.latest_inbound_message = create_inbound_fact("Received your message. I am OOO.", is_meaningful=False)
    evaluate_acknowledgement_status(facts)
    assert facts.outcome_status is None

def test_conflicting_ambiguous():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("Received, but this is the wrong email.")
    evaluate_acknowledgement_status(facts)
    assert facts.outcome_status == "Needs Review"

def test_quoted_history_false_positive():
    text = """Nothing here.
-----Original Message-----
From: Recruiter
Thank you for submitting."""
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact(text)
    evaluate_acknowledgement_status(facts)
    assert facts.outcome_status is None

def test_signature_false_positive():
    text = """Let me know.
--
Bob
Received Goods Dept"""
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact(text)
    evaluate_acknowledgement_status(facts)
    assert facts.outcome_status is None
