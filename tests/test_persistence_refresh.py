import os
import json
import tempfile
import pytest
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.models import DomainStatus

@pytest.fixture
def temp_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_records_refresh.db")
        engine = EncryptedPersistenceEngine(db_path=db_path, master_key="test_master_key_123")
        yield engine

def test_placeholder_becomes_complete_without_duplication(temp_persistence):
    engine = temp_persistence
    record_id = "rec-001"
    graph_id = "immutable-id-1"
    conv_id = "conv-id-1"
    
    # 1. Insert placeholder
    placeholder_payload = {
        "thread_messages": [],
        "attachment_hashes": []
    }
    is_new, is_updated = engine.upsert_submission(
        record_id=record_id,
        graph_immutable_id=graph_id,
        conversation_id=conv_id,
        job_id="J1",
        ep_reference="EP1",
        candidate_name="Alice",
        tcs_eligibility="eligible",
        domain_status=DomainStatus.NEW_SUBMISSION.value,
        received_at="2026-07-10T12:00:00Z",
        created_at="2026-07-10T12:00:00Z",
        payload_data=placeholder_payload
    )
    assert is_new is True
    
    # 2. Refresh with complete data
    complete_payload = {
        "thread_messages": [{"id": "msg1", "bodyPreview": "hello"}],
        "attachment_hashes": ["hash1"]
    }
    is_new, is_updated = engine.upsert_submission(
        record_id=record_id, # ID doesn't matter for refresh, looks up by immutable_id
        graph_immutable_id=graph_id,
        conversation_id=conv_id,
        job_id="J1",
        ep_reference="EP1",
        candidate_name="Alice",
        tcs_eligibility="eligible",
        domain_status=DomainStatus.IN_EVALUATION.value,
        received_at="2026-07-10T12:05:00Z",
        created_at="2026-07-10T12:05:00Z",
        payload_data=complete_payload
    )
    assert is_new is False
    assert is_updated is True
    
    # Verify DB state
    with engine._get_connection() as conn:
        cursor = conn.execute("SELECT payload_ciphertext FROM submission_records WHERE graph_immutable_id = ?", (graph_id,))
        row = cursor.fetchone()
        payload = json.loads(engine.encryptor.decrypt(row["payload_ciphertext"]))
        assert len(payload["thread_messages"]) == 1
        assert payload["thread_messages"][0]["id"] == "msg1"
        assert len(payload["attachment_hashes"]) == 1
        
def test_rerun_adds_no_duplicate_messages_or_attachments(temp_persistence):
    engine = temp_persistence
    graph_id = "immutable-id-2"
    
    payload = {
        "thread_messages": [{"id": "msg1"}],
        "attachment_hashes": ["hash1"]
    }
    engine.upsert_submission("r2", graph_id, "c2", "J2", "EP2", "Bob", "eligible", DomainStatus.NEW_SUBMISSION.value, "time", "time", payload)
    
    # Rerun with exact same payload
    is_new, is_updated = engine.upsert_submission("r2", graph_id, "c2", "J2", "EP2", "Bob", "eligible", DomainStatus.NEW_SUBMISSION.value, "time", "time", payload)
    
    with engine._get_connection() as conn:
        cursor = conn.execute("SELECT payload_ciphertext FROM submission_records WHERE graph_immutable_id = ?", (graph_id,))
        row = cursor.fetchone()
        dec_payload = json.loads(engine.encryptor.decrypt(row["payload_ciphertext"]))
        
        # Still only 1 message and 1 attachment
        assert len(dec_payload["thread_messages"]) == 1
        assert dec_payload["thread_message_count"] == 1
        assert len(dec_payload["attachment_hashes"]) == 1

def test_newer_conversation_message_updates_record(temp_persistence):
    engine = temp_persistence
    graph_id = "immutable-id-3"
    
    # Original
    payload = {
        "thread_messages": [{"id": "msg1"}]
    }
    engine.upsert_submission("r3", graph_id, "c3", "J3", "EP3", "Carol", "eligible", DomainStatus.NEW_SUBMISSION.value, "time", "time", payload)
    
    # New message arrives
    new_payload = {
        "thread_messages": [{"id": "msg1"}, {"id": "msg2"}]
    }
    engine.upsert_submission("r3", graph_id, "c3", "J3", "EP3", "Carol", "eligible", DomainStatus.NEW_SUBMISSION.value, "time2", "time", new_payload)
    
    with engine._get_connection() as conn:
        cursor = conn.execute("SELECT payload_ciphertext FROM submission_records WHERE graph_immutable_id = ?", (graph_id,))
        dec_payload = json.loads(engine.encryptor.decrypt(cursor.fetchone()["payload_ciphertext"]))
        assert len(dec_payload["thread_messages"]) == 2
        assert dec_payload["thread_messages"][1]["id"] == "msg2"

def test_manager_notes_survive_refresh(temp_persistence):
    engine = temp_persistence
    graph_id = "immutable-id-4"
    
    payload = {
        "thread_messages": [{"id": "msg1"}],
        "manager_notes": "Important candidate",
        "latest_update": "Some update"
    }
    engine.upsert_submission("r4", graph_id, "c4", "J4", "EP4", "Dave", "eligible", DomainStatus.NEW_SUBMISSION.value, "time", "time", payload)
    
    # Refresh payload from Graph (which lacks manager notes)
    refresh_payload = {
        "thread_messages": [{"id": "msg1"}]
    }
    engine.upsert_submission("r4", graph_id, "c4", "J4", "EP4", "Dave", "eligible", DomainStatus.NEW_SUBMISSION.value, "time", "time", refresh_payload)
    
    with engine._get_connection() as conn:
        cursor = conn.execute("SELECT payload_ciphertext FROM submission_records WHERE graph_immutable_id = ?", (graph_id,))
        dec_payload = json.loads(engine.encryptor.decrypt(cursor.fetchone()["payload_ciphertext"]))
        assert dec_payload["manager_notes"] == "Important candidate"
        assert dec_payload["latest_update"] == "Some update"


def test_manager_outcome_and_linked_conversations_survive_refresh(temp_persistence):
    payload = {
        "thread_messages": [],
        "manager_outcome_category": "Position Closed",
        "linked_conversations": [{"conversation_id": "interview-conv", "role": "interview_coordination"}],
    }
    temp_persistence.upsert_submission(
        "manager-rec", "manager-imm", "manager-conv", "1", "EP1", "Candidate",
        "eligible", DomainStatus.MANAGER_ACTION_REQUIRED.value,
        "2026-08-01T10:00:00Z", "2026-08-01T10:00:00Z", payload,
    )
    temp_persistence.upsert_submission(
        "manager-rec", "manager-imm", "manager-conv", "1", "EP1", "Candidate",
        "eligible", DomainStatus.NEW_SUBMISSION.value,
        "2026-08-01T10:00:00Z", "2026-08-01T10:00:00Z", {"thread_messages": []},
    )
    refreshed, _version, status = temp_persistence.get_record_payload_snapshot("manager-rec")
    assert status == DomainStatus.MANAGER_ACTION_REQUIRED.value
    assert refreshed["manager_outcome_category"] == "Position Closed"
    assert refreshed["linked_conversations"][0]["conversation_id"] == "interview-conv"
def test_closed_records_not_automatically_reopened(temp_persistence):
    engine = temp_persistence
    graph_id = "immutable-id-5"
    
    payload = {
        "thread_messages": [{"id": "msg1"}],
        "close_reason": "Position closed"
    }
    # Initial is CLOSED
    engine.upsert_submission("r5", graph_id, "c5", "J5", "EP5", "Eve", "eligible", DomainStatus.CLOSED.value, "time", "time", payload)
    
    # Refresh says it's NEW_SUBMISSION or something else from Graph
    refresh_payload = {
        "thread_messages": [{"id": "msg1"}, {"id": "msg2"}]
    }
    engine.upsert_submission("r5", graph_id, "c5", "J5", "EP5", "Eve", "eligible", DomainStatus.NEW_SUBMISSION.value, "time", "time", refresh_payload)
    
    with engine._get_connection() as conn:
        cursor = conn.execute("SELECT domain_status, payload_ciphertext FROM submission_records WHERE graph_immutable_id = ?", (graph_id,))
        row = cursor.fetchone()
        
        # Status should REMAIN CLOSED
        assert row["domain_status"] == DomainStatus.CLOSED.value
        dec_payload = json.loads(engine.encryptor.decrypt(row["payload_ciphertext"]))
        # But new message should be added
        assert len(dec_payload["thread_messages"]) == 2
        assert dec_payload["close_reason"] == "Position closed"


def test_refresh_never_resets_an_existing_workflow_status(temp_persistence):
    engine = temp_persistence
    graph_id = "immutable-id-status-preservation"
    engine.upsert_submission(
        "r-status", graph_id, "c-status", "J6", "EP6", "Frank", "eligible",
        DomainStatus.MANAGER_ACTION_REQUIRED.value, "time", "time",
        {"thread_messages": [{"id": "msg1"}]},
    )

    # Import refreshes always arrive with NewSubmission as their provisional
    # status. They may add source messages but cannot erase workflow state.
    engine.upsert_submission(
        "ignored-new-id", graph_id, "c-status", "J6", "EP6", "Frank", "eligible",
        DomainStatus.NEW_SUBMISSION.value, "time2", "time2",
        {"thread_messages": [{"id": "msg1"}, {"id": "msg2"}]},
    )

    with engine._get_connection() as conn:
        row = conn.execute(
            "SELECT domain_status, payload_ciphertext FROM submission_records "
            "WHERE graph_immutable_id = ?", (graph_id,)
        ).fetchone()
    assert row["domain_status"] == DomainStatus.MANAGER_ACTION_REQUIRED.value
    payload = json.loads(engine.encryptor.decrypt(row["payload_ciphertext"]))
    assert len(payload["thread_messages"]) == 2
