import pytest
from datetime import datetime, timezone
from backend.app.domain.models import MessageDirection
from backend.app.domain.message_facts import analyze_conversation

def test_same_logical_message_copied():
    # Two messages, same internetMessageId, different graph IDs
    source_id = "graph_1"
    thread = [
        {
            "id": "graph_1",
            "internetMessageId": "<email123@test>",
            "sentDateTime": "2026-08-01T10:00:00Z",
            "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
        },
        {
            "id": "graph_2",
            "internetMessageId": "<email123@test>",
            "sentDateTime": "2026-08-01T10:00:05Z",  # Slightly different timestamp or same doesn't matter
            "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
        }
    ]
    facts = analyze_conversation(source_id, thread)
    
    assert len(facts.messages) == 1
    msg = facts.messages[0]
    assert msg.direction == MessageDirection.ORIGINAL_SUBMISSION
    assert msg.internet_message_id == "<email123@test>"
    # Since graph_1 is source_id, it should be the primary graph_immutable_id
    assert msg.graph_immutable_id == "graph_1"
    assert "graph_2" in msg.duplicate_immutable_ids

def test_same_timestamp_different_imid():
    source_id = "graph_1"
    thread = [
        {
            "id": "graph_1",
            "internetMessageId": "<email123@test>",
            "sentDateTime": "2026-08-01T10:00:00Z",
            "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
        },
        {
            "id": "graph_2",
            "internetMessageId": "<email456@test>",
            "sentDateTime": "2026-08-01T10:00:00Z",
            "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
        }
    ]
    facts = analyze_conversation(source_id, thread)
    assert len(facts.messages) == 2
    assert facts.messages[0].graph_immutable_id == "graph_1"
    assert facts.messages[1].graph_immutable_id == "graph_2"

def test_genuine_later_sent_message():
    source_id = "graph_1"
    thread = [
        {
            "id": "graph_1",
            "internetMessageId": "<email123@test>",
            "sentDateTime": "2026-08-01T10:00:00Z",
            "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
        },
        {
            "id": "graph_2",
            "internetMessageId": "<email456@test>",
            "sentDateTime": "2026-08-02T10:00:00Z",
            "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
        }
    ]
    facts = analyze_conversation(source_id, thread)
    assert len(facts.messages) == 2
    assert facts.messages[0].direction == MessageDirection.ORIGINAL_SUBMISSION
    assert facts.messages[1].direction == MessageDirection.SENT_MESSAGE

def test_missing_malformed_imid():
    source_id = "graph_1"
    thread = [
        {
            "id": "graph_1",
            "internetMessageId": "",
            "sentDateTime": "2026-08-01T10:00:00Z",
            "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
        },
        {
            "id": "graph_2",
            "internetMessageId": "invalid_no_brackets",
            "sentDateTime": "2026-08-01T10:05:00Z",
            "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
        }
    ]
    facts = analyze_conversation(source_id, thread)
    assert len(facts.messages) == 2
    assert facts.logical_copy_requires_review is True
