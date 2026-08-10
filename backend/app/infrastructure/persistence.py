"""
Encrypted SQLite persistence engine for operational records and audit history.
Uses payload encryption backed by master key protection.
"""

import os
import sys
import json
import re
import sqlite3
import base64
import hashlib
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone
from cryptography.fernet import Fernet, InvalidToken
from backend.app.domain.models import (
    SubmissionRecordHeader, ImportReport, DomainStatus,
    SubmissionRecord, TimelineEntry, DashboardSummary,
    DraftOperationRecord, DraftOperationState
)
from backend.app.infrastructure.keychain import KeychainAdapter
from backend.app.domain.subject_parser import parse_subject_metadata

import logging
logger = logging.getLogger("persistence")

# Simple envelope encryption using SHA256 key stream / XOR for local encrypted SQLite payload
class SimplePayloadEncryptor:
    def __init__(self, key_bytes: bytes):
        self.key_bytes = key_bytes

    def encrypt(self, data: str) -> str:
        data_bytes = data.encode('utf-8')
        cipher = bytearray()
        for i, byte in enumerate(data_bytes):
            key_byte = self.key_bytes[i % len(self.key_bytes)]
            cipher.append(byte ^ key_byte)
        return base64.b64encode(cipher).decode('utf-8')

    def decrypt(self, ciphertext: str) -> str:
        cipher = base64.b64decode(ciphertext.encode('utf-8'))
        plain = bytearray()
        for i, byte in enumerate(cipher):
            key_byte = self.key_bytes[i % len(self.key_bytes)]
            plain.append(byte ^ key_byte)
        return plain.decode('utf-8')



def _coerce_notes(val: Any) -> str:
    """Coerce manager_notes / system_notes to str.

    The authoritative payload may store notes as a list (e.g. ['']) due to
    historical serialization.  This read-time coercion never writes back.
    """
    if isinstance(val, list):
        return "\n".join(str(v) for v in val if v)
    if val is None:
        return ""
    return str(val)


def _display_metadata_with_subject_fallback(
    payload: Dict[str, Any], thread_messages: List[Dict[str, Any]]
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Fill missing display metadata from the original subject only.

    This never changes record association: immutable message and conversation
    identities remain authoritative, while Job ID and EP remain metadata only.
    """
    meta = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
    skill = payload.get("skill") or meta.get("skill")
    customer = payload.get("customer") or meta.get("customer")
    location = payload.get("location") or meta.get("location")
    if skill and customer and location:
        return skill, customer, location

    subject = next(
        (m.get("subject") for m in thread_messages if isinstance(m, dict) and m.get("subject")),
        "",
    )
    parsed = parse_subject_metadata(subject)
    return skill or parsed.skill, customer or parsed.customer, location or parsed.location


class EncryptedPersistenceEngine:
    def __init__(self, db_path: Optional[str] = None, master_key: Optional[str] = None):
        is_test = (
            os.environ.get("ENVIRONMENT", "").lower() == "test"
            or "pytest" in sys.modules
            or "PYTEST_CURRENT_TEST" in os.environ
        )
        authoritative_db = os.path.abspath(os.path.expanduser("~/.recruitment_agent/records.db"))

        if not db_path:
            if is_test:
                import tempfile
                import uuid
                db_path = os.path.join(tempfile.gettempdir(), f"test_records_{uuid.uuid4().hex}.db")
            else:
                base_dir = os.path.expanduser("~/.recruitment_agent")
                os.makedirs(base_dir, exist_ok=True)
                db_path = os.path.join(base_dir, "records.db")

        self.db_path = db_path
        
        canonical_db_path = os.path.abspath(self.db_path) if self.db_path else None
        if is_test and canonical_db_path == authoritative_db:
            raise RuntimeError("FATAL: Test mode attempted to connect to the authoritative database.")

        master_key_str = master_key or "default_local_key_clifyx_follow_up_agent_2026"
        key_bytes = hashlib.sha256(master_key_str.encode('utf-8')).digest()
        self.encryptor = SimplePayloadEncryptor(key_bytes)
        # Draft approvals contain mailbox recipients and message bodies.  New
        # draft-operation payloads use authenticated encryption.  Existing
        # legacy rows remain readable only so they can be safely superseded.
        if master_key is not None or is_test:
            fernet_key = base64.urlsafe_b64encode(hashlib.sha256((master_key_str + ":draft-ops-v2").encode()).digest())
        else:
            adapter = KeychainAdapter(use_memory_fallback=False)
            stored = adapter.get_secret("BackupKey", "MasterBackupKey")
            if not stored:
                raise RuntimeError("Keychain-protected encryption key is unavailable; draft persistence failed closed")
            fernet_key = stored.encode("utf-8")
        self._draft_fernet = Fernet(fernet_key)
        self._init_tables()

    def _encrypt_draft_payload(self, payload: Dict[str, Any]) -> str:
        token = self._draft_fernet.encrypt(json.dumps(payload, sort_keys=True).encode("utf-8")).decode("ascii")
        return "fernet:v2:" + token

    def _decrypt_draft_payload(self, ciphertext: str) -> Dict[str, Any]:
        if ciphertext.startswith("fernet:v2:"):
            try:
                raw = self._draft_fernet.decrypt(ciphertext[len("fernet:v2:"):].encode("ascii"))
            except InvalidToken as exc:
                raise RuntimeError("Draft operation ciphertext authentication failed") from exc
            return json.loads(raw.decode("utf-8"))
        return json.loads(self.encryptor.decrypt(ciphertext))

    def _get_connection(self) -> sqlite3.Connection:
        is_test = (
            os.environ.get("ENVIRONMENT", "").lower() == "test"
            or "pytest" in sys.modules
            or "PYTEST_CURRENT_TEST" in os.environ
        )
        authoritative_db = os.path.abspath(os.path.expanduser("~/.recruitment_agent/records.db"))
        canonical_db_path = os.path.abspath(self.db_path) if self.db_path else None
        if is_test and canonical_db_path == authoritative_db:
            raise RuntimeError("FATAL: Test mode attempted to connect to the authoritative database.")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_latest_import_report(self) -> Optional[ImportReport]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM import_events ORDER BY started_at DESC LIMIT 1").fetchone()
            if not row:
                return None
            return ImportReport(**json.loads(row["report_json"]))

    def store_draft_operation(self, op: DraftOperationRecord) -> None:
        payload_cipher = self._encrypt_draft_payload(op.payload_data)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO draft_operations (
                    idempotency_key, record_id, approval_hash, record_version, state, created_at, updated_at, payload_ciphertext
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (op.idempotency_key, op.record_id, op.approval_hash, op.record_version, op.state.value, op.created_at, op.updated_at, payload_cipher)
            )
            conn.commit()

    def get_draft_operation(self, idempotency_key: str) -> Optional[DraftOperationRecord]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM draft_operations WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
            if not row:
                return None
            return DraftOperationRecord(
                idempotency_key=row["idempotency_key"],
                record_id=row["record_id"],
                approval_hash=row["approval_hash"],
                record_version=row["record_version"],
                state=DraftOperationState(row["state"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                payload_data=self._decrypt_draft_payload(row["payload_ciphertext"])
            )

    def get_latest_draft_operation_for_record(self, record_id: str) -> Optional[DraftOperationRecord]:
        """Return the newest durable draft operation so UI recovery survives restarts."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM draft_operations WHERE record_id = ? ORDER BY created_at DESC LIMIT 1",
                (record_id,),
            ).fetchone()
            if not row:
                return None
            return DraftOperationRecord(
                idempotency_key=row["idempotency_key"], record_id=row["record_id"],
                approval_hash=row["approval_hash"], record_version=row["record_version"],
                state=DraftOperationState(row["state"]), created_at=row["created_at"],
                updated_at=row["updated_at"],
                payload_data=self._decrypt_draft_payload(row["payload_ciphertext"]),
            )

    def update_draft_operation_state(self, idempotency_key: str, state: DraftOperationState, updated_payload_data: Optional[Dict[str, Any]] = None) -> None:
        updated_at = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            if updated_payload_data is not None:
                payload_cipher = self._encrypt_draft_payload(updated_payload_data)
                conn.execute(
                    "UPDATE draft_operations SET state = ?, updated_at = ?, payload_ciphertext = ? WHERE idempotency_key = ?",
                    (state.value, updated_at, payload_cipher, idempotency_key)
                )
            else:
                conn.execute(
                    "UPDATE draft_operations SET state = ?, updated_at = ? WHERE idempotency_key = ?",
                    (state.value, updated_at, idempotency_key)
                )
            conn.commit()

    def compare_and_set_draft_operation(
        self,
        idempotency_key: str,
        expected_states: List[DraftOperationState],
        new_state: DraftOperationState,
        updated_payload_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Atomically transition a draft operation; false means another request won."""
        updated_at = datetime.now(timezone.utc).isoformat()
        placeholders = ",".join("?" for _ in expected_states)
        params: List[Any] = [new_state.value, updated_at]
        set_sql = "state = ?, updated_at = ?"
        if updated_payload_data is not None:
            set_sql += ", payload_ciphertext = ?"
            params.append(self._encrypt_draft_payload(updated_payload_data))
        params.extend([idempotency_key, *[s.value for s in expected_states]])
        with self._get_connection() as conn:
            cursor = conn.execute(
                f"UPDATE draft_operations SET {set_sql} WHERE idempotency_key = ? AND state IN ({placeholders})",
                params,
            )
            conn.commit()
            return cursor.rowcount == 1

    def supersede_active_draft_operations(self, record_id: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE draft_operations SET state = ?, updated_at = ? WHERE record_id = ? AND state NOT IN (?, ?)",
                (DraftOperationState.SUPERSEDED.value, datetime.now(timezone.utc).isoformat(), record_id,
                 DraftOperationState.CREATED.value, DraftOperationState.SUPERSEDED.value),
            )
            conn.commit()

    def _init_tables(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS submission_records (
                    id TEXT PRIMARY KEY,
                    graph_immutable_id TEXT UNIQUE NOT NULL,
                    conversation_id TEXT NOT NULL,
                    job_id TEXT,
                    ep_reference TEXT,
                    candidate_name TEXT,
                    tcs_eligibility TEXT NOT NULL,
                    domain_status TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_ciphertext TEXT NOT NULL,
                    record_version INTEGER NOT NULL DEFAULT 1
                );
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_records_conversation ON submission_records(conversation_id);
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_records_immutable ON submission_records(graph_immutable_id);
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS import_events (
                    import_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    messages_scanned INTEGER NOT NULL,
                    messages_eligible INTEGER NOT NULL,
                    messages_imported INTEGER NOT NULL,
                    duplicates_skipped INTEGER NOT NULL,
                    excluded_count INTEGER NOT NULL,
                    error_count INTEGER NOT NULL,
                    is_preview INTEGER NOT NULL,
                    report_json TEXT NOT NULL
                );
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS draft_operations (
                    idempotency_key TEXT PRIMARY KEY,
                    record_id TEXT NOT NULL,
                    approval_hash TEXT NOT NULL,
                    record_version INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_ciphertext TEXT NOT NULL
                );
            """)
            conn.commit()

    def exists_by_immutable_id(self, graph_immutable_id: str) -> bool:
        """Check if record with graph_immutable_id already exists."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM submission_records WHERE graph_immutable_id = ?",
                (graph_immutable_id,)
            )
            return cursor.fetchone() is not None

    def upsert_submission(
        self,
        record_id: str,
        graph_immutable_id: str,
        conversation_id: str,
        job_id: Optional[str],
        ep_reference: Optional[str],
        candidate_name: Optional[str],
        tcs_eligibility: str,
        domain_status: str,
        received_at: str,
        created_at: str,
        payload_data: Dict[str, Any]
    ) -> Tuple[bool, bool]:
        """
        Idempotently insert or update a submission record.
        Returns: (is_new, is_updated)
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT domain_status, payload_ciphertext FROM submission_records WHERE graph_immutable_id = ?",
                (graph_immutable_id,)
            )
            row = cursor.fetchone()

            if row:
                existing_status = row["domain_status"]
                existing_payload_json = self.encryptor.decrypt(row["payload_ciphertext"])
                existing_payload = json.loads(existing_payload_json)

                # A mailbox refresh updates source content, not workflow state.
                # Classification is a separate deterministic step and manager
                # decisions must never be reset to NewSubmission by re-import.
                domain_status = existing_status

                # Preserve manager fields and retention history from existing payload
                preserve_keys = [
                    "manager_notes", "system_notes", "close_reason", "close_note",
                    "closed_at", "interview_state", "interview_updated_at",
                    "feedback_due_at", "latest_update", "latest_sender",
                    "latest_timestamp", "timeline", "is_operational_record_only",
                    "retention_expired", "expires_at", "latest_real_message_at",
                    "draft_approval", "retention_history", "manager_outcome_category",
                    "linked_conversations", "interview_suggestions"
                ]
                for k in preserve_keys:
                    if k in existing_payload:
                        payload_data[k] = existing_payload[k]

                # Merge thread_messages idempotently
                existing_messages = existing_payload.get("thread_messages", [])
                existing_msg_map = {m.get("id"): m for m in existing_messages if m.get("id")}

                new_messages = payload_data.get("thread_messages", [])
                merged_messages = list(existing_messages)
                
                for msg in new_messages:
                    if msg.get("id") not in existing_msg_map:
                        merged_messages.append(msg)
                        existing_msg_map[msg.get("id")] = msg
                
                # Merge attachments idempotently
                existing_attachments = existing_payload.get("attachment_hashes", [])
                existing_att_set = set(existing_attachments)
                new_attachments = payload_data.get("attachment_hashes", [])
                for att in new_attachments:
                    if att not in existing_att_set:
                        existing_attachments.append(att)
                        existing_att_set.add(att)
                payload_data["attachment_hashes"] = existing_attachments
                
                payload_data["thread_messages"] = merged_messages
                payload_data["thread_message_count"] = len(merged_messages)

                ciphertext = self.encryptor.encrypt(json.dumps(payload_data))

                conn.execute("""
                    UPDATE submission_records
                    SET conversation_id = ?, job_id = ?, ep_reference = ?,
                        candidate_name = ?, tcs_eligibility = ?, domain_status = ?,
                        received_at = ?, payload_ciphertext = ?
                    WHERE graph_immutable_id = ?
                """, (
                    conversation_id, job_id, ep_reference, candidate_name,
                    tcs_eligibility, domain_status, received_at, ciphertext,
                    graph_immutable_id
                ))
                conn.commit()
                return False, True

            # Insert new record
            ciphertext = self.encryptor.encrypt(json.dumps(payload_data))

            conn.execute("""
                INSERT INTO submission_records (
                    id, graph_immutable_id, conversation_id, job_id, ep_reference,
                    candidate_name, tcs_eligibility, domain_status, received_at, created_at, payload_ciphertext
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record_id, graph_immutable_id, conversation_id, job_id, ep_reference,
                candidate_name, tcs_eligibility, domain_status, received_at, created_at, ciphertext
            ))
            conn.commit()

        return True, False

    def save_record_payload(self, record_id: str, payload: dict, domain_status: str) -> None:
        """Insert or update record payload and domain status in one explicit transaction."""
        ciphertext = self.encryptor.encrypt(json.dumps(payload))
        meta = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
        graph_id = payload.get("graph_immutable_id") or f"graph-{record_id}"
        conv_id = payload.get("conversation_id") or f"conv-{record_id}"
        job_id = payload.get("job_id") or meta.get("job_id")
        ep_ref = payload.get("ep_reference") or meta.get("ep_reference")
        cand_name = payload.get("candidate_name") or meta.get("candidate_name")
        tcs_elig = payload.get("tcs_eligibility") or meta.get("tcs_eligibility", "eligible")
        recv_at = payload.get("received_at") or meta.get("received_at") or datetime.now(timezone.utc).isoformat()
        created_at = payload.get("created_at") or meta.get("created_at") or datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO submission_records (
                    id, graph_immutable_id, conversation_id, job_id, ep_reference,
                    candidate_name, tcs_eligibility, domain_status, received_at, created_at, payload_ciphertext, record_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(id) DO UPDATE SET
                    graph_immutable_id = excluded.graph_immutable_id,
                    conversation_id = excluded.conversation_id,
                    job_id = excluded.job_id,
                    ep_reference = excluded.ep_reference,
                    candidate_name = excluded.candidate_name,
                    tcs_eligibility = excluded.tcs_eligibility,
                    domain_status = excluded.domain_status,
                    received_at = excluded.received_at,
                    payload_ciphertext = excluded.payload_ciphertext,
                    record_version = submission_records.record_version + 1
                """,
                (record_id, graph_id, conv_id, job_id, ep_ref, cand_name, tcs_elig, domain_status, recv_at, created_at, ciphertext)
            )
            conn.commit()

    def update_record_optimistically(self, record_id: str, payload: dict, domain_status: str, expected_version: int) -> int:
        """Atomically update a record ensuring exact version match."""
        ciphertext = self.encryptor.encrypt(json.dumps(payload))
        meta = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
        graph_id = payload.get("graph_immutable_id") or f"graph-{record_id}"
        conv_id = payload.get("conversation_id") or f"conv-{record_id}"
        job_id = payload.get("job_id") or meta.get("job_id")
        ep_ref = payload.get("ep_reference") or meta.get("ep_reference")
        cand_name = payload.get("candidate_name") or meta.get("candidate_name")
        tcs_elig = payload.get("tcs_eligibility") or meta.get("tcs_eligibility", "eligible")
        recv_at = payload.get("received_at") or meta.get("received_at") or datetime.now(timezone.utc).isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE submission_records SET
                    graph_immutable_id = ?, conversation_id = ?, job_id = ?, ep_reference = ?,
                    candidate_name = ?, tcs_eligibility = ?, domain_status = ?, received_at = ?,
                    payload_ciphertext = ?, record_version = record_version + 1
                WHERE id = ? AND record_version = ?
                """,
                (graph_id, conv_id, job_id, ep_ref, cand_name, tcs_elig, domain_status, recv_at, ciphertext, record_id, expected_version)
            )
            if cursor.rowcount == 0:
                raise ValueError("Record version token is stale or mismatched, or record does not exist.")
            conn.commit()
            return expected_version + 1

    def save_import_event(self, report: ImportReport) -> None:
        """Save import run event report."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO import_events (
                    import_id, started_at, completed_at, messages_scanned, messages_eligible,
                    messages_imported, duplicates_skipped, excluded_count, error_count, is_preview, report_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                report.import_id,
                report.started_at,
                report.completed_at or datetime.utcnow().isoformat(),
                report.messages_scanned,
                report.messages_eligible,
                report.messages_imported,
                report.duplicates_skipped,
                report.excluded_count,
                report.error_count,
                1 if report.is_preview else 0,
                report.model_dump_json()
            ))
            conn.commit()

    def list_records(self) -> List[SubmissionRecordHeader]:
        """List operational record headers, enriched from payload."""
        records = []
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, graph_immutable_id, conversation_id, job_id, ep_reference,
                       candidate_name, tcs_eligibility, domain_status, received_at, created_at,
                       payload_ciphertext, record_version
                FROM submission_records
                ORDER BY received_at DESC
            """)
            for row in cursor.fetchall():
                # Extract enriched fields from payload
                latest_logical_timestamp = None
                latest_logical_author = None
                logical_message_count = 0
                skill = None
                customer = None
                location = None
                thread_message_count = 0
                try:
                    payload = self._decrypt_payload(row["payload_ciphertext"])
                    meta = payload.get("metadata", {})
                    thread_messages = payload.get("thread_messages", [])
                    skill, customer, location = _display_metadata_with_subject_fallback(
                        payload, thread_messages
                    )
                    thread_message_count = len(thread_messages)
                    
                    logical_msgs = self._build_timeline_from_thread_messages(row["id"], thread_messages)
                    logical_message_count = len(logical_msgs)
                    if logical_msgs:
                        latest_logical_timestamp = logical_msgs[-1].timestamp
                        latest_logical_author = logical_msgs[-1].sender
                except Exception as exc:
                    # An encrypted record that cannot be read must never be
                    # rendered as a plausible empty record. Stop the request so
                    # the manager sees an operational fault instead of acting on
                    # incomplete or misleading data.
                    raise RuntimeError(
                        f"Unable to decrypt or parse record {row['id']}; failing closed."
                    ) from exc

                source_content_warning = self._detect_source_content_conflict(
                    row["job_id"] or meta.get("job_id"),
                    thread_messages,
                    row["graph_immutable_id"]
                )

                records.append(SubmissionRecordHeader(
                    id=row["id"],
                    graph_immutable_id=row["graph_immutable_id"],
                    conversation_id=row["conversation_id"],
                    job_id=row["job_id"] or payload.get("job_id") or meta.get("job_id"),
                    ep_reference=row["ep_reference"] or payload.get("ep_reference") or meta.get("ep_reference"),
                    candidate_name=row["candidate_name"] or payload.get("candidate_name") or meta.get("candidate_name"),
                    tcs_eligibility=row["tcs_eligibility"],
                    domain_status=DomainStatus(row["domain_status"]),
                    received_at=row["received_at"],
                    created_at=row["created_at"],
                    record_version=row["record_version"],
                    latest_logical_timestamp=latest_logical_timestamp,
                    latest_logical_author=latest_logical_author,
                    logical_message_count=logical_message_count,
                    skill=skill,
                    customer=customer,
                    location=location,
                    thread_message_count=thread_message_count,
                    source_content_warning=source_content_warning,
                    feedback_due_at=payload.get("feedback_due_at"),
                    interview_state=payload.get("interview_state"),
                    interview_updated_at=payload.get("interview_updated_at"),
                    interview_datetime=payload.get("interview_datetime"),
                ))
            
            # Sort by latest logical timestamp descending, fallback to received_at
            records.sort(key=lambda r: r.latest_logical_timestamp or r.received_at, reverse=True)
            return records
        return records

    def _decrypt_payload(self, ciphertext: str) -> Dict[str, Any]:
        """Decrypt payload ciphertext and parse JSON. Raises on failure."""
        plain = self.encryptor.decrypt(ciphertext)
        return json.loads(plain)

    @staticmethod
    def _detect_source_content_conflict(
        subj_job_id: Optional[str],
        thread_messages: List[Dict[str, Any]],
        graph_immutable_id: Optional[str]
    ) -> Optional[str]:
        """Detect read-time subject-versus-body Job ID conflict without modifying record state."""
        if not subj_job_id or not thread_messages:
            return None
        orig_msg = next((m for m in thread_messages if m.get("id") == graph_immutable_id), thread_messages[0])
        body = orig_msg.get("body", {}).get("content", "") or orig_msg.get("bodyPreview", "")
        if not body:
            return None
            
        body_matches = re.findall(r'(?i)(?:job\s*(?:id|#|number)?[:\s]*|req\s*(?:id|#|number)?[:\s]*)\s*([0-9]{6})\b', body)
        if not body_matches:
            six_digits = re.findall(r'\b([0-9]{6})\b', body[:500])
            body_matches = [d for d in six_digits if d != subj_job_id]
            
        conflicts = [m for m in set(body_matches) if m != subj_job_id and m not in subj_job_id and subj_job_id not in m]
        if conflicts:
            conflicting_id = conflicts[0]
            return f"Email subject specifies Job {subj_job_id}, but message body references Job {conflicting_id}. Identity and classification remain anchored to immutable source message."
        return None

    def _build_timeline_from_thread_messages(
        self,
        record_id: str,
        thread_messages: List[Dict[str, Any]],
        role: str = "original_submission",
        conversation_id: Optional[str] = None
    ) -> List[TimelineEntry]:
        """Convert Graph thread messages into sorted TimelineEntry objects without duplicates."""
        entries: List[TimelineEntry] = []
        seen_imids = set()

        def _get_msg_ts(m):
            return m.get("sentDateTime") or m.get("receivedDateTime") or "1970-01-01T00:00:00Z"

        sorted_messages = sorted(thread_messages, key=_get_msg_ts)

        prefix = "te" if role == "original_submission" else "te-lc"
        for idx, msg in enumerate(sorted_messages):
            imid = (msg.get("internetMessageId") or "").strip()
            is_valid_imid = bool(imid and imid.startswith("<") and imid.endswith(">"))
            if is_valid_imid:
                if imid in seen_imids:
                    # Skip duplicate cross-folder copy of the same logical email
                    continue
                seen_imids.add(imid)

            sender_info = msg.get("from", {}).get("emailAddress", {})
            sender = sender_info.get("address", "unknown")
            timestamp = _get_msg_ts(msg)
            unique_body = msg.get("uniqueBody", {}).get("content", "").strip()
            if unique_body:
                body_preview = unique_body
            else:
                body_preview = msg.get("bodyPreview", "").strip()
                if len(body_preview) > 250:
                    body_preview = body_preview[:250] + "..."

            to_recips = [
                r.get("emailAddress", {}).get("address", "")
                for r in msg.get("toRecipients", [])
            ]
            cc_recips = [
                r.get("emailAddress", {}).get("address", "")
                for r in msg.get("ccRecipients", [])
            ]

            entries.append(TimelineEntry(
                entry_id=f"{prefix}-{record_id[:8]}-{idx:03d}",
                record_id=record_id,
                sender=sender,
                timestamp=timestamp,
                body_preview=body_preview,
                classification=None,
                is_system_note=False,
                to_recipients=to_recips,
                cc_recipients=cc_recips,
                reply_to=None,
                graph_immutable_id=msg.get("id"),  # kept internal, hidden from UI
                conversation_id=conversation_id,
                role=role
            ))

        return entries

    def get_record_by_id(self, record_id: str) -> Optional[SubmissionRecord]:
        """Fetch and decrypt a single record from the authoritative database."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM submission_records WHERE id = ?",
                (record_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            try:
                payload = self._decrypt_payload(row["payload_ciphertext"])
            except Exception:
                logger.error("Decryption failed for record (fail-closed)")
                raise RuntimeError("Payload decryption failed — fail closed")

            thread_messages = payload.get("thread_messages", [])
            logical_message_timeline = self._build_timeline_from_thread_messages(
                row["id"], thread_messages, role="original_submission", conversation_id=row["conversation_id"]
            )
            
            logical_message_count = len(logical_message_timeline)
            latest_logical_timestamp = logical_message_timeline[-1].timestamp if logical_message_timeline else None
            latest_logical_author = logical_message_timeline[-1].sender if logical_message_timeline else None
            
            timeline = list(logical_message_timeline)

            # Extract linked conversations & suggestions
            from backend.app.domain.models import LinkedConversation, LinkedInterviewSuggestion
            linked_convs_raw = payload.get("linked_conversations", [])
            linked_conversations: List[LinkedConversation] = []
            for lc in linked_convs_raw:
                if isinstance(lc, dict):
                    linked_conversations.append(LinkedConversation(**lc))
                elif isinstance(lc, LinkedConversation):
                    linked_conversations.append(lc)

            suggestions_raw = payload.get("interview_suggestions", [])
            interview_suggestions: List[LinkedInterviewSuggestion] = []
            for s in suggestions_raw:
                if isinstance(s, dict):
                    interview_suggestions.append(LinkedInterviewSuggestion(**s))
                elif isinstance(s, LinkedInterviewSuggestion):
                    interview_suggestions.append(s)

            # Include messages from confirmed linked conversations in timeline
            for lc in linked_conversations:
                if lc.role == "interview_coordination" and lc.thread_messages:
                    lc_timeline = self._build_timeline_from_thread_messages(
                        row["id"], lc.thread_messages, role="interview_coordination", conversation_id=lc.conversation_id
                    )
                    timeline.extend(lc_timeline)

            # Include audit events stored in payload["timeline"]
            audit_events = payload.get("timeline", [])
            for item in audit_events:
                if isinstance(item, dict) and item.get("is_system_note"):
                    timeline.append(TimelineEntry(
                        entry_id=item.get("entry_id", "audit-sys"),
                        record_id=row["id"],
                        sender=item.get("sender", "system"),
                        timestamp=item.get("timestamp", ""),
                        body_preview=item.get("body_preview", ""),
                        classification=None,
                        is_system_note=True,
                        to_recipients=[],
                        cc_recipients=[],
                        reply_to=None,
                        event_type=item.get("event_type")
                    ))
            timeline.sort(key=lambda e: e.timestamp)

            # Compute attachment count excluding inline/signature
            INLINE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/gif", "image/bmp", "image/svg+xml"}
            INLINE_NAME_PATTERNS = ("image", "logo", "signature", "icon", "banner")
            attachment_count = 0
            for msg in thread_messages:
                for att in (msg.get("attachments_metadata") or []):
                    ct = (att.get("contentType") or att.get("@odata.mediaContentType") or "").lower()
                    name = (att.get("name") or "").lower()
                    is_inline = ct in INLINE_CONTENT_TYPES and any(
                        p in name for p in INLINE_NAME_PATTERNS
                    )
                    if not is_inline:
                        attachment_count += 1

            # Extract metadata fields from payload
            metadata = payload.get("metadata", {})
            latest_msg = thread_messages[-1] if thread_messages else None
            latest_sender = None
            latest_timestamp = None
            latest_update = None
            if latest_msg:
                latest_sender_info = latest_msg.get("from", {}).get("emailAddress", {})
                latest_sender = latest_sender_info.get("address")
                latest_timestamp = latest_msg.get("sentDateTime") or latest_msg.get("receivedDateTime")
                preview = latest_msg.get("bodyPreview", "")
                latest_update = preview[:100] + "..." if len(preview) > 100 else preview

            payload["record_version"] = row["record_version"]
            
            # --- Structured Evidence ---
            structured_evidence = None
            try:
                from backend.app.domain.consolidated_classifier import classify_record
                from backend.app.domain.message_facts import analyze_conversation
                from backend.app.domain.models import StructuredEvidence
                
                facts = analyze_conversation(row["graph_immutable_id"], thread_messages)
                result = classify_record(
                    row["graph_immutable_id"], 
                    thread_messages, 
                    datetime.now(timezone.utc),
                    timeline=timeline,
                    linked_conversations=linked_conversations
                )
                
                timer_ts = facts.timer_anchor_message.timestamp.isoformat() if facts.timer_anchor_message else None
                latest_logical_ts = facts.messages[-1].timestamp.isoformat() if facts.messages else None
                
                cat = payload.get("manager_outcome_category") or result.category
                status_val = row["domain_status"]
                reason = "MANAGER_OUTCOME_DECISION" if payload.get("manager_outcome_category") else result.reason_code
                structured_evidence = StructuredEvidence(
                    category=cat,
                    workflow_status=status_val,
                    reason_code=reason,
                    timer_anchor_timestamp=timer_ts,
                    latest_logical_timestamp=latest_logical_ts,
                    logical_messages_evaluated=len(facts.messages)
                )
            except Exception as e:
                logger.error(f"Failed to compute structured evidence: {e}")
                
            display_skill, display_customer, display_location = _display_metadata_with_subject_fallback(
                payload, thread_messages
            )
            return SubmissionRecord(
                id=row["id"],
                graph_immutable_id=row["graph_immutable_id"],
                conversation_id=row["conversation_id"],
                job_id=row["job_id"] or metadata.get("job_id"),
                ep_reference=row["ep_reference"] or metadata.get("ep_reference"),
                candidate_name=row["candidate_name"] or metadata.get("candidate_name"),
                skill=display_skill,
                customer=display_customer,
                location=display_location,
                tcs_eligibility=row["tcs_eligibility"],
                domain_status=DomainStatus(row["domain_status"]),
                received_at=row["received_at"],
                created_at=row["created_at"],
                interview_state=payload.get("interview_state"),
                interview_datetime=payload.get("interview_datetime"),
                interview_updated_at=payload.get("interview_updated_at"),
                feedback_due_at=payload.get("feedback_due_at"),
                manager_notes=_coerce_notes(payload.get("manager_notes", "")),
                system_notes=_coerce_notes(payload.get("system_notes", "")),
                close_reason=payload.get("close_reason"),
                close_note=payload.get("close_note"),
                closed_at=payload.get("closed_at"),
                latest_update=latest_update,
                latest_sender=latest_sender,
                latest_logical_timestamp=latest_logical_timestamp,
                latest_logical_author=latest_logical_author,
                logical_message_count=logical_message_count,
                record_version=row["record_version"],
                timeline=timeline,
                linked_conversations=linked_conversations,
                interview_suggestions=interview_suggestions,
                structured_evidence=structured_evidence,
                is_operational_record_only=payload.get("is_operational_record_only", False),
                retention_expired=payload.get("retention_expired", False),
                expires_at=payload.get("expires_at"),
                latest_real_message_at=latest_timestamp,
                attachment_count=attachment_count,
                attachment_hashes=payload.get("attachment_hashes", []),
                storage_size_bytes=len(json.dumps(payload).encode("utf-8")),
                source_content_warning=self._detect_source_content_conflict(
                    row["job_id"] or metadata.get("job_id"),
                    thread_messages,
                    row["graph_immutable_id"]
                )
            )

    def get_record_payload_snapshot(self, record_id: str) -> Optional[tuple[dict, int, str]]:
        """Return decrypted payload, version and status for an internal reconciliation.

        The caller must use ``update_record_optimistically``; this method performs
        no mutation and deliberately exposes no data through the HTTP API.
        """
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT payload_ciphertext, record_version, domain_status "
                "FROM submission_records WHERE id = ?",
                (record_id,),
            ).fetchone()
        if not row:
            return None
        return (
            self._decrypt_payload(row["payload_ciphertext"]),
            int(row["record_version"]),
            row["domain_status"],
        )

    def get_dashboard_summary(self) -> DashboardSummary:
        """Compute dashboard summary from the authoritative encrypted database."""
        headers = self.list_records()
        status_counts = {
            "awaiting_response": 0,
            "pending_follow_up": 0,
            "interview_awaiting_confirmation": 0,
            "interview_request_scheduled": 0,
            "awaiting_feedback": 0,
            "feedback_due": 0,
            "manager_action_required": 0,
            "in_evaluation": 0,
            "needs_review": 0,
            "incomplete": 0,
            "closed": 0,
        }
        for h in headers:
            ds = h.domain_status
            if h.thread_message_count == 0:
                status_counts["incomplete"] += 1
            elif ds == DomainStatus.AWAITING_RESPONSE:
                status_counts["awaiting_response"] += 1
            elif ds == DomainStatus.PENDING_FOLLOW_UP:
                status_counts["pending_follow_up"] += 1
            elif ds == DomainStatus.INTERVIEW_REQUEST_SCHEDULED:
                status_counts["interview_request_scheduled"] += 1
            elif ds == DomainStatus.INTERVIEW_AWAITING_CONFIRMATION:
                status_counts["interview_awaiting_confirmation"] += 1
            elif ds == DomainStatus.AWAITING_FEEDBACK:
                status_counts["awaiting_feedback"] += 1
            elif ds == DomainStatus.FEEDBACK_DUE:
                status_counts["feedback_due"] += 1
            elif ds == DomainStatus.MANAGER_ACTION_REQUIRED:
                status_counts["manager_action_required"] += 1
            elif ds == DomainStatus.IN_EVALUATION:
                status_counts["in_evaluation"] += 1
            elif ds in (DomainStatus.NEEDS_REVIEW, DomainStatus.NEW_SUBMISSION):
                status_counts["needs_review"] += 1
            elif ds == DomainStatus.CLOSED:
                status_counts["closed"] += 1

        complete_count = len(headers) - status_counts["incomplete"]
        return DashboardSummary(
            awaiting_response=status_counts["awaiting_response"],
            pending_follow_up=status_counts["pending_follow_up"],
            interview_awaiting_confirmation=status_counts["interview_awaiting_confirmation"],
            interview_request_scheduled=status_counts["interview_request_scheduled"],
            awaiting_feedback=status_counts["awaiting_feedback"],
            feedback_due=status_counts["feedback_due"],
            manager_action_required=status_counts["manager_action_required"],
            in_evaluation=status_counts["in_evaluation"],
            needs_review=status_counts["needs_review"],
            incomplete=status_counts["incomplete"],
            complete_records=complete_count,
            closed=status_counts["closed"],
            total=len(headers),
            auth_status="authoritative_encrypted_database",
            records=headers
        )
