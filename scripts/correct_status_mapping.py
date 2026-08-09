import os
import sys
import sqlite3
import shutil
import hashlib
import json
import subprocess
from datetime import datetime
from collections import Counter

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.models import DomainStatus

def check_ollama_status():
    try:
        res = subprocess.run(["ollama", "ps"], capture_output=True, text=True)
        lines = [l.strip() for l in res.stdout.strip().split("\n") if l.strip()]
        return len(lines) > 1
    except Exception:
        return False

def get_file_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def run():
    print("--- Transactional Post-Apply Status Mapping Correction ---")
    
    if check_ollama_status():
        print("ABORT: Ollama model is currently loaded in memory.")
        sys.exit(1)
        
    os.environ["OLLAMA_ENABLED"] = "False"
    snapshot_time = datetime.fromisoformat("2026-08-04T01:01:23-04:00")
    
    persistence = EncryptedPersistenceEngine()
    db_path = persistence.db_path
    if not os.path.exists(db_path):
        print(f"ABORT: Authoritative database not found at {db_path}")
        sys.exit(1)
        
    # Create new pre-correction checkpoint
    backup_dir = os.path.expanduser("~/.recruitment_agent/backups")
    os.makedirs(backup_dir, exist_ok=True)
    checkpoint_filename = f"records_pre_status_correction_{snapshot_time.strftime('%Y%m%d_%H%M%S')}.db"
    checkpoint_path = os.path.join(backup_dir, checkpoint_filename)
    
    shutil.copy2(db_path, checkpoint_path)
    
    orig_hash = get_file_sha256(db_path)
    chk_hash = get_file_sha256(checkpoint_path)
    
    if orig_hash != chk_hash:
        print("ABORT: Pre-correction checkpoint hash mismatch!")
        sys.exit(1)
        
    print(f"Checkpoint created successfully: {checkpoint_path}")
    print(f"Checkpoint SHA256: {chk_hash[:16]}...")
    
    # Identify the 4 records requiring status correction
    # 3 NewSubmission -> AwaitingResponse
    # 1 AwaitingFeedback -> InterviewAwaitingConfirmation
    records_to_correct = []
    
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, graph_immutable_id, domain_status, payload_ciphertext FROM submission_records")
        rows = cursor.fetchall()
        
        for row in rows:
            try:
                payload = persistence._decrypt_payload(row["payload_ciphertext"])
            except Exception:
                continue
                
            st = payload.get("classification_status")
            ds = row["domain_status"]
            
            if st == "Awaiting Response" and ds == "NewSubmission":
                records_to_correct.append((row["id"], payload, DomainStatus.AWAITING_RESPONSE))
            elif st == "Interview Awaiting Confirmation" and ds == "AwaitingFeedback":
                records_to_correct.append((row["id"], payload, DomainStatus.INTERVIEW_AWAITING_CONFIRMATION))

    print(f"Found {len(records_to_correct)} records requiring domain_status correction (Expected: 4).")
    if len(records_to_correct) != 4:
        print(f"ABORT: Expected exactly 4 records to correct, found {len(records_to_correct)}.")
        sys.exit(1)
        
    # Execute correction in one single database transaction
    actual_db_writes = 0
    try:
        conn = sqlite3.connect(db_path)
        conn.isolation_level = None
        conn.execute("BEGIN TRANSACTION")
        
        for record_id, payload, target_ds in records_to_correct:
            payload["domain_status"] = target_ds.value
            
            # Non-PII audit event
            timeline = payload.get("timeline", [])
            timeline.append({
                "entry_id": f"audit_corr_{snapshot_time.strftime('%Y%m%d%H%M%S')}",
                "event_type": "DOMAIN_STATUS_CORRECTED",
                "status": target_ds.value,
                "timestamp": snapshot_time.isoformat(),
                "is_system_note": True,
                "body_preview": f"Corrected stored domain status to: {target_ds.value}"
            })
            payload["timeline"] = timeline
            
            new_ciphertext = persistence.encryptor.encrypt(json.dumps(payload))
            
            conn.execute(
                """
                UPDATE submission_records
                SET payload_ciphertext = ?, domain_status = ?
                WHERE id = ?
                """,
                (new_ciphertext, target_ds.value, record_id)
            )
            actual_db_writes += 1
            
        conn.execute("COMMIT")
        print("Database transaction COMMITTED successfully.")
    except Exception as e:
        if conn:
            conn.execute("ROLLBACK")
        print(f"ABORT: Transaction failed and ROLLED BACK. Error: {e}")
        sys.exit(1)

    # Post-commit verification
    summary = persistence.get_dashboard_summary()
    
    print("\n--- Post-Correction Dashboard Summary ---")
    print(f"Total: {summary.total}")
    print(f"Complete operational records: {summary.complete_records}")
    print(f"Follow-up Due (pending_follow_up): {summary.pending_follow_up}")
    print(f"Awaiting Response (awaiting_response): {summary.awaiting_response}")
    print(f"Interview Awaiting Confirmation (interview_awaiting_confirmation): {summary.interview_awaiting_confirmation}")
    print(f"Manager Action Required (manager_action_required): {summary.manager_action_required}")
    print(f"Needs Review (needs_review): {summary.needs_review}")
    print(f"Incomplete (incomplete): {summary.incomplete}")
    
    # Assertions
    assert summary.total == 89
    assert summary.complete_records == 87
    assert summary.pending_follow_up == 44
    assert summary.awaiting_response == 3
    assert summary.interview_awaiting_confirmation == 1
    assert summary.manager_action_required == 3
    assert summary.needs_review == 36
    assert summary.incomplete == 2
    
    print("\nAll Dashboard summary assertions passed 100%!")

if __name__ == "__main__":
    run()
