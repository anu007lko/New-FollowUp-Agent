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
def temp_db(tmp_path, monkeypatch):
    """Create a temporary isolated encrypted database for mutation testing."""
    db_file = tmp_path / "temp_records.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    monkeypatch.delenv("USE_SYNTHETIC_DATA", raising=False)
    
    # Save old persistence engine
    import backend.app.api.routes as routes_module
    old_persistence = routes_module.persistence

    # Initialize isolated temp database engine
    engine = EncryptedPersistenceEngine(db_path=str(db_file))
    routes_module.persistence = engine
    
    # Seed test records into temporary database
    record_id = "test-rec-001"
    graph_id = "AAMkAGTest123"
    conv_id = "AAQkAGConv123"
    ts = "2026-07-01T10:00:00Z"
    
    payload = {
        "id": record_id,
        "graph_immutable_id": graph_id,
        "conversation_id": conv_id,
        "job_id": "111111",
        "ep_reference": "EP111111",
        "candidate_name": "Test Candidate",
        "tcs_eligibility": "eligible",
        "domain_status": DomainStatus.PENDING_FOLLOW_UP.value,
        "received_at": ts,
        "created_at": ts,
        "manager_notes": "",
        "system_notes": "",
        "thread_messages": [
            {
                "id": graph_id,
                "internetMessageId": "<test-msg-1@clifyx.com>",
                "from": {"emailAddress": {"address": "manager@clifyx.com"}},
                "sentDateTime": ts,
                "bodyPreview": "Original submission email",
                "toRecipients": [{"emailAddress": {"address": "client@example.com"}}]
            },
            {
                "id": "AAMkAGDuplicateCopy",
                "internetMessageId": "<test-msg-1@clifyx.com>",  # Duplicate cross-folder copy
                "from": {"emailAddress": {"address": "manager@clifyx.com"}},
                "sentDateTime": ts,
                "bodyPreview": "Original submission email copy",
                "toRecipients": [{"emailAddress": {"address": "client@example.com"}}]
            }
        ]
    }
    
    engine.save_record_payload(record_id, payload, DomainStatus.PENDING_FOLLOW_UP.value)

    # Seed incomplete record (0 messages)
    inc_payload = {
        "id": "test-inc-002",
        "graph_immutable_id": "AAMkAGIncomplete",
        "conversation_id": "AAQkAGIncConv",
        "tcs_eligibility": "eligible",
        "domain_status": DomainStatus.NEW_SUBMISSION.value,
        "received_at": ts,
        "created_at": ts,
        "thread_messages": []
    }
    engine.save_record_payload("test-inc-002", inc_payload, DomainStatus.NEW_SUBMISSION.value)

    yield engine, record_id, graph_id, conv_id, ts

    routes_module.persistence = old_persistence


def test_manager_local_capability_gate(temp_db, monkeypatch):
    """Prove APP_MODE=manager_local permits ONLY local action endpoints and blocks all other mutations."""
    monkeypatch.setenv("READ_ONLY", "True")
    monkeypatch.setenv("APP_MODE", "manager_local")
    
    engine, rec_id, graph_id, conv_id, ts = temp_db
    
    # 1. Permitted local endpoint (Add Note)
    res = client.post(
        f"/api/v1/records/{rec_id}/notes",
        headers=CSRF_HEADERS,
        json={
            "record_id": rec_id,
            "graph_immutable_id": graph_id,
            "conversation_id": conv_id,
            "record_version": 1,
            "note_text": "Local test note"
        }
    )
    assert res.status_code == 200

    # 2. Blocked endpoint (Draft creation)
    res_draft = client.post(
        "/api/v1/drafts/create",
        headers=CSRF_HEADERS,
        json={"record_id": rec_id}
    )
    assert res_draft.status_code == 403
    assert "manager_local mode" in res_draft.json()["detail"]


def test_timeline_internet_message_id_deduplication(temp_db):
    """Prove cross-folder copies sharing valid internetMessageId render once in timeline."""
    engine, rec_id, _, _, _ = temp_db
    rec = engine.get_record_by_id(rec_id)
    
    # Payload has 2 thread_messages with identical internetMessageId <test-msg-1@clifyx.com>
    # Rendered timeline must contain exactly 1 entry
    assert len(rec.timeline) == 1
    assert rec.timeline[0].graph_immutable_id == "AAMkAGTest123"


def test_manager_note_does_not_reset_timers(temp_db, monkeypatch):
    """Prove adding a note updates notes/audit without changing timers or domain status."""
    monkeypatch.setenv("READ_ONLY", "True")
    monkeypatch.setenv("APP_MODE", "manager_local")
    
    engine, rec_id, graph_id, conv_id, ts = temp_db
    
    res = client.post(
        f"/api/v1/records/{rec_id}/notes",
        headers=CSRF_HEADERS,
        json={
            "record_id": rec_id,
            "graph_immutable_id": graph_id,
            "conversation_id": conv_id,
            "record_version": 1,
            "note_text": "Spoke to candidate, highly interested."
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert "Spoke to candidate" in data["manager_notes"]
    assert data["domain_status"] == DomainStatus.PENDING_FOLLOW_UP.value


def test_manager_note_accepts_legacy_list_storage(temp_db, monkeypatch):
    """Legacy list-form notes append safely instead of causing a 500 response."""
    monkeypatch.setenv("READ_ONLY", "True")
    monkeypatch.setenv("APP_MODE", "manager_local")
    engine, rec_id, graph_id, conv_id, _ = temp_db
    rec = engine.get_record_by_id(rec_id)
    with engine._get_connection() as conn:
        row = conn.execute("SELECT payload_ciphertext FROM submission_records WHERE id = ?", (rec_id,)).fetchone()
        payload = engine._decrypt_payload(row["payload_ciphertext"])
    payload["manager_notes"] = ["Existing note"]
    engine.update_record_optimistically(rec_id, payload, rec.domain_status.value, rec.record_version)

    result = client.post(
        f"/api/v1/records/{rec_id}/notes", headers=CSRF_HEADERS,
        json={"record_id": rec_id, "graph_immutable_id": graph_id, "conversation_id": conv_id,
              "record_version": 2, "note_text": "New local note"}
    )
    assert result.status_code == 200
    assert "Existing note" in result.json()["manager_notes"]
    assert "New local note" in result.json()["manager_notes"]


def test_followup_decision_creates_no_draft(temp_db, monkeypatch):
    """Prove Request Follow-up records local manager decision without creating draft or calling Graph."""
    monkeypatch.setenv("READ_ONLY", "True")
    monkeypatch.setenv("APP_MODE", "manager_local")
    
    engine, rec_id, graph_id, conv_id, ts = temp_db
    
    res = client.post(
        f"/api/v1/records/{rec_id}/follow-up-decision",
        headers=CSRF_HEADERS,
        json={
            "record_id": rec_id,
            "graph_immutable_id": graph_id,
            "conversation_id": conv_id,
            "record_version": 1,
            "decision": "Request Follow-up"
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert any("Request Follow-up" in (e.get("body_preview") or "") for e in data["timeline"])


def test_interview_confirmation_choices(temp_db, monkeypatch):
    """Prove every interview confirmation choice (completed, rescheduled, cancelled, not_confirmed)."""
    monkeypatch.setenv("READ_ONLY", "True")
    monkeypatch.setenv("APP_MODE", "manager_local")
    
    engine, rec_id, graph_id, conv_id, ts = temp_db

    # Choice: completed -> starts 48h feedback timer
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
    assert data["interview_state"] == InterviewState.COMPLETED.value
    assert data["feedback_due_at"] is not None
    assert data["domain_status"] == DomainStatus.AWAITING_FEEDBACK.value
    v2 = data["record_version"]

    # Choice: rescheduled -> requires date/time
    res_resched = client.post(
        f"/api/v1/records/{rec_id}/interview-confirmation",
        headers=CSRF_HEADERS,
        json={
            "record_id": rec_id,
            "graph_immutable_id": graph_id,
            "conversation_id": conv_id,
            "record_version": v2,
            "choice": "rescheduled",
            "new_date": "2026-08-10",
            "new_time": "14:00",
            "timezone": "America/New_York"
        }
    )
    assert res_resched.status_code == 200
    assert res_resched.json()["interview_state"] == InterviewState.RESCHEDULED.value
    v3 = res_resched.json()["record_version"]


def test_manager_can_confirm_future_schedule_and_defer_review(temp_db, monkeypatch):
    """A future schedule and a manager-approved review deadline are explicit local actions."""
    monkeypatch.setenv("READ_ONLY", "True")
    monkeypatch.setenv("APP_MODE", "manager_local")
    _, rec_id, graph_id, conv_id, _ = temp_db

    scheduled = client.post(
        f"/api/v1/records/{rec_id}/interview-schedule", headers=CSRF_HEADERS,
        json={"record_id": rec_id, "graph_immutable_id": graph_id, "conversation_id": conv_id,
              "record_version": 1, "interview_date": "2099-08-10", "interview_time": "15:00"}
    )
    assert scheduled.status_code == 200
    data = scheduled.json()
    assert data["domain_status"] == DomainStatus.INTERVIEW_REQUEST_SCHEDULED.value
    assert data["interview_state"] == InterviewState.SCHEDULED.value
    assert data["feedback_due_at"] is None

    deferred = client.post(
        f"/api/v1/records/{rec_id}/review-deferral", headers=CSRF_HEADERS,
        json={"record_id": rec_id, "graph_immutable_id": graph_id, "conversation_id": conv_id,
              "record_version": data["record_version"], "review_after": "2099-08-13T15:00:00-04:00",
              "reason": "Client expects confirmation later."}
    )
    assert deferred.status_code == 200
    assert deferred.json()["domain_status"] == DomainStatus.IN_EVALUATION.value
    assert deferred.json()["feedback_due_at"] == "2099-08-13T19:00:00+00:00"

    # Choice: cancelled -> keeps record open
    res_cancel = client.post(
        f"/api/v1/records/{rec_id}/interview-confirmation",
        headers=CSRF_HEADERS,
        json={
            "record_id": rec_id,
            "graph_immutable_id": graph_id,
            "conversation_id": conv_id,
            "record_version": deferred.json()["record_version"],
            "choice": "cancelled"
        }
    )
    assert res_cancel.status_code == 200
    assert res_cancel.json()["interview_state"] == InterviewState.CANCELLED.value
    assert res_cancel.json()["domain_status"] != DomainStatus.CLOSED.value


def test_close_reason_validation_and_other_note(temp_db, monkeypatch):
    """Prove close workflow reason validation and requirement for note when reason is 'Other'."""
    monkeypatch.setenv("READ_ONLY", "True")
    monkeypatch.setenv("APP_MODE", "manager_local")
    
    engine, rec_id, graph_id, conv_id, ts = temp_db

    # Close with 'Other' without note -> fails 400
    res_fail = client.post(
        f"/api/v1/records/{rec_id}/close",
        headers=CSRF_HEADERS,
        json={
            "record_id": rec_id,
            "graph_immutable_id": graph_id,
            "conversation_id": conv_id,
            "record_version": 1,
            "reason": "Other",
            "close_note": ""
        }
    )
    assert res_fail.status_code == 400

    # Close with 'Position closed' -> succeeds
    res_ok = client.post(
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
    assert res_ok.status_code == 200
    assert res_ok.json()["domain_status"] == DomainStatus.CLOSED.value
    v2 = res_ok.json()["record_version"]

    # Reopen
    res_reopen = client.post(
        f"/api/v1/records/{rec_id}/reopen",
        headers=CSRF_HEADERS,
        json={
            "record_id": rec_id,
            "graph_immutable_id": graph_id,
            "conversation_id": conv_id,
            "record_version": v2,
            "reason": "Reopening for new position"
        }
    )
    assert res_reopen.status_code == 200
    assert res_reopen.json()["domain_status"] == DomainStatus.NEEDS_REVIEW.value


def test_incomplete_record_restrictions(temp_db, monkeypatch):
    """Prove incomplete records cannot be actioned."""
    monkeypatch.setenv("READ_ONLY", "True")
    monkeypatch.setenv("APP_MODE", "manager_local")
    
    engine, _, _, _, ts = temp_db
    inc_id = "test-inc-002"

    res = client.post(
        f"/api/v1/records/{inc_id}/notes",
        headers=CSRF_HEADERS,
        json={
            "record_id": inc_id,
            "graph_immutable_id": "AAMkAGIncomplete",
            "conversation_id": "AAQkAGIncConv",
            "record_version": 1,
            "note_text": "Test note"
        }
    )
    assert res.status_code == 400
    assert "incomplete and cannot be actioned" in res.json()["detail"]


def test_stale_or_mismatched_binding_rejection(temp_db, monkeypatch):
    """Prove stale record_version or mismatched graph_immutable_id is rejected."""
    monkeypatch.setenv("READ_ONLY", "True")
    monkeypatch.setenv("APP_MODE", "manager_local")
    
    engine, rec_id, graph_id, conv_id, ts = temp_db

    # Stale version
    res_stale = client.post(
        f"/api/v1/records/{rec_id}/notes",
        headers=CSRF_HEADERS,
        json={
            "record_id": rec_id,
            "graph_immutable_id": graph_id,
            "conversation_id": conv_id,
            "record_version": 999,
            "note_text": "Stale note"
        }
    )
    assert res_stale.status_code == 409

    # Mismatched graph ID
    res_mismatch = client.post(
        f"/api/v1/records/{rec_id}/notes",
        headers=CSRF_HEADERS,
        json={
            "record_id": rec_id,
            "graph_immutable_id": "WRONG_GRAPH_ID",
            "conversation_id": conv_id,
            "record_version": 1,
            "note_text": "Wrong ID note"
        }
    )
    assert res_mismatch.status_code == 400


def test_source_content_conflict_detection():
    """Verify read-time conflict detection between subject Job ID and body Job ID."""
    # Mismatch case
    warn = EncryptedPersistenceEngine._detect_source_content_conflict(
        subj_job_id="418737",
        thread_messages=[
            {
                "id": "msg_001",
                "body": {"content": "Submission for Candidate: Job ID: 423819 Network Manager"},
            }
        ],
        graph_immutable_id="msg_001"
    )
    assert warn is not None
    assert "418737" in warn
    assert "423819" in warn

    # Matching case
    no_warn = EncryptedPersistenceEngine._detect_source_content_conflict(
        subj_job_id="418737",
        thread_messages=[
            {
                "id": "msg_001",
                "body": {"content": "Submission for Candidate: Job ID: 418737 Network Manager"},
            }
        ],
        graph_immutable_id="msg_001"
    )
    assert no_warn is None
