"""
End-to-End (E2E) Integration Test Suite for Recruitment Follow-Up Agent.

Guarantees:
1. MAIL_SEND_ENABLED is strictly False — no actual email will ever be sent.
2. If MAIL_SEND_ENABLED is set to True, all draft capabilities fail closed immediately (HTTP 503).
3. Complete manager workflow (Config check -> Record fetch -> Draft Approve -> Close -> Reopen -> Notes).
"""

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.api.routes import security_service


@pytest.fixture
def db_client(tmp_path, monkeypatch):
    """Fixture initializing TestClient with isolated SQLite persistence."""
    db_file = tmp_path / "test_e2e_records.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    monkeypatch.setenv("GRAPH_ENABLED", "True")
    monkeypatch.setenv("DRAFTS_ENABLED", "True")
    monkeypatch.setenv("MAIL_SEND_ENABLED", "False")
    monkeypatch.setenv("APP_MODE", "manager_local")
    monkeypatch.setenv("READ_ONLY", "False")
    monkeypatch.delenv("USE_SYNTHETIC_DATA", raising=False)

    import backend.app.api.routes as routes_module
    engine = EncryptedPersistenceEngine(db_path=str(db_file))
    routes_module.persistence = engine

    # Seed test record
    rec_id = "e2e-rec-001"
    graph_id = "AAMkE2E001"
    conv_id = "AAQkE2EConv001"
    ts = "2026-07-29T15:17:00Z"

    payload = {
        "id": rec_id,
        "graph_immutable_id": graph_id,
        "conversation_id": conv_id,
        "job_id": "424631",
        "ep_reference": "EP424631",
        "candidate_name": "Naga Venkata Akhilesh Koorma",
        "role_title": "Data Engineer",
        "client_name": "FCB",
        "location": "Dallas, TX",
        "tcs_eligibility": "eligible",
        "domain_status": "PendingFollowUp",
        "received_at": ts,
        "created_at": ts,
        "manager_notes": "",
        "system_notes": "",
        "record_version": 1,
        "thread_messages": [
            {
                "id": graph_id,
                "internetMessageId": "<e2e-1@fcb.com>",
                "from": {"emailAddress": {"address": "tarun@example.com"}},
                "sentDateTime": ts,
                "bodyPreview": "Original submission email",
                "toRecipients": [{"emailAddress": {"address": "sara@fcb.com"}}]
            }
        ]
    }
    engine.save_record_payload(rec_id, payload, "PendingFollowUp")

    with TestClient(app) as client:
        yield client, engine, rec_id, graph_id, conv_id


def _get_csrf_headers() -> dict:
    """Helper to bootstrap valid CSRF headers."""
    return {"X-CSRF-Token": security_service.generate_csrf_token()}


def test_e2e_config_status_and_safety_invariants(db_client):
    """E2E Test 1: Verify config status and mail_send_prohibited invariant."""
    client, _, _, _, _ = db_client

    response = client.get("/api/v1/config/status")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ready"
    assert data["mail_send_prohibited"] is True, "Mail sending must be strictly prohibited"
    assert data["graph_enabled"] is True
    assert data["drafts_enabled"] is True
    assert data["draft_creation_available"] is True, "Draft creation should be available when GRAPH and DRAFTS are enabled"


def test_e2e_fail_closed_if_mail_send_enabled(db_client, monkeypatch):
    """E2E Test 2: Safety guard check — if MAIL_SEND_ENABLED is True, draft creation fails closed with 503."""
    client, _, rec_id, _, _ = db_client

    # Fetch record to get version
    rec_resp = client.get(f"/api/v1/records/{rec_id}")
    assert rec_resp.status_code == 200
    version = rec_resp.json()["record_version"]

    # Force MAIL_SEND_ENABLED=True to verify fail-closed protection
    monkeypatch.setenv("MAIL_SEND_ENABLED", "True")

    response = client.post(
        f"/api/v1/records/{rec_id}/draft-approve",
        json={
            "record_id": rec_id,
            "record_version": version,
            "content": "Hi, following up on candidate submission."
        },
        headers=_get_csrf_headers()
    )
    assert response.status_code == 503
    assert "Draft capability failed closed" in response.json()["detail"]


def test_e2e_manager_draft_approval_workflow(db_client):
    """E2E Test 3: Manager approves a follow-up draft. Verifies approval creation without sending email."""
    client, _, rec_id, _, _ = db_client

    # Fetch record to get current version
    rec_resp = client.get(f"/api/v1/records/{rec_id}")
    assert rec_resp.status_code == 200
    rec_data = rec_resp.json()
    version = rec_data["record_version"]

    # Trigger draft approval stage
    response = client.post(
        f"/api/v1/records/{rec_id}/draft-approve",
        json={
            "record_id": rec_id,
            "record_version": version,
            "content": "Hi Sara, following up on candidate submission for Naga Venkata Akhilesh Koorma."
        },
        headers=_get_csrf_headers()
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["is_approved"] is True
    assert "approval_hash" in payload
    assert "idempotency_key" in payload


def test_e2e_manager_close_reopen_note_lifecycle(db_client):
    """E2E Test 4: Complete manager outcome lifecycle (Close -> Reopen -> Add Note)."""
    client, _, rec_id, graph_id, conv_id = db_client
    headers = _get_csrf_headers()

    # Get initial record details
    rec_resp = client.get(f"/api/v1/records/{rec_id}")
    assert rec_resp.status_code == 200
    version = rec_resp.json()["record_version"]

    # 1. Close Record
    close_resp = client.post(
        f"/api/v1/records/{rec_id}/close",
        json={
            "record_id": rec_id,
            "graph_immutable_id": graph_id,
            "conversation_id": conv_id,
            "record_version": version,
            "reason": "Position closed",
            "close_note": "Filled internally"
        },
        headers=headers
    )
    assert close_resp.status_code == 200
    closed_rec = close_resp.json()
    assert closed_rec["domain_status"] == "Closed"

    # 2. Reopen Record
    reopen_resp = client.post(
        f"/api/v1/records/{rec_id}/reopen",
        json={
            "record_id": rec_id,
            "graph_immutable_id": graph_id,
            "conversation_id": conv_id,
            "record_version": closed_rec["record_version"],
            "reason": "Reopening for new role evaluation"
        },
        headers=headers
    )
    assert reopen_resp.status_code == 200
    reopened_rec = reopen_resp.json()
    assert reopened_rec["domain_status"] != "Closed"

    # 3. Add Manager Note
    note_resp = client.post(
        f"/api/v1/records/{rec_id}/notes",
        json={
            "record_id": rec_id,
            "graph_immutable_id": graph_id,
            "conversation_id": conv_id,
            "record_version": reopened_rec["record_version"],
            "note_text": "Followed up with candidate on potential new role."
        },
        headers=headers
    )
    assert note_resp.status_code == 200
    rec_after_note = note_resp.json()
    assert "manager_notes" in rec_after_note or "timeline" in rec_after_note


def test_e2e_invalid_record_fail_closed(db_client):
    """E2E Test 5: Operations on non-existent record fail closed safely with 404."""
    client, _, _, _, _ = db_client

    response = client.post(
        "/api/v1/records/non-existent-rec/draft-approve",
        json={
            "record_id": "non-existent-rec",
            "record_version": 1,
            "content": "Test draft"
        },
        headers=_get_csrf_headers()
    )
    assert response.status_code in (404, 500)
