from fastapi.testclient import TestClient

from backend.app.api.routes import security_service
import backend.app.api.routes as routes
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.main import app


client = TestClient(app)


def _payload(record_id: str, job_id: str, candidate: str, status: str = "NeedsReview") -> dict:
    return {
        "id": record_id,
        "graph_immutable_id": f"graph-{record_id}",
        "conversation_id": f"conversation-{record_id}",
        "job_id": job_id,
        "candidate_name": candidate,
        "tcs_eligibility": "eligible",
        "domain_status": status,
        "received_at": "2026-08-12T00:00:00Z",
        "created_at": "2026-08-12T00:00:00Z",
        "record_version": 1,
        "timeline": [],
        "thread_messages": [],
    }


def test_bulk_close_job_previews_and_closes_only_selected_active_records(tmp_path, monkeypatch):
    monkeypatch.setenv("READ_ONLY", "False")
    monkeypatch.setenv("APP_MODE", "manager_local")
    monkeypatch.delenv("USE_SYNTHETIC_DATA", raising=False)
    previous = routes.persistence
    database = EncryptedPersistenceEngine(db_path=str(tmp_path / "bulk-close.db"))
    routes.persistence = database
    try:
        database.save_record_payload("one", _payload("one", "JOB-42", "Ava"), "NeedsReview")
        database.save_record_payload("two", _payload("two", "JOB-42", "Ben"), "NeedsReview")
        database.save_record_payload("closed", _payload("closed", "JOB-42", "Cam", "Closed"), "Closed")
        database.save_record_payload("other", _payload("other", "JOB-99", "Dee"), "NeedsReview")
        headers = {"x-csrf-token": security_service.generate_csrf_token()}

        preview = client.post("/api/v1/records/one/bulk-close-job/preview", json={"record_version": 1}, headers=headers)
        assert preview.status_code == 200
        targets = preview.json()["records"]
        assert {target["record_id"] for target in targets} == {"one", "two"}

        close = client.post(
            "/api/v1/records/one/bulk-close-job",
            json={"record_version": 1, "targets": [{"record_id": item["record_id"], "record_version": item["record_version"]} for item in targets]},
            headers=headers,
        )
        assert close.status_code == 200
        assert set(close.json()["closed_record_ids"]) == {"one", "two"}
        assert database.get_record_by_id("one").domain_status.value == "Closed"
        assert database.get_record_by_id("two").domain_status.value == "Closed"
        assert database.get_record_by_id("closed").record_version == 1
        assert database.get_record_by_id("other").domain_status.value == "NeedsReview"
        one = database.get_record_by_id("one")
        assert any("Bulk closed for Job ID JOB-42" in event.body_preview for event in one.timeline)
    finally:
        routes.persistence = previous


def test_bulk_close_job_rejects_a_stale_source_record(tmp_path, monkeypatch):
    monkeypatch.setenv("READ_ONLY", "False")
    monkeypatch.setenv("APP_MODE", "manager_local")
    monkeypatch.delenv("USE_SYNTHETIC_DATA", raising=False)
    previous = routes.persistence
    database = EncryptedPersistenceEngine(db_path=str(tmp_path / "stale-bulk-close.db"))
    routes.persistence = database
    try:
        database.save_record_payload("one", _payload("one", "JOB-42", "Ava"), "NeedsReview")
        headers = {"x-csrf-token": security_service.generate_csrf_token()}
        response = client.post("/api/v1/records/one/bulk-close-job/preview", json={"record_version": 99}, headers=headers)
        assert response.status_code == 409
    finally:
        routes.persistence = previous
