"""
Integration tests for unified workflow API endpoints in routes.py.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.api.routes import security_service
import backend.app.api.routes as routes_module
from backend.app.domain.models import (
    WorkflowStatus, ActionID, CloseReason, OutcomeOptionID,
    RecordDetailResponse, RecordListItem
)
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine

client = TestClient(app)
CSRF_HEADERS = {"x-csrf-token": security_service.generate_csrf_token()}


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Create a temporary isolated encrypted database for endpoint testing."""
    db_file = tmp_path / "temp_wf_endpoints.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    monkeypatch.delenv("USE_SYNTHETIC_DATA", raising=False)

    old_persistence = routes_module.persistence
    engine = EncryptedPersistenceEngine(db_path=str(db_file))
    routes_module.persistence = engine

    record_id = "test_wf_endpoint_rec_1"
    payload = {
        "id": record_id,
        "graph_immutable_id": "graph_test_wf_1",
        "conversation_id": "conv_test_wf_1",
        "job_id": "JOB-101",
        "candidate_name": "Jane Doe",
        "tcs_eligibility": "eligible",
        "domain_status": "NeedsReview",
        "received_at": "2026-08-01T10:00:00Z",
        "created_at": "2026-08-01T10:00:00Z",
        "manager_notes": "",
        "record_version": 1,
        "timeline": [],
        "thread_messages": []
    }
    engine.save_record_payload(record_id, payload, "NeedsReview")

    yield record_id, engine

    routes_module.persistence = old_persistence


def test_get_record_returns_detail_dto(temp_db):
    rec_id, _ = temp_db
    response = client.get(f"/api/v1/records/{rec_id}")
    assert response.status_code == 200
    data = response.json()
    assert "record" in data
    assert "workflow" in data
    assert data["record"]["id"] == rec_id
    assert data["workflow"]["status"] == "NeedsReview"
    assert data["workflow"]["display"]["label"] == "Needs Review"


def test_execute_action_close_record_alias_normalization(temp_db):
    rec_id, _ = temp_db
    payload = {
        "action_id": "CLOSE_RECORD",
        "record_version": 1,
        "reason": "Duplicate Submission"  # Raw alias
    }
    response = client.post(f"/api/v1/records/{rec_id}/action", json=payload, headers=CSRF_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["workflow"]["status"] == "Closed"
    assert data["workflow"]["close_reason"] == "Duplicate submission entry"
    assert data["workflow"]["display"]["label"] == "Duplicate Submission"
    assert data["record"]["record_version"] == 2


def test_execute_action_stale_version_returns_409(temp_db):
    rec_id, _ = temp_db
    payload = {
        "action_id": "CLOSE_RECORD",
        "record_version": 99,  # Stale version
        "reason": "Position closed"
    }
    response = client.post(f"/api/v1/records/{rec_id}/action", json=payload, headers=CSRF_HEADERS)
    assert response.status_code == 409
    assert "CONFLICT" in response.json()["detail"]


def test_execute_action_reopen_and_add_note(temp_db):
    rec_id, _ = temp_db
    # First close
    close_payload = {
        "action_id": "CLOSE_RECORD",
        "record_version": 1,
        "reason": "Position closed"
    }
    res_close = client.post(f"/api/v1/records/{rec_id}/action", json=close_payload, headers=CSRF_HEADERS)
    assert res_close.status_code == 200

    # Reopen
    reopen_payload = {
        "action_id": "REOPEN_RECORD",
        "record_version": 2
    }
    res_reopen = client.post(f"/api/v1/records/{rec_id}/action", json=reopen_payload, headers=CSRF_HEADERS)
    assert res_reopen.status_code == 200
    data_reopen = res_reopen.json()
    assert data_reopen["workflow"]["status"] == "NeedsReview"
    assert data_reopen["workflow"]["close_reason"] is None
    assert data_reopen["record"]["record_version"] == 3

    # Add note
    note_payload = {
        "action_id": "ADD_NOTE",
        "record_version": 3,
        "note": "Candidate requested call back."
    }
    res_note = client.post(f"/api/v1/records/{rec_id}/action", json=note_payload, headers=CSRF_HEADERS)
    assert res_note.status_code == 200
    data_note = res_note.json()
    assert data_note["workflow"]["status"] == "NeedsReview"
    assert data_note["record"]["record_version"] == 4
