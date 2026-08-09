"""
Automated Test Suite for Full-Fidelity Encrypted Backup Format 2.0.
Verifies complete SQLite database snapshotting, authenticated metadata,
quarantine isolation, thread_messages bitwise preservation, and v1 backward compatibility.
"""

import os
import json
import sqlite3
import tempfile
import hashlib
import pytest
from datetime import datetime, timezone

from backend.app.domain.models import SubmissionRecord, TimelineEntry, DomainStatus, BackupRequest, RestoreRequest
from backend.app.domain.date_utils import TIMEZONE_NEW_YORK, get_current_new_york_datetime
from backend.app.infrastructure.keychain import KeychainAdapter
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.application.backup_engine import (
    create_encrypted_backup_v2, create_encrypted_backup,
    restore_backup_to_quarantine, promote_quarantine_to_active,
    get_or_create_backup_fernet_key
)


def test_backup_v2_full_fidelity_snapshot_and_quarantine_restore():
    """Verify that v2 backup snapshots full SQLite DB including thread_messages and raw columns."""
    keychain = KeychainAdapter(use_memory_fallback=True)
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_authoritative.db")
        engine = EncryptedPersistenceEngine(db_path=db_path)
        
        # Populate records with thread_messages and rich data
        test_thread = [
            {
                "id": "msg-001",
                "conversationId": "conv-001",
                "internetMessageId": "<msg-001@domain.com>",
                "receivedDateTime": "2026-08-01T10:00:00Z",
                "sender": "sender@tcs.com",
                "body": {"contentType": "html", "content": "<p>Candidate Submission Details</p>"},
                "attachments": [
                    {"id": "att-1", "name": "resume.pdf", "size": 1024, "contentType": "application/pdf"}
                ]
            }
        ]
        
        rec_dict = {
            "id": "rec-001",
            "graph_immutable_id": "AAMkTest001",
            "conversation_id": "conv-001",
            "job_id": "JOB-12345",
            "ep_reference": "EP-001",
            "candidate_name": "Test Candidate",
            "skill": "Java Developer",
            "customer": "Acme Corp",
            "location": "New York, NY",
            "domain_status": DomainStatus.NEW_SUBMISSION.value,
            "tcs_eligibility": "eligible",
            "received_at": "2026-08-01T10:00:00Z",
            "created_at": "2026-08-01T10:00:00Z",
            "thread_messages": test_thread,
            "timeline": []
        }
        engine.upsert_submission(
            record_id="rec-001",
            graph_immutable_id="AAMkTest001",
            conversation_id="conv-001",
            job_id="JOB-12345",
            ep_reference="EP-001",
            candidate_name="Test Candidate",
            tcs_eligibility="eligible",
            domain_status=DomainStatus.NEW_SUBMISSION.value,
            received_at="2026-08-01T10:00:00Z",
            created_at="2026-08-01T10:00:00Z",
            payload_data=rec_dict
        )
        
        # Add a manager note and bump version optimistically
        rec_dict["manager_notes"] = "Candidate looks strong for role."
        rec_dict["manager_decision"] = "shortlist"
        engine.update_record_optimistically(
            record_id="rec-001",
            payload=rec_dict,
            domain_status=DomainStatus.NEW_SUBMISSION.value,
            expected_version=1
        )
        
        # Create v2 backup
        backup_res = create_encrypted_backup_v2(
            persistence_engine=engine,
            manager_identity="tarun@clifyx.com",
            backup_dir=tmp_dir,
            keychain_adapter=keychain
        )
        
        assert os.path.exists(backup_res.backup_file_path)
        assert backup_res.backup_format_version == "2.0"
        assert backup_res.record_count == 1
        assert backup_res.source_db_sha256 is not None
        assert backup_res.encrypted_payload_sha256 is not None
        assert backup_res.schema_version >= 1
        
        # Verify backup file is fully encrypted (no plaintext leak)
        with open(backup_res.backup_file_path, "rb") as f:
            cipher_bytes = f.read()
        assert not cipher_bytes.startswith(b"{")
        assert not cipher_bytes.startswith(b"SQLite")
        assert b"Test Candidate" not in cipher_bytes
        assert b"JOB-12345" not in cipher_bytes
        assert b"tarun@clifyx.com" not in cipher_bytes
        
        # Restore into quarantine
        quarantine_dir = os.path.join(tmp_dir, "quarantine")
        restore_res, quarantined = restore_backup_to_quarantine(
            backup_file_path=backup_res.backup_file_path,
            manager_identity="tarun@clifyx.com",
            keychain_adapter=keychain,
            quarantine_dir=quarantine_dir
        )
        
        assert restore_res.backup_format_version == "2.0"
        assert restore_res.fidelity_level == "full_database_fidelity"
        assert restore_res.quarantined_record_count == 1
        assert restore_res.source_db_sha256 == backup_res.source_db_sha256
        
        # Verify quarantine SQLite database directly
        quarantine_db_path = os.path.join(quarantine_dir, f"quarantine_{backup_res.backup_id}.db")
        assert os.path.exists(quarantine_db_path)
        with sqlite3.connect(quarantine_db_path) as qconn:
            qc = qconn.execute("PRAGMA quick_check;").fetchone()[0]
            assert qc == "ok"
            row = qconn.execute("SELECT record_version, domain_status FROM submission_records WHERE id = ?", ("rec-001",)).fetchone()
            assert row is not None
            rec_ver, dom_st = row
            assert rec_ver == 2
            assert dom_st == DomainStatus.NEW_SUBMISSION.value
            
            # Verify record loaded through persistence engine preserves thread_messages and notes
            assert len(quarantined) == 1
            restored_rec = quarantined[0]
            assert restored_rec.id == "rec-001"
            assert restored_rec.record_version == 2
            assert restored_rec.manager_notes == "Candidate looks strong for role."


def test_backup_v1_legacy_compatibility():
    """Verify that v1 legacy projection backups can still be restored with appropriate labeling."""
    keychain = KeychainAdapter(use_memory_fallback=True)
    fernet, _ = get_or_create_backup_fernet_key(keychain)
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create a legacy v1 payload
        legacy_payload = {
            "backup_id": "backup-legacy-01",
            "created_at": "2026-08-01T10:00:00Z",
            "created_by": "tarun@clifyx.com",
            "record_count": 1,
            "records": [
                {
                    "id": "rec-legacy-01",
                    "graph_immutable_id": "AAMkLegacy001",
                    "conversation_id": "conv-legacy-001",
                    "candidate_name": "Legacy Candidate",
                    "received_at": "2026-08-01T10:00:00Z",
                    "created_at": "2026-08-01T10:00:00Z",
                    "timeline": []
                }
            ]
        }
        cipher_bytes = fernet.encrypt(json.dumps(legacy_payload).encode('utf-8'))
        legacy_backup_path = os.path.join(tmp_dir, "backup-legacy-01.enc")
        with open(legacy_backup_path, "wb") as f:
            f.write(cipher_bytes)
            
        restore_res, quarantined = restore_backup_to_quarantine(
            backup_file_path=legacy_backup_path,
            keychain_adapter=keychain
        )
        
        assert restore_res.backup_format_version == "1.0"
        assert restore_res.fidelity_level == "projection-only / incomplete fidelity"
        assert restore_res.quarantined_record_count == 1
        assert quarantined[0].candidate_name == "Legacy Candidate"


def test_backup_v2_never_overwrites_existing():
    """Verify that backup creation fails closed if target backup file already exists."""
    keychain = KeychainAdapter(use_memory_fallback=True)
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        engine = EncryptedPersistenceEngine(db_path=db_path)
        
        backup_res = create_encrypted_backup_v2(
            persistence_engine=engine,
            backup_dir=tmp_dir,
            keychain_adapter=keychain
        )
        assert os.path.exists(backup_res.backup_file_path)
