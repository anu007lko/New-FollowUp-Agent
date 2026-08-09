"""
Encrypted Local Backup & Quarantine Restore Engine for Milestone M6 & M7.
Uses reviewed authenticated-encryption library (cryptography.fernet.Fernet).
Backup encryption key is protected via macOS Keychain.

SAFETY INVARIANTS:
1. Never print or log encryption keys, backup contents, message bodies, or attachment data.
2. A backup must not become a way to restore content beyond its retention expiry. Every backup retains expiry metadata.
3. Restored content remains INACCESSIBLE in quarantine until the manager reviews and deletes expired content.
4. Outlook remains the source for rebuilding available mailbox content.
5. Keychain-only recovery is initially limited to this Mac.
"""

import os
import json
import uuid
import base64
import hashlib
import sqlite3
import tempfile
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Optional, Any
from cryptography.fernet import Fernet

from backend.app.domain.models import (
    SubmissionRecord, BackupResult, RestoreResult, ExpiryReviewSummary
)
from backend.app.domain.date_utils import (
    TIMEZONE_NEW_YORK, TIMEZONE_UTC, get_current_new_york_datetime
)
from backend.app.infrastructure.keychain import KeychainAdapter
from backend.app.application.retention_engine import (
    evaluate_record_retention, get_expiry_review_list, execute_approved_deletion
)

# Global in-memory Quarantine Store
_quarantine_store: List[SubmissionRecord] = []

# Module-level singleton KeychainAdapter for consistent key resolution
_is_test_env = (
    os.getenv("ENVIRONMENT", "").lower() == "test"
    or os.getenv("TESTING", "").lower() == "true"
    or os.getenv("PYTEST_CURRENT_TEST") is not None
)
_default_keychain_adapter = KeychainAdapter(service_prefix="RecruitmentFollowUpAgent", use_memory_fallback=_is_test_env)


def get_or_create_backup_fernet_key(keychain_adapter: Optional[KeychainAdapter] = None) -> Tuple[Fernet, str]:
    """
    Retrieve or create the master Fernet encryption key stored in macOS Keychain.
    Returns (Fernet instance, key_id).
    """
    adapter = keychain_adapter or _default_keychain_adapter
    service_name = "BackupKey"
    account_name = "MasterBackupKey"
    
    existing_key_str = adapter.get_secret(service_name, account_name)
    if existing_key_str:
        key_bytes = existing_key_str.encode('utf-8')
    else:
        new_key_bytes = Fernet.generate_key()
        key_str = new_key_bytes.decode('utf-8')
        adapter.set_secret(service_name, account_name, key_str)
        key_bytes = new_key_bytes
    
    key_id = f"keychain-fernet-{key_bytes[:8].decode('utf-8', errors='ignore')}"
    return Fernet(key_bytes), key_id


def create_encrypted_backup_v2(
    persistence_engine: Optional[Any] = None,
    manager_identity: str = "tarun@clifyx.com",
    backup_dir: Optional[str] = None,
    keychain_adapter: Optional[KeychainAdapter] = None
) -> BackupResult:
    """
    Create a version 2.0 full-fidelity encrypted local backup by snapshotting the complete
    authoritative SQLite database using SQLite's safe backup API.
    """
    from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
    engine = persistence_engine or EncryptedPersistenceEngine()
    
    fernet, key_id = get_or_create_backup_fernet_key(keychain_adapter)
    now_dt = get_current_new_york_datetime()
    now_str = now_dt.strftime("%Y-%m-%d_%H-%M-%S")
    timestamp_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    if not backup_dir:
        backup_dir = (
            os.path.join(tempfile.gettempdir(), "recruitment_agent_test", "backups")
            if _is_test_env else os.path.expanduser("~/.recruitment_agent/backups")
        )
    os.makedirs(backup_dir, exist_ok=True)
    
    backup_id = f"backup-{uuid.uuid4().hex[:8]}"
    backup_file_path = os.path.join(backup_dir, f"{backup_id}_{now_str}.enc")
    
    if os.path.exists(backup_file_path):
        raise FileExistsError(f"Backup file already exists: {backup_file_path}")

    # Use a secure temporary file for the plaintext SQLite snapshot
    temp_snapshot = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_snapshot_path = temp_snapshot.name
    temp_snapshot.close()

    try:
        # SQLite safe backup API
        with engine._get_connection() as src_conn, sqlite3.connect(temp_snapshot_path) as dst_conn:
            src_conn.backup(dst_conn)
        
        # Verify snapshot with PRAGMA quick_check
        with sqlite3.connect(temp_snapshot_path) as chk_conn:
            qc = chk_conn.execute("PRAGMA quick_check;").fetchone()[0]
            if qc != "ok":
                raise RuntimeError(f"Database snapshot failed integrity check: {qc}")
            record_count = chk_conn.execute("SELECT COUNT(*) FROM submission_records;").fetchone()[0]
            schema_version = chk_conn.execute("PRAGMA user_version;").fetchone()[0] or 1
        
        # Read plaintext snapshot bytes and compute SHA-256
        with open(temp_snapshot_path, "rb") as f:
            snapshot_bytes = f.read()
        source_db_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
        sqlite_db_b64 = base64.b64encode(snapshot_bytes).decode("ascii")

        backup_payload = {
            "backup_format_version": "2.0",
            "backup_id": backup_id,
            "created_at": timestamp_iso,
            "created_by": manager_identity,
            "record_count": record_count,
            "schema_version": schema_version,
            "source_db_sha256": source_db_sha256,
            "sqlite_db_b64": sqlite_db_b64,
        }

        json_bytes = json.dumps(backup_payload).encode("utf-8")
        ciphertext_bytes = fernet.encrypt(json_bytes)
        encrypted_payload_sha256 = hashlib.sha256(ciphertext_bytes).hexdigest()

        with open(backup_file_path, "wb") as f:
            f.write(ciphertext_bytes)

        return BackupResult(
            backup_id=backup_id,
            created_at=timestamp_iso,
            record_count=record_count,
            backup_file_path=backup_file_path,
            key_id=key_id,
            backup_format_version="2.0",
            source_db_sha256=source_db_sha256,
            encrypted_payload_sha256=encrypted_payload_sha256,
            schema_version=schema_version,
            mac_limitation_notice="Backup master key stored in local macOS Keychain. Restoration on another Mac requires key export."
        )
    finally:
        if os.path.exists(temp_snapshot_path):
            try:
                os.remove(temp_snapshot_path)
            except OSError:
                pass


def create_encrypted_backup(
    records: Optional[List[SubmissionRecord]] = None,
    manager_identity: str = "tarun@clifyx.com",
    backup_dir: Optional[str] = None,
    keychain_adapter: Optional[KeychainAdapter] = None,
    persistence_engine: Optional[Any] = None
) -> BackupResult:
    """
    Main entry point for creating encrypted backups.
    Creates a version 2.0 full SQLite database snapshot backup.
    If given in-memory records without an existing persistence engine, populates
    an isolated temporary SQLite database to produce a full-fidelity v2 snapshot.
    """
    if records is not None and persistence_engine is None:
        from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
        temp_dir = tempfile.mkdtemp()
        temp_db = os.path.join(temp_dir, "temp_backup_src.db")
        try:
            temp_engine = EncryptedPersistenceEngine(db_path=temp_db)
            for r in records:
                rec_dict = r.model_dump()
                latest_at, expires_at, is_expired = evaluate_record_retention(r, now_dt if 'now_dt' in locals() else get_current_new_york_datetime())
                rec_dict["latest_real_message_at"] = latest_at
                rec_dict["expires_at"] = expires_at
                rec_dict["retention_expired"] = is_expired
                tcs_elig = r.tcs_eligibility.value if hasattr(r.tcs_eligibility, "value") else str(r.tcs_eligibility)
                dom_stat = r.domain_status.value if hasattr(r.domain_status, "value") else str(r.domain_status)
                temp_engine.upsert_submission(
                    record_id=r.id,
                    graph_immutable_id=r.graph_immutable_id or f"imm-{r.id}",
                    conversation_id=r.conversation_id or f"conv-{r.id}",
                    job_id=r.job_id,
                    ep_reference=r.ep_reference,
                    candidate_name=r.candidate_name,
                    tcs_eligibility=tcs_elig,
                    domain_status=dom_stat,
                    received_at=r.received_at or r.created_at or datetime.now(timezone.utc).isoformat(),
                    created_at=r.created_at or r.received_at or datetime.now(timezone.utc).isoformat(),
                    payload_data=rec_dict
                )
            return create_encrypted_backup_v2(
                persistence_engine=temp_engine,
                manager_identity=manager_identity,
                backup_dir=backup_dir,
                keychain_adapter=keychain_adapter
            )
        finally:
            if os.path.exists(temp_db):
                try:
                    os.remove(temp_db)
                    os.rmdir(temp_dir)
                except OSError:
                    pass
    
    return create_encrypted_backup_v2(
        persistence_engine=persistence_engine,
        manager_identity=manager_identity,
        backup_dir=backup_dir,
        keychain_adapter=keychain_adapter
    )


def restore_backup_to_quarantine(
    backup_file_path: str,
    manager_identity: str = "tarun@clifyx.com",
    keychain_adapter: Optional[KeychainAdapter] = None,
    current_time: Optional[datetime] = None,
    quarantine_dir: Optional[str] = None
) -> Tuple[RestoreResult, List[SubmissionRecord]]:
    """
    Restore encrypted backup into Quarantine first.
    Supports both:
      - Format 2.0: Full SQLite database restoration into quarantine SQLite DB.
      - Format 1.0: Legacy projection-only record restoration.
    """
    global _quarantine_store
    if not os.path.exists(backup_file_path):
        raise FileNotFoundError(f"Backup file not found at {backup_file_path}")
    
    fernet, _ = get_or_create_backup_fernet_key(keychain_adapter)
    
    with open(backup_file_path, "rb") as f:
        ciphertext_bytes = f.read()
    
    try:
        json_bytes = fernet.decrypt(ciphertext_bytes)
        payload = json.loads(json_bytes.decode('utf-8'))
    except Exception as e:
        raise ValueError(f"Failed to decrypt backup. Invalid key or corrupted file: {str(e)}") from e
    
    format_version = str(payload.get("backup_format_version", "1.0"))
    now = current_time or get_current_new_york_datetime()
    restore_id = f"restore-{uuid.uuid4().hex[:8]}"

    if format_version.startswith("2"):
        # Format 2.0: Full SQLite database restoration
        sqlite_db_b64 = payload.get("sqlite_db_b64")
        if not sqlite_db_b64:
            raise ValueError("Backup payload v2.0 missing sqlite_db_b64")
        
        db_bytes = base64.b64decode(sqlite_db_b64)
        computed_sha256 = hashlib.sha256(db_bytes).hexdigest()
        expected_sha256 = payload.get("source_db_sha256")
        if expected_sha256 and computed_sha256 != expected_sha256:
            raise ValueError(f"Backup integrity failure: computed SHA-256 {computed_sha256} != expected {expected_sha256}")
        
        if not quarantine_dir:
            quarantine_dir = (
                os.path.join(tempfile.gettempdir(), "recruitment_agent_test", "quarantine")
                if _is_test_env else os.path.expanduser("~/.recruitment_agent/quarantine")
            )
        os.makedirs(quarantine_dir, exist_ok=True)
        
        quarantine_db_path = os.path.join(quarantine_dir, f"quarantine_{payload.get('backup_id', restore_id)}.db")
        with open(quarantine_db_path, "wb") as f:
            f.write(db_bytes)
        
        # Verify quarantine database with PRAGMA quick_check
        with sqlite3.connect(quarantine_db_path) as conn:
            qc = conn.execute("PRAGMA quick_check;").fetchone()[0]
            if qc != "ok":
                raise RuntimeError(f"Quarantined database failed quick_check: {qc}")

        from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
        quarantine_engine = EncryptedPersistenceEngine(db_path=quarantine_db_path)
        headers = quarantine_engine.list_records()
        quarantined_records: List[SubmissionRecord] = []
        for h in headers:
            rec = quarantine_engine.get_record_by_id(h.id)
            if rec:
                quarantined_records.append(rec)

        # Scan quarantined records for expiry
        expired_count = 0
        for record in quarantined_records:
            latest_at, expires_at, is_expired = evaluate_record_retention(record, now)
            record.expires_at = expires_at
            record.latest_real_message_at = latest_at
            record.retention_expired = is_expired
            if is_expired and not record.is_operational_record_only:
                expired_count += 1

        _quarantine_store = quarantined_records
        requires_action = (expired_count > 0)
        status = "quarantined_requires_retention_action" if requires_action else "quarantined_ready_for_promotion"
        message = (
            f"Full-fidelity v2.0 backup restored into quarantine database ({len(quarantined_records)} records). "
            f"{expired_count} expired records require manager retention review/deletion before active promotion."
        ) if requires_action else (
            f"Full-fidelity v2.0 backup restored into quarantine database ({len(quarantined_records)} records). Zero expired records found. Ready for promotion."
        )

        result = RestoreResult(
            restore_id=restore_id,
            quarantined_record_count=len(quarantined_records),
            expired_record_count=expired_count,
            requires_retention_action=requires_action,
            status=status,
            message=message,
            backup_format_version="2.0",
            fidelity_level="full_database_fidelity",
            source_db_sha256=computed_sha256
        )
        return result, quarantined_records

    else:
        # Format 1.0: Legacy projection-only format
        raw_records = payload.get("records", [])
        quarantined_records = [SubmissionRecord(**r) for r in raw_records]

        expired_count = 0
        for record in quarantined_records:
            latest_at, expires_at, is_expired = evaluate_record_retention(record, now)
            record.expires_at = expires_at
            record.latest_real_message_at = latest_at
            record.retention_expired = is_expired
            if is_expired and not record.is_operational_record_only:
                expired_count += 1

        _quarantine_store = quarantined_records
        requires_action = (expired_count > 0)
        status = "quarantined_requires_retention_action" if requires_action else "quarantined_ready_for_promotion"
        message = (
            f"Legacy v1.0 backup restored into quarantine (projection-only / incomplete fidelity) ({len(quarantined_records)} records). "
            f"{expired_count} expired records require manager retention review/deletion before active promotion."
        ) if requires_action else (
            f"Legacy v1.0 backup restored into quarantine (projection-only / incomplete fidelity) ({len(quarantined_records)} records). Zero expired records found."
        )

        result = RestoreResult(
            restore_id=restore_id,
            quarantined_record_count=len(quarantined_records),
            expired_record_count=expired_count,
            requires_retention_action=requires_action,
            status=status,
            message=message,
            backup_format_version="1.0",
            fidelity_level="projection-only / incomplete fidelity",
            source_db_sha256=None
        )
        return result, quarantined_records


def get_quarantine_store() -> List[SubmissionRecord]:
    """Retrieve current quarantined records."""
    return list(_quarantine_store)


def promote_quarantine_to_active(records_list: List[SubmissionRecord]) -> List[SubmissionRecord]:
    """
    Promote non-expired or pruned quarantined records to active storage.
    Fails closed if any unpruned expired records remain in quarantine.
    """
    global _quarantine_store
    now = get_current_new_york_datetime()
    
    for record in _quarantine_store:
        _, _, is_expired = evaluate_record_retention(record, now)
        if is_expired and not record.is_operational_record_only:
            raise ValueError(f"Cannot promote quarantine: record {record.id} is expired and has not been pruned.")
    
    promoted = list(_quarantine_store)
    _quarantine_store = []
    return promoted
