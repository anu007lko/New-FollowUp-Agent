import pytest
from datetime import datetime, timezone
from backend.app.domain.models import MessageDirection
from backend.app.domain.message_facts import (
    analyze_conversation,
    is_automatic_reply,
    parse_graph_timestamp
)

def test_parse_graph_timestamp():
    # Test valid UTC Graph timestamp
    dt = parse_graph_timestamp("2026-06-15T10:00:00Z")
    assert dt.year == 2026
    assert dt.month == 6
    assert dt.hour == 10
    
    # Test unparseable string returns current UTC fallback
    dt_invalid = parse_graph_timestamp("Invalid date")
    assert dt_invalid is not None

    # By sender
    assert is_automatic_reply("noreply@example.com", "Hello", {}) == True
    assert is_automatic_reply("postmaster@domain.com", "Hello", {}) == True
    assert is_automatic_reply("MicrosoftExchange329e71ec88ae4615bbc36ab6ce41109e", "Delivery failed", {}) == True
    
    # By body
    assert is_automatic_reply("person@example.com", "Out of office until next week", {}) == True
    assert is_automatic_reply("person@example.com", "This is an automatic reply", {}) == True
    assert is_automatic_reply("person@example.com", "Your message to anjaneyareddy.rmkrishnareddy@aexp.com couldn't be delivered.", {}) == True
    assert is_automatic_reply("person@example.com", "anjaneyareddy.rmkrishnareddy wasn't found at aexp.com.", {}) == True
    
    # By item class (NDR)
    assert is_automatic_reply("person@example.com", "Hello", {"itemClass": "IPM.Note.NDR"}) == True
    assert is_automatic_reply("person@example.com", "Hello", {"itemClass": "REPORT.IPM.Note.NDR"}) == True
    
    # False for real messages
    assert is_automatic_reply("person@example.com", "Here is my resume", {"itemClass": "IPM.Note"}) == False

def test_analyze_conversation_identity_and_chronology():
    source_id = "AAMkAGSource123"
    thread_messages = [
        {
            "id": "AAMkAGLater123",
            "sentDateTime": "2026-07-02T10:00:00Z",
            "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
            "bodyPreview": "Following up on this."
        },
        {
            "id": source_id,
            "sentDateTime": "2026-07-01T10:00:00Z",
            "from": {"emailAddress": {"address": "recruiter@agency.com"}},
            "bodyPreview": "Original submission details."
        },
        {
            "id": "AAMkAGInbound123",
            "sentDateTime": "2026-07-03T10:00:00Z",
            "from": {"emailAddress": {"address": "client@domain.com"}},
            "bodyPreview": "We would like to interview this candidate."
        },
    ]
    
    facts = analyze_conversation(source_id, thread_messages)
    
    # Chronology validation
    assert len(facts.messages) == 3
    assert facts.messages[0].graph_immutable_id == source_id
    assert facts.messages[1].graph_immutable_id == "AAMkAGLater123"
    assert facts.messages[2].graph_immutable_id == "AAMkAGInbound123"
    
    # Identity validation
    assert facts.messages[0].direction == MessageDirection.ORIGINAL_SUBMISSION
    assert facts.messages[1].direction == MessageDirection.SENT_MESSAGE
    assert facts.messages[2].direction == MessageDirection.INBOUND_MESSAGE
    
    # Pointers
    assert facts.latest_real_message.graph_immutable_id == "AAMkAGInbound123"
    assert facts.latest_inbound_message.graph_immutable_id == "AAMkAGInbound123"
    assert facts.latest_sent_message.graph_immutable_id == "AAMkAGLater123"
    assert facts.has_meaningful_inbound_response == True
    assert facts.requires_classification == True

def test_analyze_conversation_excludes_auto_replies_from_meaningful():
    source_id = "AAMkAGSource123"
    thread_messages = [
        {
            "id": source_id,
            "sentDateTime": "2026-07-01T10:00:00Z",
            "from": {"emailAddress": {"address": "recruiter@agency.com"}},
        },
        {
            "id": "AAMkAGAutoReply123",
            "sentDateTime": "2026-07-01T10:05:00Z",
            "from": {"emailAddress": {"address": "noreply@domain.com"}},
            "bodyPreview": "Thank you for your email."
        },
    ]
    
    facts = analyze_conversation(source_id, thread_messages)
    assert facts.messages[1].direction == MessageDirection.AUTOMATIC_REPLY
    assert facts.messages[1].is_meaningful == False
    
    # Latest real message should still be the original submission
    assert facts.latest_real_message.graph_immutable_id == source_id
    assert facts.has_meaningful_inbound_response == False

def test_analyze_conversation_unknown_direction_fallback():
    source_id = "AAMkAGSource123"
    thread_messages = [
        {
            "id": "AAMkAGUnknown",
            "sentDateTime": "2026-07-01T10:05:00Z",
            # Missing from/sender info
        },
    ]
    
    facts = analyze_conversation(source_id, thread_messages)
    assert facts.messages[0].direction == MessageDirection.UNKNOWN
    assert facts.messages[0].is_meaningful == False
