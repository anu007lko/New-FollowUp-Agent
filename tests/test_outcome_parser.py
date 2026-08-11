import pytest
from datetime import datetime, timezone
from backend.app.domain.models import MessageDirection, MessageFact, ConversationFacts
from backend.app.domain.outcome_parser import evaluate_outcome_status

def create_inbound_fact(text: str) -> MessageFact:
    return MessageFact(
        graph_immutable_id="id",
        timestamp=datetime(2026, 8, 1, tzinfo=timezone.utc),
        sender_email="candidate@test.com",
        direction=MessageDirection.INBOUND_MESSAGE,
        is_meaningful=True,
        body_preview=text
    )

def test_position_closed():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("Unfortunately the position is closed now.")
    evaluate_outcome_status(facts)
    assert facts.outcome_status == "Position Closed"

def test_requirement_closed():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("This requirement is closed, please do not submit profiles.")
    evaluate_outcome_status(facts)
    assert facts.outcome_status == "Position Closed"

def test_rejection():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("We are going to pass on this candidate.")
    evaluate_outcome_status(facts)
    assert facts.outcome_status == "Rejection"


def test_candidate_specific_cannot_consider_is_rejection_not_position_closed():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact(
        "Associate is not having strong Data Platform Engineering, hence we cannot consider the associate"
    )
    evaluate_outcome_status(facts)
    assert facts.outcome_status == "Rejection"

def test_duplicate():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("This is a duplicate submission, we already have them.")
    evaluate_outcome_status(facts)
    assert facts.outcome_status == "Duplicate / Already Submitted"


def test_short_duplicate_response():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("Thanks but duplicate.")
    evaluate_outcome_status(facts)
    assert facts.outcome_status == "Duplicate / Already Submitted"


def test_soft_rejection_not_suitable():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact(
        "The profile is not suitable for our role. Please submit other profiles if you have any."
    )
    evaluate_outcome_status(facts)
    assert facts.outcome_status == "Rejection"


def test_unable_to_consider_further_overrides_polite_ack():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact(
        "Thanks for sharing. The requirement is Cortex AI Tech Lead. Won't be able to consider further."
    )
    evaluate_outcome_status(facts)
    assert facts.outcome_status == "Rejection"


def test_position_on_hold():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact(
        "The position is on hold for now. I will update if it reopens."
    )
    evaluate_outcome_status(facts)
    assert facts.outcome_status == "On Hold"


def test_selected_application_requested():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact(
        "Joicy is selected, please share the application."
    )
    evaluate_outcome_status(facts)
    assert facts.outcome_status == "Selected"

def test_conflicting_outcomes():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("We will pass on this candidate as it is a duplicate submission.")
    evaluate_outcome_status(facts)
    assert facts.outcome_status == "Needs Review"

def test_conditional_wording():
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact("We might reject if the interview goes poorly.")
    evaluate_outcome_status(facts)
    assert facts.outcome_status == "Needs Review"

def test_quoted_history_false_positive():
    text = """Let's wait a bit.
-----Original Message-----
From: Recruiter
Did you reject the candidate?"""
    
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact(text)
    evaluate_outcome_status(facts)
    # The word reject is in the quote. So the main body has no outcome keywords.
    assert facts.outcome_status is None

def test_signature_false_positive():
    text = """Still reviewing.
--
Bob
Director of Filled Roles"""
    
    facts = ConversationFacts()
    facts.latest_inbound_message = create_inbound_fact(text)
    evaluate_outcome_status(facts)
    # The word filled is in the signature.
    assert facts.outcome_status is None
