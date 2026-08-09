import pytest
from unittest.mock import MagicMock, patch
import httpx
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.infrastructure.ollama_client import OllamaAdvisoryClient
from backend.app.domain.models import CategoryEnum, TimelineEntry, DomainStatus, AIPreflightResult, ServerStoredAdvisory, LLMAdvisoryResult
from backend.app.api.routes import _advisory_registry
from backend.app.infrastructure.synthetic_data import get_synthetic_record_by_id
from backend.app.api.routes import security_service

client = TestClient(app)
client.headers.update({"x-csrf-token": security_service.generate_csrf_token()})


@pytest.fixture(autouse=True)
def _enable_ollama_for_safe_ai_tests(monkeypatch):
    monkeypatch.setenv("OLLAMA_ENABLED", "True")


class TestSafeOptionalAIWorkflow:

    @patch("subprocess.run")
    @patch("backend.app.infrastructure.ollama_client.OllamaAdvisoryClient.is_available", return_value=True)
    def test_resource_preflight_available(self, mock_available, mock_sub):
        mock_sub.return_value = MagicMock(returncode=0, stdout="vm.memory_pressure: 1")
        res = client.get("/api/v1/ai/preflight")
        assert res.status_code == 200
        data = res.json()
        assert data["is_available"] is True

    @patch("subprocess.run")
    def test_resource_preflight_warning_critical_disabled(self, mock_sub):
        # Test level 2 (Warning)
        mock_sub.return_value = MagicMock(returncode=0, stdout="vm.memory_pressure: 2")
        ollama_client = OllamaAdvisoryClient()
        preflight2 = ollama_client.check_preflight()
        assert preflight2.is_available is False
        assert preflight2.reason == "low_memory"

        # Test level 4 (Critical)
        mock_sub.return_value = MagicMock(returncode=0, stdout="vm.memory_pressure: 4")
        preflight4 = ollama_client.check_preflight()
        assert preflight4.is_available is False
        assert preflight4.reason == "low_memory"

    @patch("subprocess.run")
    def test_memory_pressure_cli_fallback_and_fail_closed(self, mock_sub):
        # Test sysctl fails, memory_pressure CLI returns warning
        def mock_run(cmd, **kwargs):
            if cmd[0] == "sysctl":
                return MagicMock(returncode=1, stdout="")
            else:
                return MagicMock(returncode=0, stdout="System-wide memory pressure level: Warning")

        mock_sub.side_effect = mock_run
        ollama_client = OllamaAdvisoryClient()
        preflight = ollama_client.check_preflight()
        assert preflight.is_available is False
        assert preflight.reason == "low_memory"

        # Test sysctl and memory_pressure CLI both fail (Fail closed)
        mock_sub.side_effect = Exception("CLI error")
        preflight_fail = ollama_client.check_preflight()
        assert preflight_fail.is_available is False
        assert preflight_fail.reason == "preflight_parse_error"
        assert "verified reliably" in preflight_fail.message

    def test_one_request_concurrency_lock(self):
        ollama_client = OllamaAdvisoryClient()
        assert ollama_client._analysis_lock.acquire(blocking=False) is True
        
        # Second attempt while locked
        preflight = ollama_client.check_preflight()
        assert preflight.is_available is False
        assert preflight.reason == "busy"
        
        ollama_client._analysis_lock.release()

    @patch("httpx.Client.post")
    def test_cancellation_and_fallback(self, mock_post):
        mock_post.side_effect = httpx.ConnectError("Ollama disconnected")
        ollama_client = OllamaAdvisoryClient()
        timeline = [TimelineEntry(entry_id="e1", record_id="r1", sender="user@test.com", timestamp="2026-08-03T10:00:00Z", body_preview="hello")]
        
        result = ollama_client.analyze_conversation(timeline)
        assert result.category == CategoryEnum.NEEDS_REVIEW
        assert result.is_uncertain is True
        assert result.confidence == 0.0

    @patch("httpx.Client.post")
    def test_model_unloading_invariant(self, mock_post):
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {"response": '{"category": "InEvaluation", "confidence": 0.9, "summary": "Ok"}'}
        mock_post.return_value = mock_res

        ollama_client = OllamaAdvisoryClient()
        timeline = [TimelineEntry(entry_id="e1", record_id="r1", sender="user@test.com", timestamp="2026-08-03T10:00:00Z", body_preview="hello")]
        
        ollama_client.analyze_conversation(timeline)
        assert mock_post.called
        call_json = mock_post.call_args.kwargs.get("json", {})
        assert call_json.get("keep_alive") == 0

    def test_forged_decision_rejection(self):
        # Test submitting without valid server advisory_id is rejected (400)
        res = client.post("/api/v1/records/syn-rec-001/advisory-decision", json={
            "decision": "apply",
            "suggested_category": "InEvaluation"
        })
        assert res.status_code == 400
        assert "Valid server advisory token required" in res.json()["detail"]

    def test_replay_attack_prevention(self):
        # Create a mock valid server advisory
        record = get_synthetic_record_by_id("syn-rec-001")
        latest_id = record.timeline[-1].entry_id if record.timeline else None
        now_dt = datetime.now(timezone.utc)
        adv_id = "adv_test_replay_01"
        _advisory_registry[adv_id] = ServerStoredAdvisory(
            advisory_id=adv_id,
            record_id="syn-rec-001",
            conversation_id=record.conversation_id,
            graph_immutable_id=record.graph_immutable_id,
            latest_entry_id=latest_id,
            suggested_category=CategoryEnum.IN_EVALUATION,
            target_domain_status=DomainStatus.IN_EVALUATION,
            confidence=0.9,
            created_at=now_dt.isoformat(),
            expires_at=(now_dt + timedelta(minutes=15)).isoformat(),
            nonce="nonce01",
            consumed=False
        )

        # First use succeeds
        res1 = client.post("/api/v1/records/syn-rec-001/advisory-decision", json={
            "decision": "apply",
            "advisory_id": adv_id
        })
        assert res1.status_code == 200

        # Second use (replay) must fail (400)
        res2 = client.post("/api/v1/records/syn-rec-001/advisory-decision", json={
            "decision": "apply",
            "advisory_id": adv_id
        })
        assert res2.status_code == 400
        assert "replay attack rejected" in res2.json()["detail"]

    def test_cross_record_reuse_rejection(self):
        record = get_synthetic_record_by_id("syn-rec-001")
        now_dt = datetime.now(timezone.utc)
        adv_id = "adv_test_cross_01"
        _advisory_registry[adv_id] = ServerStoredAdvisory(
            advisory_id=adv_id,
            record_id="syn-rec-001",  # Bound to syn-rec-001
            conversation_id=record.conversation_id,
            suggested_category=CategoryEnum.IN_EVALUATION,
            target_domain_status=DomainStatus.IN_EVALUATION,
            confidence=0.9,
            created_at=now_dt.isoformat(),
            expires_at=(now_dt + timedelta(minutes=15)).isoformat(),
            nonce="nonce02",
            consumed=False
        )

        # Attempt to apply to syn-rec-002 must fail (400)
        res = client.post("/api/v1/records/syn-rec-002/advisory-decision", json={
            "decision": "apply",
            "advisory_id": adv_id
        })
        assert res.status_code == 400
        assert "cross-record reuse rejected" in res.json()["detail"]

    def test_expired_advisory_rejection(self):
        record = get_synthetic_record_by_id("syn-rec-001")
        old_dt = datetime.now(timezone.utc) - timedelta(minutes=30)
        adv_id = "adv_test_expired_01"
        _advisory_registry[adv_id] = ServerStoredAdvisory(
            advisory_id=adv_id,
            record_id="syn-rec-001",
            conversation_id=record.conversation_id,
            suggested_category=CategoryEnum.IN_EVALUATION,
            target_domain_status=DomainStatus.IN_EVALUATION,
            confidence=0.9,
            created_at=(old_dt - timedelta(minutes=15)).isoformat(),
            expires_at=old_dt.isoformat(), # Expired 30 mins ago
            nonce="nonce03",
            consumed=False
        )

        res = client.post("/api/v1/records/syn-rec-001/advisory-decision", json={
            "decision": "apply",
            "advisory_id": adv_id
        })
        assert res.status_code == 400
        assert "expired" in res.json()["detail"]

    def test_stale_anchor_and_newer_message_invalidation(self):
        record = get_synthetic_record_by_id("syn-rec-001")
        now_dt = datetime.now(timezone.utc)
        adv_id = "adv_test_stale_01"
        _advisory_registry[adv_id] = ServerStoredAdvisory(
            advisory_id=adv_id,
            record_id="syn-rec-001",
            conversation_id=record.conversation_id,
            latest_entry_id="old_message_id_999", # Stale anchor
            suggested_category=CategoryEnum.IN_EVALUATION,
            target_domain_status=DomainStatus.IN_EVALUATION,
            confidence=0.9,
            created_at=now_dt.isoformat(),
            expires_at=(now_dt + timedelta(minutes=15)).isoformat(),
            nonce="nonce04",
            consumed=False
        )

        res = client.post("/api/v1/records/syn-rec-001/advisory-decision", json={
            "decision": "apply",
            "advisory_id": adv_id
        })
        assert res.status_code == 400
        assert "Stale advisory token invalidated" in res.json()["detail"]

    @patch("backend.app.api.routes.ollama_client.analyze_conversation")
    def test_raw_id_hiding_in_ui_response(self, mock_analyze):
        mock_analyze.return_value = LLMAdvisoryResult(
            category=CategoryEnum.POSITION_CLOSED,
            confidence=0.95,
            summary="Position closed",
            evidence_entry_ids=["te-001b"],
            is_uncertain=False,
            reasoning="Reasoning text"
        )

        res = client.post("/api/v1/records/syn-rec-001/analyze")
        assert res.status_code == 200
        data = res.json()
        assert "advisory_id" in data
        assert "sanitized_evidence" in data
        # Ensure sanitized_evidence does NOT contain raw immutable Graph IDs like AAMk...
        for label in data["sanitized_evidence"]:
            assert "AAMk" not in label
            assert "AAQk" not in label

    def test_no_auto_close_mapping(self):
        record = get_synthetic_record_by_id("syn-rec-001")
        latest_id = record.timeline[-1].entry_id if record.timeline else None
        now_dt = datetime.now(timezone.utc)
        adv_id = "adv_test_no_close_01"
        _advisory_registry[adv_id] = ServerStoredAdvisory(
            advisory_id=adv_id,
            record_id="syn-rec-001",
            conversation_id=record.conversation_id,
            latest_entry_id=latest_id,
            suggested_category=CategoryEnum.POSITION_CLOSED,
            target_domain_status=DomainStatus.MANAGER_ACTION_REQUIRED, # Must NEVER map to CLOSED
            confidence=0.9,
            created_at=now_dt.isoformat(),
            expires_at=(now_dt + timedelta(minutes=15)).isoformat(),
            nonce="nonce05",
            consumed=False
        )

        res = client.post("/api/v1/records/syn-rec-001/advisory-decision", json={
            "decision": "apply",
            "advisory_id": adv_id
        })
        assert res.status_code == 200
        data = res.json()
        assert data["domain_status"] == "ManagerActionRequired"
        assert data["domain_status"] != "Closed"
