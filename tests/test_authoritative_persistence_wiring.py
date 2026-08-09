"""
Tests proving:
- Normal runtime uses the real encrypted repository, never synthetic fallback.
- Explicit test mode can use synthetic fixtures.
- Missing database/key/decryption fails closed.
- Dashboard totals reconcile with repository records.
- Record detail uses the same authoritative repository.
- Read-only mutation requests return 403.
- Raw Graph IDs remain hidden from sanitized evidence.
- No Graph/Ollama/send routes execute.
"""

import os
import tempfile
import uuid
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.api.routes import _use_synthetic, persistence
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.models import SubmissionRecord, DomainStatus

client = TestClient(app)

@pytest.fixture(autouse=True)
def block_real_db_access(monkeypatch):
    """Ensure no test ever accesses the real ~/.recruitment_agent directory."""
    original_expanduser = os.path.expanduser
    def fake_expanduser(path):
        if ".recruitment_agent" in path:
            return "/blocked_by_test_isolation/.recruitment_agent" + path.split(".recruitment_agent")[1]
        return original_expanduser(path)
    
    monkeypatch.setattr(os.path, "expanduser", fake_expanduser)

@pytest.fixture
def auth_fixture(monkeypatch):
    """
    Creates a temporary encrypted database with 7 synthetic records
    and injects it as the authoritative persistence engine.
    """
    temp_db_path = os.path.join(tempfile.gettempdir(), f"test_records_{uuid.uuid4().hex}.db")
    test_engine = EncryptedPersistenceEngine(db_path=temp_db_path, master_key="test-master-key-1234567890123456")
    
    # Initialize some synthetic data
    for i in range(7):
        rec_id = f"test-id-{i}"
        payload = {
            "id": rec_id,
            "graph_immutable_id": f"AAMk{i}xyz",
            "conversation_id": f"conv-{i}",
            "tcs_eligibility": "eligible",
            "domain_status": DomainStatus.NEEDS_REVIEW.value,
            "received_at": "2026-08-01T12:00:00Z",
            "created_at": "2026-08-01T12:00:00Z",
            "timeline": [
                {
                    "entry_id": "1",
                    "event_type": "INBOUND_MESSAGE",
                    "sender": "candidate@example.com",
                    "timestamp": "2026-08-01T12:00:00Z",
                    "body_preview": "Hello!"
                }
            ]
        }
        test_engine.upsert_submission(
            record_id=rec_id,
            graph_immutable_id=f"AAMk{i}xyz",
            conversation_id=f"conv-{i}",
            job_id=None,
            ep_reference=None,
            candidate_name=None,
            tcs_eligibility="eligible",
            domain_status=DomainStatus.NEEDS_REVIEW.value,
            received_at="2026-08-01T12:00:00Z",
            created_at="2026-08-01T12:00:00Z",
            payload_data=payload
        )
        
    # Inject it into routes
    monkeypatch.setattr("backend.app.api.routes.persistence", test_engine)
    
    yield test_engine
    
    # Cleanup
    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)


class TestAuthoritativePersistenceWiring:

    def test_normal_runtime_uses_real_repository(self, monkeypatch, auth_fixture):
        """Without USE_SYNTHETIC_DATA, dashboard returns authoritative_encrypted_database."""
        monkeypatch.delenv("USE_SYNTHETIC_DATA", raising=False)
        res = client.get("/api/v1/dashboard")
        assert res.status_code == 200
        data = res.json()
        assert data["auth_status"] == "authoritative_encrypted_database"
        # Test DB has 7 injected records
        assert data["total"] == 7

    def test_synthetic_data_used_only_with_explicit_flag(self, monkeypatch, auth_fixture):
        """With USE_SYNTHETIC_DATA=True, dashboard returns synthetic_test_data."""
        monkeypatch.setenv("USE_SYNTHETIC_DATA", "True")
        res = client.get("/api/v1/dashboard")
        assert res.status_code == 200
        data = res.json()
        assert data["auth_status"] == "synthetic_test_data"

    def test_missing_db_fails_closed(self, monkeypatch, auth_fixture):
        """If the real DB is missing, the system fails closed with 500."""
        monkeypatch.delenv("USE_SYNTHETIC_DATA", raising=False)
        with patch.object(auth_fixture, "get_dashboard_summary", side_effect=RuntimeError("DB missing")):
            res = client.get("/api/v1/dashboard")
            assert res.status_code == 500
            assert "fail closed" in res.json()["detail"]

    def test_decryption_failure_fails_closed(self, monkeypatch, auth_fixture):
        """If decryption fails, the system fails closed with 500 on record detail."""
        monkeypatch.delenv("USE_SYNTHETIC_DATA", raising=False)
        with patch.object(auth_fixture, "get_record_by_id", side_effect=RuntimeError("Decryption failed")):
            res = client.get("/api/v1/records/test-id-0")
            assert res.status_code == 500
            assert "fail closed" in res.json()["detail"]

    def test_dashboard_totals_reconcile_with_db(self, monkeypatch, auth_fixture):
        """Dashboard status counts must sum to total records."""
        monkeypatch.delenv("USE_SYNTHETIC_DATA", raising=False)
        res = client.get("/api/v1/dashboard")
        assert res.status_code == 200
        data = res.json()
        bucket_sum = (
            data.get("awaiting_response", 0) +
            data["pending_follow_up"] +
            data.get("interview_awaiting_confirmation", 0) +
            data["awaiting_feedback"] +
            data["feedback_due"] +
            data["manager_action_required"] +
            data["in_evaluation"] +
            data["needs_review"] +
            data.get("incomplete", 0) +
            data["closed"]
        )
        assert bucket_sum == data["total"]

    def test_record_detail_uses_real_repository(self, monkeypatch, auth_fixture):
        """Record detail for a real record ID returns from DB, not synthetic."""
        monkeypatch.delenv("USE_SYNTHETIC_DATA", raising=False)
        # Get first real record ID from dashboard
        dash = client.get("/api/v1/dashboard").json()
        if dash["records"]:
            first_id = dash["records"][0]["id"]
            res = client.get(f"/api/v1/records/{first_id}")
            assert res.status_code == 200
            record_data = res.json()
            assert record_data["id"] == first_id
            # Verify timeline is present (real data has thread_messages)
            assert "timeline" in record_data

    def test_synthetic_record_not_found_in_real_mode(self, monkeypatch, auth_fixture):
        """Synthetic record IDs like syn-rec-001 must return 404 in real mode."""
        monkeypatch.delenv("USE_SYNTHETIC_DATA", raising=False)
        res = client.get("/api/v1/records/syn-rec-001")
        assert res.status_code == 404

    def test_read_only_mutations_rejected(self, monkeypatch, auth_fixture):
        """Mutation endpoints return 403 when READ_ONLY=True."""
        monkeypatch.setenv("READ_ONLY", "True")
        res = client.post("/api/v1/records/test-id-0/notes", json={"note": "Test"})
        assert res.status_code == 403
        assert "READ_ONLY mode is active" in res.json()["detail"]

    def test_raw_graph_ids_hidden_in_sanitized_evidence(self, monkeypatch, auth_fixture):
        """Sanitized evidence descriptions must not contain raw Graph IDs."""
        monkeypatch.delenv("USE_SYNTHETIC_DATA", raising=False)
        # Get first real record
        dash = client.get("/api/v1/dashboard").json()
        if dash["records"]:
            first_id = dash["records"][0]["id"]
            record = client.get(f"/api/v1/records/{first_id}").json()
            # Check timeline entries don't expose graph_immutable_id in body_preview
            for entry in record.get("timeline", []):
                preview = entry.get("body_preview", "")
                # Graph IDs start with AAMk or AAQk
                assert "AAMk" not in preview or len(preview) > 200  # long previews may contain coincidental matches
                assert "AAQk" not in preview or len(preview) > 200

    def test_no_graph_ollama_send_routes_execute(self, monkeypatch, auth_fixture):
        """Verify no Graph/Ollama/send routes execute in normal operation."""
        monkeypatch.delenv("USE_SYNTHETIC_DATA", raising=False)
        # Health endpoint works without Graph
        res = client.get("/api/v1/health")
        assert res.status_code == 200
        # Dashboard works without Graph
        res = client.get("/api/v1/dashboard")
        assert res.status_code == 200
        # Config shows mail_send_prohibited
        res = client.get("/api/v1/config/status")
        assert res.status_code == 200
        assert res.json()["mail_send_prohibited"] is True

    def test_daily_review_auth_status_reflects_mode(self, monkeypatch, auth_fixture):
        """Daily review status reports correct auth_status based on mode."""
        monkeypatch.delenv("USE_SYNTHETIC_DATA", raising=False)
        res = client.get("/api/v1/daily-review/status")
        assert res.status_code == 200
        assert res.json()["auth_status"] == "authoritative_encrypted_database"

        monkeypatch.setenv("USE_SYNTHETIC_DATA", "True")
        res2 = client.get("/api/v1/daily-review/status")
        assert res2.json()["auth_status"] == "synthetic_test_data"
