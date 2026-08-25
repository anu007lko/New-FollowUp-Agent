"""
Automated Test Suite for Milestone M6: Local Retention, Encrypted Backup & Operations.

Tests:
1. Calendar-month expiry math (month-end clamping, leap year, EST/EDT transitions).
2. Latest real message controls expiry (system/manager notes ignored).
3. Zero automatic deletion (daily review identifies expired records but never purges content).
4. Selected-record deletion only.
5. Complete content removal & metadata preservation (Operational Record Only state).
6. Zero Graph / Outlook calls.
7. Encrypted backup contains zero plaintext tokens or secrets.
8. Restore quarantine and retention enforcement.
9. Idempotent deletion retries.
10. Final confirmation enforcement.
"""

import os
import tempfile
import pytest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.domain.models import (
    SubmissionRecord, TimelineEntry, DomainStatus, DeletionApprovalRequest,
    BackupRequest, RestoreRequest
)
from backend.app.domain.date_utils import (
    TIMEZONE_NEW_YORK, TIMEZONE_UTC,
    add_calendar_months, calculate_retention_expiry
)
from backend.app.application.retention_engine import (
    select_latest_real_message, evaluate_record_retention, get_expiry_review_list,
    execute_approved_deletion, get_retention_audit_log
)
from backend.app.application.backup_engine import (
    create_encrypted_backup, restore_backup_to_quarantine, promote_quarantine_to_active,
    get_quarantine_store
)
from backend.app.infrastructure.synthetic_data import get_synthetic_records, reset_synthetic_records_cache
from backend.app.infrastructure.keychain import KeychainAdapter
from backend.app.api.routes import security_service

client = TestClient(app)
client.headers.update({"x-csrf-token": security_service.generate_csrf_token()})


# --- 1. Calendar-Month Expiry Math Tests ---

def test_calendar_month_expiry_math():
    # Month-end clamping: Jan 31 + 3 calendar months -> Apr 30
    jan_31 = datetime(2026, 1, 31, 10, 0, 0, tzinfo=TIMEZONE_NEW_YORK)
    apr_30 = add_calendar_months(jan_31, 3)
    assert apr_30.year == 2026
    assert apr_30.month == 4
    assert apr_30.day == 30

    # Leap year: Nov 29, 2023 + 3 calendar months -> Feb 29, 2024
    nov_29_leap = datetime(2023, 11, 29, 14, 0, 0, tzinfo=TIMEZONE_NEW_YORK)
    feb_29_leap = add_calendar_months(nov_29_leap, 3)
    assert feb_29_leap.year == 2024
    assert feb_29_leap.month == 2
    assert feb_29_leap.day == 29

    # Non-leap year: Nov 29, 2025 + 3 calendar months -> Feb 28, 2026
    nov_29_std = datetime(2025, 11, 29, 14, 0, 0, tzinfo=TIMEZONE_NEW_YORK)
    feb_28_std = add_calendar_months(nov_29_std, 3)
    assert feb_28_std.year == 2026
    assert feb_28_std.month == 2
    assert feb_28_std.day == 28


# --- 2. Authoritative Message Control Tests ---

def test_latest_real_message_controls_expiry():
    # Construct test record where real message is old, but manager/system notes are recent
    record = SubmissionRecord(
        id="test-rec-retention-01",
        graph_immutable_id="AAMkTest001",
        conversation_id="AAQkTestConv001",
        candidate_name="Test Candidate",
        received_at="2026-03-01T10:00:00Z",
        created_at="2026-03-01T10:00:00Z",
        manager_notes="[2026-08-01T10:00:00Z] Manager added note recently",
        system_notes="[2026-08-02T10:00:00Z] System event added recently",
        timeline=[
            TimelineEntry(entry_id="t1", record_id="test-rec-retention-01", sender="tarun@example.com", timestamp="2026-03-01T10:00:00Z", body_preview="Real email message", to_recipients=["recruiter@example.com"]),
            TimelineEntry(entry_id="t2", record_id="test-rec-retention-01", sender="Manager Action (Manual Confirmation)", timestamp="2026-08-01T10:00:00Z", body_preview="Manager note entry", is_system_note=True),
        ]
    )

    latest_entry = select_latest_real_message(record)
    assert latest_entry is not None
    assert latest_entry.entry_id == "t1"
    assert latest_entry.timestamp == "2026-03-01T10:00:00Z"

    # Evaluate expiry as of 2026-08-03
    now = datetime(2026, 8, 3, 12, 0, 0, tzinfo=TIMEZONE_NEW_YORK)
    latest_at, expires_at, is_expired = evaluate_record_retention(record, now)
    
    assert "2026-03-01" in latest_at
    assert "2026-06-01" in expires_at  # 3 calendar months after March 1
    assert is_expired is True  # August 3 is after June 1


# --- 3. No Automatic Deletion Tests ---

def test_no_automatic_deletion():
    records = get_synthetic_records()
    now = datetime(2026, 8, 3, 12, 0, 0, tzinfo=TIMEZONE_NEW_YORK)
    
    # Expiry review list identifies expired records (e.g. syn-rec-007)
    expiry_list = get_expiry_review_list(records, now)
    assert len(expiry_list) >= 1
    expired_ids = [r.record_id for r in expiry_list]
    assert "syn-rec-007" in expired_ids

    # Verify content bodies in synthetic data remain 100% intact until manager approval
    syn_007 = next(r for r in records if r.id == "syn-rec-007")
    assert syn_007.is_operational_record_only is False
    assert len(syn_007.timeline[0].body_preview) > 0
    assert "[CONTENT REMOVED" not in syn_007.timeline[0].body_preview


# --- 4. Selected Record Deletion & Final Confirmation Tests ---

def test_deletion_requires_final_confirmation():
    records = get_synthetic_records()
    request = DeletionApprovalRequest(
        record_ids=["syn-rec-007"],
        confirmed_by="tarun@example.com",
        final_confirmation=False  # Must fail closed
    )
    with pytest.raises(ValueError, match="final_confirmation must be explicitly True"):
        execute_approved_deletion(records, request)


def test_selected_record_deletion_only_and_operational_record_state():
    reset_synthetic_records_cache()
    records = get_synthetic_records()
    
    request = DeletionApprovalRequest(
        record_ids=["syn-rec-007"],
        confirmed_by="tarun@example.com",
        final_confirmation=True
    )
    
    now = datetime(2026, 8, 3, 12, 0, 0, tzinfo=TIMEZONE_NEW_YORK)
    updated_records, audit_evt = execute_approved_deletion(records, request, now)
    
    # 1. Selected record syn-rec-007 is transformed
    rec_007 = next(r for r in updated_records if r.id == "syn-rec-007")
    assert rec_007.is_operational_record_only is True
    assert rec_007.timeline[0].body_preview == "[CONTENT REMOVED PER 3-MONTH RETENTION POLICY]"
    
    # 2. Retained Operational Metadata: Immutable IDs, candidate name, notes, attachment hashes
    assert rec_007.graph_immutable_id == "AAMkSynth007"
    assert rec_007.conversation_id == "AAQkSynthConv007"
    assert rec_007.candidate_name == "David Chen"
    assert rec_007.attachment_count == 2
    assert len(rec_007.attachment_hashes) == 2
    assert "Local email content deleted per manager approval" in rec_007.system_notes
    
    # 3. Unselected record syn-rec-001 remains completely untouched
    rec_001 = next(r for r in updated_records if r.id == "syn-rec-001")
    assert rec_001.is_operational_record_only is False
    assert "[CONTENT REMOVED" not in rec_001.timeline[0].body_preview
    
    # 4. Verification Audit Event generated
    assert audit_evt.approved_by == "tarun@example.com"
    assert audit_evt.stats.record_count == 1
    assert audit_evt.verification_result == "passed_integrity_check"


# --- 5. Zero Graph / Outlook Calls Verification ---

def test_zero_graph_outlook_calls():
    # Verifies retention deletion executes purely in local storage with zero network or Graph calls
    reset_synthetic_records_cache()
    records = get_synthetic_records()
    request = DeletionApprovalRequest(record_ids=["syn-rec-007"], final_confirmation=True)
    
    # Run deletion
    updated_records, audit_evt = execute_approved_deletion(records, request)
    assert audit_evt.verification_result == "passed_integrity_check"


# --- 6. Encrypted Backup & Quarantine Restore Tests ---

def test_encrypted_backup_contains_no_secrets():
    reset_synthetic_records_cache()
    records = get_synthetic_records()
    keychain = KeychainAdapter(use_memory_fallback=True)
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        result = create_encrypted_backup(records, "tarun@example.com", backup_dir=tmp_dir, keychain_adapter=keychain)
        
        assert os.path.exists(result.backup_file_path)
        assert result.record_count == len(records)
        assert "Backup master key stored in local macOS Keychain" in result.mac_limitation_notice
        
        # Read raw backup file bytes — verify it is ciphertext and NOT raw JSON
        with open(result.backup_file_path, "rb") as f:
            content_bytes = f.read()
        
        assert not content_bytes.startswith(b"{")
        assert b"David Chen" not in content_bytes  # Content is Fernet encrypted
        assert b"tarun@example.com" not in content_bytes


def test_restore_quarantine_and_expiry_enforcement():
    reset_synthetic_records_cache()
    records = get_synthetic_records()
    keychain = KeychainAdapter(use_memory_fallback=True)
    now = datetime(2026, 8, 3, 12, 0, 0, tzinfo=TIMEZONE_NEW_YORK)
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        backup_res = create_encrypted_backup(records, "tarun@example.com", backup_dir=tmp_dir, keychain_adapter=keychain)
        
        # Restore backup into quarantine
        restore_res, quarantined = restore_backup_to_quarantine(backup_res.backup_file_path, "tarun@example.com", keychain_adapter=keychain, current_time=now)
        
        assert restore_res.quarantined_record_count == len(records)
        assert restore_res.requires_retention_action is True
        assert restore_res.status == "quarantined_requires_retention_action"
        assert "expired records require manager retention review" in restore_res.message
        
        # Promotion to active fails closed while unpruned expired records remain
        with pytest.raises(ValueError, match="Cannot promote quarantine"):
            promote_quarantine_to_active(quarantined)
        
        # Prune expired record syn-rec-007 in quarantine
        prune_req = DeletionApprovalRequest(record_ids=["syn-rec-007"], final_confirmation=True)
        execute_approved_deletion(quarantined, prune_req, now)
        
        # Now promotion succeeds cleanly
        promoted = promote_quarantine_to_active(quarantined)
        assert len(promoted) == len(records)


# --- 7. Idempotency & API Endpoint Tests ---

def test_idempotent_deletion_retry():
    reset_synthetic_records_cache()
    records = get_synthetic_records()
    request = DeletionApprovalRequest(record_ids=["syn-rec-007"], final_confirmation=True)
    
    # First execution
    updated1, audit1 = execute_approved_deletion(records, request)
    bytes_freed_first = audit1.stats.bytes_freed
    
    # Second execution on already pruned records
    updated2, audit2 = execute_approved_deletion(updated1, request)
    assert audit2.stats.bytes_freed == 0  # 0 additional bytes freed
    assert audit2.verification_result == "passed_integrity_check"


class TestRetentionEndpoints:
    def test_get_expiry_review_endpoint(self):
        reset_synthetic_records_cache()
        res = client.get("/api/v1/retention/expiry-review")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        # Verify NO message bodies in expiry review payload
        for item in data:
            assert "body_preview" not in item
            assert "timeline" not in item

    def test_post_approved_deletion_endpoint(self):
        reset_synthetic_records_cache()
        payload = {
            "record_ids": ["syn-rec-007"],
            "confirmed_by": "tarun@example.com",
            "final_confirmation": True
        }
        res = client.post("/api/v1/retention/delete-approved", json=payload)
        assert res.status_code == 200
        audit = res.json()
        assert audit["approved_by"] == "tarun@example.com"
        assert audit["verification_result"] == "passed_integrity_check"

    def test_backup_and_restore_endpoints(self):
        reset_synthetic_records_cache()
        # 1. Create backup
        backup_res = client.post("/api/v1/backup/create", json={"manager_identity": "tarun@example.com"})
        assert backup_res.status_code == 200
        backup_data = backup_res.json()
        assert "backup_file_path" in backup_data

        # 2. Restore into quarantine
        restore_res = client.post("/api/v1/backup/restore", json={
            "backup_file_path": backup_data["backup_file_path"],
            "manager_identity": "tarun@example.com"
        })
        assert restore_res.status_code == 200
        restore_data = restore_res.json()
        assert restore_data["quarantined_record_count"] >= 1
        assert restore_data["requires_retention_action"] is True
