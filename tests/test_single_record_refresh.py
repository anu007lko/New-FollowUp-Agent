import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.api.routes import security_service, daily_review_engine
from backend.app.application.daily_review_engine import DailyReviewEngine, SingleRecordRefreshStatus, SingleRecordRefreshResult
from backend.app.domain.models import SubmissionRecord, DomainStatus

client = TestClient(app, base_url="http://127.0.0.1:8000")


# --- Endpoint Authorization / CSRF Tests ---

def test_refresh_single_record_endpoint_requires_csrf(monkeypatch):
    """POST /api/v1/records/{id}/refresh must enforce CSRF protection in manager_local mode."""
    monkeypatch.setenv("READ_ONLY", "False")
    monkeypatch.setenv("APP_MODE", "manager_local")
    response = client.post(
        "/api/v1/records/rec-001/refresh",
        headers={"Host": "127.0.0.1:8000", "Origin": "http://127.0.0.1:8000"},
    )
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]


def test_refresh_single_record_endpoint_csrf_authorized(monkeypatch):
    """POST /api/v1/records/{id}/refresh proceeds when valid CSRF token and loopback headers are supplied."""
    monkeypatch.setenv("READ_ONLY", "False")
    monkeypatch.setenv("APP_MODE", "manager_local")
    csrf_token = security_service.generate_csrf_token()
    headers = {
        "Host": "127.0.0.1:8000",
        "Origin": "http://127.0.0.1:8000",
        "X-CSRF-Token": csrf_token
    }
    with patch.object(daily_review_engine, "refresh_single_record") as mock_refresh:
        mock_refresh.return_value = SingleRecordRefreshResult(
            status=SingleRecordRefreshStatus.NOT_FOUND,
            error_message="Record not found"
        )
        response = client.post("/api/v1/records/rec-001/refresh", headers=headers)
        assert response.status_code == 404
        mock_refresh.assert_called_once_with("rec-001")


def test_refresh_single_record_endpoint_status_code_mapping(monkeypatch):
    """Verify endpoint maps SingleRecordRefreshResult statuses to 404, 503, 409, and 200 correctly."""
    monkeypatch.setenv("READ_ONLY", "False")
    monkeypatch.setenv("APP_MODE", "manager_local")
    csrf_token = security_service.generate_csrf_token()
    headers = {
        "Host": "127.0.0.1:8000",
        "Origin": "http://127.0.0.1:8000",
        "X-CSRF-Token": csrf_token
    }

    # 503 - REFRESH_DISABLED
    with patch.object(daily_review_engine, "refresh_single_record") as mock_refresh:
        mock_refresh.return_value = SingleRecordRefreshResult(
            status=SingleRecordRefreshStatus.REFRESH_DISABLED,
            error_message="Disabled"
        )
        resp = client.post("/api/v1/records/rec-001/refresh", headers=headers)
        assert resp.status_code == 503
        assert "disabled" in resp.json()["detail"].lower()

    # 409 - CONFLICT
    with patch.object(daily_review_engine, "refresh_single_record") as mock_refresh:
        mock_refresh.return_value = SingleRecordRefreshResult(
            status=SingleRecordRefreshStatus.CONFLICT,
            error_message="Conflict"
        )
        resp = client.post("/api/v1/records/rec-001/refresh", headers=headers)
        assert resp.status_code == 409
        assert "conflict" in resp.json()["detail"].lower()

    # 404 - NOT_FOUND
    with patch.object(daily_review_engine, "refresh_single_record") as mock_refresh:
        mock_refresh.return_value = SingleRecordRefreshResult(
            status=SingleRecordRefreshStatus.NOT_FOUND,
            error_message="Not found"
        )
        resp = client.post("/api/v1/records/rec-001/refresh", headers=headers)
        assert resp.status_code == 404

    # 200 - SUCCESS
    with patch.object(daily_review_engine, "refresh_single_record") as mock_refresh:
        dummy_rec = SubmissionRecord(
            id="rec-001",
            candidate_name="Jane Doe",
            candidate_email="jane@example.com",
            job_title="Engineer",
            submitting_ep="Agency A",
            submitted_at="2026-08-01T10:00:00Z", received_at="2026-08-01T10:00:00Z", created_at="2026-08-01T10:00:00Z",
            domain_status=DomainStatus.AWAITING_RESPONSE,
            graph_immutable_id="graph-001",
            conversation_id="conv-001"
        )
        mock_refresh.return_value = SingleRecordRefreshResult(
            status=SingleRecordRefreshStatus.SUCCESS,
            record=dummy_rec
        )
        resp = client.post("/api/v1/records/rec-001/refresh", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == "rec-001"


# --- Unit Tests for Engine Behaviour ---

def test_refresh_single_record_unknown_record():
    engine = DailyReviewEngine()
    engine.persistence = MagicMock()
    engine.persistence.get_record_by_id.return_value = None
    engine.persistence.get_record_payload_snapshot.return_value = None
    
    result = engine.refresh_single_record("unknown-id")
    assert result.status == SingleRecordRefreshStatus.NOT_FOUND
    assert result.record is None
    engine.persistence.update_record_optimistically.assert_not_called()


def test_refresh_single_record_refresh_disabled():
    engine = DailyReviewEngine()
    engine._mailbox_refresh_enabled = False
    engine.persistence = MagicMock()
    engine.graph_client = MagicMock()

    result = engine.refresh_single_record("rec-001")
    assert result.status == SingleRecordRefreshStatus.REFRESH_DISABLED
    engine.graph_client.fetch_exact_conversation_messages.assert_not_called()
    engine.persistence.update_record_optimistically.assert_not_called()


def test_refresh_single_record_optimistic_conflict():
    engine = DailyReviewEngine()
    engine.persistence = MagicMock()
    engine.graph_client = MagicMock()

    mock_payload = {
        "conversation_id": "conv-1",
        "thread_messages": [{"id": "msg-1", "bodyPreview": "Test"}],
        "graph_immutable_id": "imm-1",
        "classification_status": "AwaitingResponse",
        "classification_category": "category",
        "reason_code": "reason",
        "timer_anchor_type": None
    }
    engine.persistence.get_record_by_id.return_value = MagicMock()
    engine.persistence.get_record_payload_snapshot.return_value = (mock_payload.copy(), 1, "AwaitingResponse")
    engine.graph_client.fetch_exact_conversation_messages.return_value = (
        [{"id": "msg-1", "bodyPreview": "Test"}, {"id": "msg-2", "bodyPreview": "New message"}], "ok"
    )
    # Simulate optimistic concurrency conflict during database write
    engine.persistence.update_record_optimistically.side_effect = ValueError("Version conflict")

    result = engine.refresh_single_record("rec-001")
    assert result.status == SingleRecordRefreshStatus.CONFLICT
    assert "conflict" in result.error_message.lower()


def test_refresh_single_record_no_change_success():
    engine = DailyReviewEngine()
    engine.persistence = MagicMock()
    engine.graph_client = MagicMock()
    dummy_rec = MagicMock()
    engine.persistence.get_record_by_id.return_value = dummy_rec

    mock_payload = {
        "conversation_id": "conv-1",
        "thread_messages": [{"id": "msg-1", "bodyPreview": "Test"}],
        "graph_immutable_id": "imm-1",
        "classification_status": "AwaitingResponse",
        "classification_category": "category",
        "reason_code": "reason",
        "timer_anchor_type": None
    }
    engine.persistence.get_record_payload_snapshot.return_value = (mock_payload, 1, "AwaitingResponse")
    engine.graph_client.fetch_exact_conversation_messages.return_value = (
        [{"id": "msg-1", "bodyPreview": "Test"}], "ok"
    )

    with patch('backend.app.application.daily_review_engine.classify_record') as mock_classify:
        mock_classify.return_value = MagicMock(
            proposed_status="AwaitingResponse",
            category="category",
            reason_code="reason",
            timer_anchor_type=None
        )
        result = engine.refresh_single_record("record-1")

    assert result.status == SingleRecordRefreshStatus.SUCCESS
    assert result.record == dummy_rec
    engine.persistence.update_record_optimistically.assert_not_called()


def test_refresh_single_record_changed_success_and_scope():
    engine = DailyReviewEngine()
    engine.persistence = MagicMock()
    engine.graph_client = MagicMock()
    engine.import_service = MagicMock()
    dummy_rec = MagicMock()
    engine.persistence.get_record_by_id.return_value = dummy_rec

    mock_payload = {
        "conversation_id": "conv-1",
        "thread_messages": [{"id": "msg-1", "bodyPreview": "Test"}],
        "graph_immutable_id": "imm-1",
        "classification_status": "AwaitingResponse",
        "classification_category": "category",
        "reason_code": "reason",
        "timer_anchor_type": None
    }
    engine.persistence.get_record_payload_snapshot.return_value = (mock_payload.copy(), 1, "AwaitingResponse")
    engine.graph_client.fetch_exact_conversation_messages.return_value = (
        [{"id": "msg-1", "bodyPreview": "Test"}, {"id": "msg-2", "bodyPreview": "New reply"}], "ok"
    )

    with patch('backend.app.application.daily_review_engine.classify_record') as mock_classify:
        mock_classify.return_value = MagicMock(
            proposed_status="AwaitingResponse",
            category="category",
            reason_code="reason",
            timer_anchor_type=None
        )
        result = engine.refresh_single_record("target-record-123")

    assert result.status == SingleRecordRefreshStatus.SUCCESS
    # Ensure update_record_optimistically was called ONLY for target-record-123
    engine.persistence.update_record_optimistically.assert_called_once()
    args, _ = engine.persistence.update_record_optimistically.call_args
    assert args[0] == "target-record-123"

    # Confirm scope bounds: no import_service or global list_records
    engine.import_service.run_import.assert_not_called()
    engine.persistence.list_records.assert_not_called()
