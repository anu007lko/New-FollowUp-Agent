import os
import json
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.domain.models import DomainStatus, InterviewState
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.api.routes import security_service

client = TestClient(app)
CSRF_HEADERS = {"x-csrf-token": security_service.generate_csrf_token()}

@pytest.fixture
def temp_persistence_db(tmp_path, monkeypatch):
    """Create a temporary isolated encrypted database for metadata regression tests."""
    db_file = tmp_path / "metadata_test_records.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    monkeypatch.delenv("USE_SYNTHETIC_DATA", raising=False)
    
    import backend.app.api.routes as routes_module
    old_persistence = routes_module.persistence

    engine = EncryptedPersistenceEngine(db_path=str(db_file))
    routes_module.persistence = engine
    
    # Seed a complete record mimicking live import runner structure
    record_id = "test-rec-meta-001"
    graph_id = "AAMkAGTestMeta123"
    conv_id = "AAQkAGConvMeta123"
    ts = "2026-07-01T10:00:00Z"
    
    payload = {
        "id": record_id,
        "graph_immutable_id": graph_id,
        "conversation_id": conv_id,
        "metadata": {
            "job_id": "416955",
            "ep_reference": "EP2026RA7317431",
            "candidate_name": "Joicy Malarvizhi",
            "skill": "Program Manager in Asset Management",
            "customer": "Ameriprise Financial",
            "location": "Boston, MA (Local Candidate)"
        },
        "tcs_eligibility": "eligible",
        "domain_status": DomainStatus.NEEDS_REVIEW.value,
        "received_at": ts,
        "created_at": ts,
        "manager_notes": "",
        "system_notes": "",
        "thread_messages": [
            {
                "id": graph_id,
                "internetMessageId": "<orig-msg-1@clifyx.com>",
                "from": {"emailAddress": {"address": "manager@clifyx.com"}},
                "sentDateTime": ts,
                "bodyPreview": "Submission for Joicy Malarvizhi Job 416955",
                "toRecipients": [{"emailAddress": {"address": "client@example.com"}}]
            },
            {
                "id": "AAMkAGInboundInterviewMsg",
                "internetMessageId": "<inbound-interview@client.com>",
                "from": {"emailAddress": {"address": "client@example.com"}},
                "sentDateTime": "2026-07-02T14:00:00Z",
                "bodyPreview": "Interview invitation for Joicy Malarvizhi tomorrow at 2 PM",
                "toRecipients": [{"emailAddress": {"address": "manager@clifyx.com"}}]
            }
        ],
        "timeline": [
            {
                "entry_id": "init_submission",
                "graph_immutable_id": graph_id,
                "sender": "manager@clifyx.com",
                "timestamp": ts,
                "is_system_note": False,
                "body_preview": "Submission for Joicy Malarvizhi Job 416955"
            },
            {
                "entry_id": "inbound_interview_event",
                "graph_immutable_id": "AAMkAGInboundInterviewMsg",
                "sender": "client@example.com",
                "timestamp": "2026-07-02T14:00:00Z",
                "is_system_note": False,
                "body_preview": "Interview invitation for Joicy Malarvizhi tomorrow at 2 PM"
            }
        ]
    }
    
    # Save using standard persistence
    with engine._get_connection() as conn:
        meta = payload["metadata"]
        ciphertext = engine.encryptor.encrypt(json.dumps(payload))
        conn.execute(
            """
            INSERT INTO submission_records (
                id, graph_immutable_id, conversation_id, job_id, ep_reference,
                candidate_name, tcs_eligibility, domain_status, received_at, created_at, payload_ciphertext, record_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (record_id, graph_id, conv_id, meta["job_id"], meta["ep_reference"], meta["candidate_name"], "eligible", DomainStatus.NEEDS_REVIEW.value, ts, ts, ciphertext)
        )
        conn.commit()

    yield engine, record_id, graph_id, conv_id, ts
    routes_module.persistence = old_persistence


def test_add_note_v1_to_v2_preserves_all_metadata(temp_persistence_db, monkeypatch):
    """Add Note v1->v2 must preserve candidate name, job_id, ep_reference, messages, and attachments in SQLite columns and payload."""
    monkeypatch.setenv("READ_ONLY", "True")
    monkeypatch.setenv("APP_MODE", "manager_local")
    monkeypatch.setenv("MANAGER_EMAIL", "tarun@clifyx.com")

    engine, rec_id, graph_id, conv_id, ts = temp_persistence_db

    # Call Add Note endpoint
    res = client.post(
        f"/api/v1/records/{rec_id}/notes",
        headers=CSRF_HEADERS,
        json={
            "record_id": rec_id,
            "graph_immutable_id": graph_id,
            "conversation_id": conv_id,
            "record_version": 1,
            "note_text": "Candidate Selected"
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["record_version"] == 2
    assert data["candidate_name"] == "Joicy Malarvizhi"
    assert data["job_id"] == "416955"
    assert data["ep_reference"] == "EP2026RA7317431"
    assert "Candidate Selected" in data["manager_notes"]

    # Check indexed SQLite row columns
    with engine._get_connection() as conn:
        row = conn.execute("SELECT * FROM submission_records WHERE id = ?", (rec_id,)).fetchone()
        assert row["candidate_name"] == "Joicy Malarvizhi"
        assert row["job_id"] == "416955"
        assert row["ep_reference"] == "EP2026RA7317431"
        assert row["record_version"] == 2

    # Check list_records API
    list_res = client.get("/api/v1/records")
    assert list_res.status_code == 200
    headers = list_res.json()
    target_hdr = next(h for h in headers if h["id"] == rec_id)
    assert target_hdr["candidate_name"] == "Joicy Malarvizhi"
    assert target_hdr["job_id"] == "416955"
    assert target_hdr["ep_reference"] == "EP2026RA7317431"


def test_second_add_note_v2_to_v3_preserves_everything(temp_persistence_db, monkeypatch):
    """Second Add Note v2->v3 must preserve all fields and accumulate notes."""
    monkeypatch.setenv("READ_ONLY", "True")
    monkeypatch.setenv("APP_MODE", "manager_local")
    monkeypatch.setenv("MANAGER_EMAIL", "tarun@clifyx.com")

    engine, rec_id, graph_id, conv_id, ts = temp_persistence_db

    # First note
    client.post(
        f"/api/v1/records/{rec_id}/notes",
        headers=CSRF_HEADERS,
        json={"record_id": rec_id, "graph_immutable_id": graph_id, "conversation_id": conv_id, "record_version": 1, "note_text": "Note 1"}
    )

    # Second note
    res2 = client.post(
        f"/api/v1/records/{rec_id}/notes",
        headers=CSRF_HEADERS,
        json={"record_id": rec_id, "graph_immutable_id": graph_id, "conversation_id": conv_id, "record_version": 2, "note_text": "Note 2"}
    )
    assert res2.status_code == 200
    data = res2.json()
    assert data["record_version"] == 3
    assert data["candidate_name"] == "Joicy Malarvizhi"
    assert data["job_id"] == "416955"
    assert data["ep_reference"] == "EP2026RA7317431"
    assert "Note 1" in data["manager_notes"]
    assert "Note 2" in data["manager_notes"]


def test_interview_confirmation_preserves_fields_and_evidence(temp_persistence_db, monkeypatch):
    """Interview confirmation preserves candidate, job_id, ep, messages, attachments, and evidence."""
    monkeypatch.setenv("READ_ONLY", "True")
    monkeypatch.setenv("APP_MODE", "manager_local")
    monkeypatch.setenv("MANAGER_EMAIL", "tarun@clifyx.com")

    engine, rec_id, graph_id, conv_id, ts = temp_persistence_db

    res = client.post(
        f"/api/v1/records/{rec_id}/interview-confirmation",
        headers=CSRF_HEADERS,
        json={
            "record_id": rec_id,
            "graph_immutable_id": graph_id,
            "conversation_id": conv_id,
            "record_version": 1,
            "choice": "completed"
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["record_version"] == 2
    assert data["domain_status"] == DomainStatus.AWAITING_FEEDBACK.value
    assert data["candidate_name"] == "Joicy Malarvizhi"
    assert data["job_id"] == "416955"
    assert data["ep_reference"] == "EP2026RA7317431"
    assert data["interview_state"] == InterviewState.COMPLETED.value
    assert data["feedback_due_at"] is not None
    assert data["structured_evidence"] is not None


def test_set_outcome_preserves_fields_and_evidence(temp_persistence_db, monkeypatch):
    """Set Outcome preserves candidate, job_id, ep, messages, attachments, sets ManagerActionRequired and keeps closed=false."""
    monkeypatch.setenv("READ_ONLY", "True")
    monkeypatch.setenv("APP_MODE", "manager_local")
    monkeypatch.setenv("MANAGER_EMAIL", "tarun@clifyx.com")

    engine, rec_id, graph_id, conv_id, ts = temp_persistence_db

    res = client.post(
        f"/api/v1/records/{rec_id}/outcome-decision",
        headers=CSRF_HEADERS,
        json={
            "record_id": rec_id,
            "graph_immutable_id": graph_id,
            "conversation_id": conv_id,
            "record_version": 1,
            "outcome_category": "Position Closed",
            "notes": "Closed by manager"
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["record_version"] == 2
    assert data["domain_status"] == DomainStatus.CLOSED.value
    assert data["candidate_name"] == "Joicy Malarvizhi"
    assert data["job_id"] == "416955"
    assert data["ep_reference"] == "EP2026RA7317431"
    assert data["closed_at"] is not None
    assert data["close_reason"] == "Position Closed"
    assert data["structured_evidence"]["category"] == "Position Closed"
    assert data["structured_evidence"]["workflow_status"] == DomainStatus.CLOSED.value


def test_set_outcome_rejection_sets_action_required_and_open(temp_persistence_db, monkeypatch):
    """Set Outcome Rejection moves to Closed, stores category, and sets closed_at."""
    monkeypatch.setenv("READ_ONLY", "True")
    monkeypatch.setenv("APP_MODE", "manager_local")
    monkeypatch.setenv("MANAGER_EMAIL", "tarun@clifyx.com")

    engine, rec_id, graph_id, conv_id, ts = temp_persistence_db

    res = client.post(
        f"/api/v1/records/{rec_id}/outcome-decision",
        headers=CSRF_HEADERS,
        json={
            "record_id": rec_id,
            "graph_immutable_id": graph_id,
            "conversation_id": conv_id,
            "record_version": 1,
            "outcome_category": "Rejection",
            "notes": "Candidate not a good fit after interview"
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["record_version"] == 2
    assert data["domain_status"] == DomainStatus.CLOSED.value
    assert data["candidate_name"] == "Joicy Malarvizhi"
    assert data["closed_at"] is not None
    assert data["close_reason"] == "Rejection"
    assert data["structured_evidence"]["category"] == "Rejection"
    assert data["structured_evidence"]["workflow_status"] == DomainStatus.CLOSED.value


def test_set_outcome_appends_note_when_legacy_manager_notes_is_list(temp_persistence_db, monkeypatch):
    """Legacy list-form manager notes must remain valid when a new outcome note is appended."""
    monkeypatch.setenv("READ_ONLY", "True")
    monkeypatch.setenv("APP_MODE", "manager_local")
    monkeypatch.setenv("MANAGER_EMAIL", "tarun@clifyx.com")

    engine, rec_id, graph_id, conv_id, ts = temp_persistence_db
    with engine._get_connection() as conn:
        row = conn.execute(
            "SELECT payload_ciphertext FROM submission_records WHERE id = ?", (rec_id,)
        ).fetchone()
        payload = json.loads(engine.encryptor.decrypt(row[0]))
        payload["manager_notes"] = []
        conn.execute(
            "UPDATE submission_records SET payload_ciphertext = ? WHERE id = ?",
            (engine.encryptor.encrypt(json.dumps(payload)), rec_id),
        )
        conn.commit()

    note = "Associate lacks the required skills, hence we cannot consider the associate."
    res = client.post(
        f"/api/v1/records/{rec_id}/outcome-decision",
        headers=CSRF_HEADERS,
        json={
            "record_id": rec_id,
            "graph_immutable_id": graph_id,
            "conversation_id": conv_id,
            "record_version": 1,
            "outcome_category": "Client Rejected",
            "notes": note,
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["record_version"] == 2
    assert data["domain_status"] == DomainStatus.CLOSED.value
    assert note in data["manager_notes"]


def test_partial_api_object_cannot_overwrite_authoritative_encrypted_record(temp_persistence_db, monkeypatch):
    """Passing partial request objects to manager action endpoints cannot wipe out thread messages or metadata."""
    monkeypatch.setenv("READ_ONLY", "True")
    monkeypatch.setenv("APP_MODE", "manager_local")
    monkeypatch.setenv("MANAGER_EMAIL", "tarun@clifyx.com")

    engine, rec_id, graph_id, conv_id, ts = temp_persistence_db

    # Close record passing minimal request
    res = client.post(
        f"/api/v1/records/{rec_id}/close",
        headers=CSRF_HEADERS,
        json={
            "record_id": rec_id,
            "graph_immutable_id": graph_id,
            "conversation_id": conv_id,
            "record_version": 1,
            "reason": "Position closed"
        }
    )
    assert res.status_code == 200
    rec = engine.get_record_by_id(rec_id)
    assert rec is not None
    assert rec.candidate_name == "Joicy Malarvizhi"
    assert rec.job_id == "416955"
    assert rec.ep_reference == "EP2026RA7317431"
    
    # Thread messages and timeline must remain fully preserved
    with engine._get_connection() as conn:
        row = conn.execute("SELECT payload_ciphertext FROM submission_records WHERE id = ?", (rec_id,)).fetchone()
        payload = json.loads(engine.encryptor.decrypt(row["payload_ciphertext"]))
        assert len(payload["thread_messages"]) == 2
        assert payload["metadata"]["candidate_name"] == "Joicy Malarvizhi"
