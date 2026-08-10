"""
Automated unit tests for encrypted SQLite persistence and idempotent upsert.
"""

import os
import tempfile
import pytest
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.models import DomainStatus


@pytest.fixture
def temp_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_records.db")
        engine = EncryptedPersistenceEngine(db_path=db_path, master_key="test_master_key_123")
        yield engine


def test_idempotent_upsert_and_duplicate_prevention(temp_persistence):
    """Verify upsert_submission creates a new record and skips duplicates idempotently."""
    engine = temp_persistence
    record_id = "rec-001"
    graph_immutable_id = "immutable-id-12345"
    conversation_id = "conv-id-67890"

    payload = {"sample": "data", "candidate": "John Doe"}

    # First insert -> is_new = True, is_duplicate = False
    is_new, is_dup = engine.upsert_submission(
        record_id=record_id,
        graph_immutable_id=graph_immutable_id,
        conversation_id=conversation_id,
        job_id="JOB-100",
        ep_reference="EP-200",
        candidate_name="John Doe",
        tcs_eligibility="eligible",
        domain_status=DomainStatus.NEW_SUBMISSION.value,
        received_at="2026-07-15T12:00:00Z",
        created_at="2026-07-15T12:05:00Z",
        payload_data=payload
    )

    assert is_new is True
    assert is_dup is False

    # Second insert with SAME immutable_id -> is_new = False, is_duplicate = True
    is_new_2, is_dup_2 = engine.upsert_submission(
        record_id="rec-002",
        graph_immutable_id=graph_immutable_id,
        conversation_id=conversation_id,
        job_id="JOB-100",
        ep_reference="EP-200",
        candidate_name="John Doe",
        tcs_eligibility="eligible",
        domain_status=DomainStatus.NEW_SUBMISSION.value,
        received_at="2026-07-15T12:00:00Z",
        created_at="2026-07-15T12:05:00Z",
        payload_data=payload
    )

    assert is_new_2 is False
    assert is_dup_2 is True

    # Verify only 1 record exists in list_records
    records = engine.list_records()
    assert len(records) == 1
    assert records[0].graph_immutable_id == graph_immutable_id

def test_timeline_unique_body_fallback(temp_persistence):
    """Verify that uniqueBody.content is preferred for timeline body_preview, falling back to bodyPreview."""
    engine = temp_persistence
    
    # We will test the static method _linked_message_to_timeline
    from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
    
    mock_messages = [
        {
            "id": "msg-1",
            "internetMessageId": "<msg-1@test.com>",
            "sentDateTime": "2026-08-07T10:00:00Z",
            "from": {"emailAddress": {"address": "test@test.com"}},
            "bodyPreview": "Short preview...",
            "uniqueBody": {"content": "This is the unique body."}
        },
        {
            "id": "msg-2",
            "internetMessageId": "<msg-2@test.com>",
            "sentDateTime": "2026-08-07T10:05:00Z",
            "from": {"emailAddress": {"address": "test@test.com"}},
            "bodyPreview": "Fallback preview...",
            # uniqueBody missing
        },
        {
            "id": "msg-3",
            "internetMessageId": "<msg-3@test.com>",
            "sentDateTime": "2026-08-07T10:10:00Z",
            "from": {"emailAddress": {"address": "test@test.com"}},
            "bodyPreview": "Another fallback preview...",
            "uniqueBody": {"content": ""}  # uniqueBody empty
        },
        {
            "id": "msg-4",
            "internetMessageId": "<msg-4@test.com>",
            "sentDateTime": "2026-08-07T10:15:00Z",
            "from": {"emailAddress": {"address": "test@test.com"}},
            "bodyPreview": "Whitespace fallback preview...",
            "uniqueBody": {"content": "   \n\t "}  # uniqueBody whitespace only
        }
    ]
    
    timeline = engine._build_timeline_from_thread_messages(
        record_id="rec-001",
        conversation_id="conv-001",
        thread_messages=mock_messages,
        role="original_submission"
    )
    
    assert len(timeline) == 4
    assert timeline[0].body_preview == "This is the unique body."
    assert timeline[1].body_preview == "Fallback preview..."
    assert timeline[2].body_preview == "Another fallback preview..."
    assert timeline[3].body_preview == "Whitespace fallback preview..."
