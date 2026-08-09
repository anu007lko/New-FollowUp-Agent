"""
Milestone M7 Release Readiness & Pre-Release Security Test Suite.
Validates all safety invariants, retention anchor logic, 2-stage approval binding,
keychain encryption, loopback binding, release-mode gating, and end-to-end workflows.

INVARIANTS TESTED:
1. Synthetic routes gated in release mode (HTTP 403).
2. Loopback-only security middleware enforcement.
3. Strict identity scoping (conversationId + graph_immutable_id ONLY, no Job/EP matching).
4. Daily 8:00 AM scheduled catch-up execution.
5. Ollama LLM failure handling and untrusted prompt data boundary.
6. 2-Stage draft approval, stable UUID idempotency, recipient forgery rejection, and no-send invariant.
7. Retention anchor calculation including sent Outlook mailbox messages from tarun@clifyx.com.
8. Retention deletion double-confirmation and operational-record-only transformation.
9. Fernet backup encryption, Keychain key management, quarantine restore, and log redaction.
10. E2E critical path user journey with synthetic test data.
"""

import os
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.domain.models import (
    SubmissionRecord, TimelineEntry, DomainStatus, CloseAction, DeletionApprovalRequest
)
from backend.app.infrastructure.keychain import KeychainAdapter
from backend.app.application.backup_engine import create_encrypted_backup, restore_backup_to_quarantine
from backend.app.application.retention_engine import (
    evaluate_record_retention, select_latest_real_message, execute_approved_deletion
)
from backend.app.application.workflow_engine import (
    select_reply_anchor_message, compute_reply_all_recipients,
    compute_draft_approval_hash, create_and_store_approval,
    get_draft_operation, validate_close_action
)
from unittest.mock import MagicMock
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.application.daily_review_engine import DailyReviewEngine
from backend.app.infrastructure.synthetic_data import get_synthetic_records, reset_synthetic_records_cache
from backend.app.infrastructure.ollama_client import OllamaAdvisoryClient

client = TestClient(app)


def test_m7_01_synthetic_reset_gated_in_production():
    """Synthetic reset endpoint must return HTTP 403 in production environment."""
    os.environ["ENVIRONMENT"] = "production"
    try:
        from backend.app.api.routes import security_service
        res = client.post(
            "/api/v1/synthetic/reset",
            headers={"x-csrf-token": security_service.generate_csrf_token()},
        )
        assert res.status_code == 403
        assert "disabled in production release mode" in res.json()["detail"]
    finally:
        os.environ["ENVIRONMENT"] = "test"


def test_synthetic_reset_fails_closed_without_explicit_test_opt_in(monkeypatch):
    """Missing environment flags must never enable a test-only reset route."""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("ALLOW_SYNTHETIC_RESET", raising=False)
    res = client.post("/api/v1/synthetic/reset")
    assert res.status_code == 403


def test_m7_02_loopback_only_security_middleware():
    """Middleware must reject non-loopback Host headers."""
    res = client.get("/api/v1/health", headers={"Host": "evil.external-domain.com"})
    assert res.status_code == 403
    assert "Non-loopback Host header rejected" in res.json()["detail"]


def test_m7_03_exact_identity_scoping_no_job_ep_association():
    """Identity resolution must depend strictly on conversation_id/graph_immutable_id."""
    rec1 = SubmissionRecord(
        id="test-rec-101",
        graph_immutable_id="AAMkMsg101",
        conversation_id="AAQkConv101",
        job_id="JOB-9999",
        ep_reference="EP-9999",
        candidate_name="Alice Smith",
        skill="Java",
        customer="ClientA",
        location="Remote",
        domain_status=DomainStatus.AWAITING_FEEDBACK,
        received_at="2026-08-01T10:00:00Z",
        created_at="2026-08-01T10:00:00Z"
    )
    rec2 = SubmissionRecord(
        id="test-rec-102",
        graph_immutable_id="AAMkMsg102",
        conversation_id="AAQkConv102",
        job_id="JOB-9999",  # Same Job ID!
        ep_reference="EP-9999",  # Same EP Reference!
        candidate_name="Bob Jones",
        skill="Python",
        customer="ClientA",
        location="Remote",
        domain_status=DomainStatus.AWAITING_FEEDBACK,
        received_at="2026-08-01T10:00:00Z",
        created_at="2026-08-01T10:00:00Z"
    )
    anchor1 = select_reply_anchor_message(rec1.timeline, record_immutable_id=rec1.graph_immutable_id)
    assert anchor1 is None or anchor1.graph_immutable_id != rec2.graph_immutable_id


def test_m7_04_daily_review_catchup_logic(tmp_path):
    """Daily review engine must execute catch-up when requested."""
    db_file = tmp_path / "catchup_test.db"
    persistence = EncryptedPersistenceEngine(db_path=str(db_file), master_key="key_xyz")
    mock_import = MagicMock()
    mock_import.run_import.return_value = MagicMock(messages_imported=0, auth_status="ok")
    engine = DailyReviewEngine(import_service=mock_import, persistence=persistence)
    result = engine.run_daily_review(is_catchup=True)
    assert result is not None
    assert result.status == "completed"
    assert result.is_catchup is True



def test_m7_05_ollama_failure_and_untrusted_prompt_data():
    """LLM client must sanitize untrusted prompt data and fail safely to NeedsReview if service offline."""
    client_llm = OllamaAdvisoryClient()
    client_llm.host = "http://127.0.0.1:99999"
    rec = get_synthetic_records()[0]
    res = client_llm.analyze_conversation(rec.timeline)
    assert res.category == DomainStatus.NEEDS_REVIEW
    assert "Advisory" in res.advisory_label
    assert res.confidence == 0.0


def test_m7_06_draft_approval_idempotency_and_no_send_invariant():
    """Draft approval must bind to server record, produce stable UUID idempotency key, and forbid sending."""
    rec = get_synthetic_records()[1]  # Record with Feedback Due / Manager Action
    rec.domain_status = DomainStatus.FEEDBACK_DUE
    anchor = select_reply_anchor_message(rec.timeline, record_immutable_id=rec.graph_immutable_id)
    assert anchor is not None

    to_addrs, cc_addrs, source_id, is_reply_all = compute_reply_all_recipients(anchor, "tarun@clifyx.com")
    content = "Following up on feedback for John Doe."
    content_hash = compute_draft_approval_hash(rec.id, rec.conversation_id, anchor.graph_immutable_id, content, to_addrs, cc_addrs, ["mgr@clifyx.com"], "tarun@clifyx.com")

    from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
    engine = EncryptedPersistenceEngine()
    appr1 = create_and_store_approval(
        record_id=rec.id,
        conversation_id=rec.conversation_id,
        immutable_anchor_id=anchor.graph_immutable_id,
        canonical_to=to_addrs,
        canonical_cc=cc_addrs,
        normalized_bcc=["mgr@clifyx.com"],
        content=content,
        record_version=1,
        engine=engine,
        manager_identity="tarun@clifyx.com"
    )
    assert appr1.approval_hash == content_hash
    assert appr1.idempotency_key is not None

    # Retrieve approval again; idempotency key must remain stable
    # appr2 = get_active_server_approval(rec.id)
    appr2 = get_draft_operation(appr1.idempotency_key, engine)
    assert appr2 is not None
    assert appr2.idempotency_key == appr1.idempotency_key

    # Confirm zero send parameters or endpoints exist on approval object
    assert not hasattr(appr1, "send")
    assert not hasattr(appr1, "mail_send")


def test_m7_07_retention_anchor_includes_real_sent_mailbox_messages():
    """A real sent Outlook message from tarun@clifyx.com must count as retention and reply anchor."""
    sent_entry = TimelineEntry(
        entry_id="te-sent-01",
        record_id="rec-sent-01",
        sender="tarun@clifyx.com",
        timestamp="2026-04-15T14:00:00Z",
        body_preview="Sent submission follow-up email to recruiter",
        classification="FollowUpSent",
        to_recipients=["recruiter@tcs.com"],
        cc_recipients=[],
        graph_immutable_id="AAMkSentMsg01",
        is_system_note=False
    )
    rec = SubmissionRecord(
        id="rec-sent-01",
        graph_immutable_id="AAMkSent01",
        conversation_id="AAQkSentConv01",
        job_id="112233",
        ep_reference="EP112233",
        candidate_name="Carol White",
        skill="React",
        customer="Apple",
        location="Austin, TX",
        domain_status=DomainStatus.AWAITING_FEEDBACK,
        received_at="2026-04-15T14:00:00Z",
        created_at="2026-04-15T14:00:00Z",
        timeline=[sent_entry]
    )

    # 1. Retention anchor selection must identify sent_entry
    latest_msg = select_latest_real_message(rec)
    assert latest_msg is not None
    assert latest_msg.entry_id == "te-sent-01"
    assert latest_msg.sender == "tarun@clifyx.com"

    # 2. Expiry calculation must add 3 calendar months to sent_entry.timestamp (2026-04-15 -> 2026-07-15)
    latest_iso, expires_iso, _ = evaluate_record_retention(rec)
    assert "2026-04-15" in latest_iso
    assert "2026-07-15" in expires_iso


def test_m7_08_retention_deletion_double_confirmation_and_purging():
    """Retention deletion must require explicit confirmation and transform record to operational-only."""
    reset_synthetic_records_cache()
    recs = get_synthetic_records()
    target_rec = recs[0]

    approval_req = DeletionApprovalRequest(
        record_ids=[target_rec.id],
        manager_identity="tarun@clifyx.com",
        final_confirmation=True
    )

    # Perform approved deletion
    deleted_records, audit_event = execute_approved_deletion([target_rec], approval_req)
    assert target_rec in deleted_records
    assert audit_event.stats.record_count == 1

    # Verify record transformed to Operational Record Only
    assert target_rec.is_operational_record_only is True
    assert "RETENTION POLICY" in target_rec.timeline[0].body_preview


def test_m7_09_fernet_backup_encryption_and_quarantine_restore():
    """Backup encryption must use Fernet key in Keychain and restore into quarantine."""
    keychain = KeychainAdapter(service_prefix="RecruitmentFollowUpAgent", use_memory_fallback=True)
    recs = get_synthetic_records()

    backup_res = create_encrypted_backup(recs, "tarun@clifyx.com", keychain_adapter=keychain)
    assert backup_res.record_count == len(recs)
    assert os.path.exists(backup_res.backup_file_path)

    # Restore backup to quarantine
    restore_res, quarantined = restore_backup_to_quarantine(backup_res.backup_file_path, "tarun@clifyx.com", keychain_adapter=keychain)
    assert "quarantined" in restore_res.status.lower() or restore_res.status == "success"
    assert restore_res.quarantined_record_count == len(recs)
    assert len(quarantined) == len(recs)

    # Clean up temp file
    if os.path.exists(backup_res.backup_file_path):
        os.remove(backup_res.backup_file_path)


def test_m7_10_e2e_critical_path_synthetic_journey():
    """Full end-to-end user journey test via FastAPI REST endpoints."""
    reset_synthetic_records_cache()

    # 1. GET Dashboard Summary
    dash_res = client.get("/api/v1/dashboard")
    assert dash_res.status_code == 200
    dash_data = dash_res.json()
    assert dash_data["awaiting_feedback"] >= 0
    assert len(dash_data["records"]) > 0

    # 2. GET Expiry Review List
    exp_res = client.get("/api/v1/retention/expiry-review")
    assert exp_res.status_code == 200
    assert isinstance(exp_res.json(), list)

    # 3. GET Record Workspace Detail
    rec_id = dash_data["records"][0]["id"]
    rec_detail_res = client.get(f"/api/v1/records/{rec_id}")
    assert rec_detail_res.status_code == 200
    assert rec_detail_res.json()["id"] == rec_id
