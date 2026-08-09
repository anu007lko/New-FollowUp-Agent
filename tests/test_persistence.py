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
