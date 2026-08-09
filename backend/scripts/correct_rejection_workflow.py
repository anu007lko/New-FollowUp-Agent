import os
import sys
import json
import shutil
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.models import DomainStatus

db_path = os.path.expanduser("~/.recruitment_agent/records.db")

print("1. Creating checkpoint...")
checkpoint_path = os.path.expanduser("~/.recruitment_agent/records_checkpoint_rejection.db")
shutil.copy2(db_path, checkpoint_path)
print(f"Checkpoint created at {checkpoint_path}")

engine = EncryptedPersistenceEngine(db_path)

print("2. Opening engine...")
r_id = "b549ab8c-b3e2-47ee-9baf-1a7e0e977608"

def apply_correction(engine, r_id):
    import sqlite3
    with sqlite3.connect(engine.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT payload_ciphertext, record_version FROM submission_records WHERE id = ?", (r_id,)).fetchone()
        if not row:
            print("Record not found!")
            return
            
        current_version = row["record_version"]
        payload_str = engine.encryptor.decrypt(row["payload_ciphertext"])
        payload = json.loads(payload_str)
        
        print(f"Current version: {current_version}")
        
        audit_events = payload.get("audit_events", [])
        new_event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "WORKFLOW_CORRECTION",
            "manager_identity": "tarun@clifyx.com",
            "details": "Corrected premature closure of rejection decision to Manager Action Required."
        }
        audit_events.append(new_event)
        payload["audit_events"] = audit_events
        
        new_payload_str = json.dumps(payload)
        new_cipher = engine.encryptor.encrypt(new_payload_str)
        
        new_status = DomainStatus.MANAGER_ACTION_REQUIRED.value
        
        conn.execute("""
            UPDATE submission_records
            SET domain_status = ?,
                payload_ciphertext = ?,
                record_version = record_version + 1
            WHERE id = ? AND record_version = ?
        """, (new_status, new_cipher, r_id, current_version))
        
        if conn.execute("SELECT changes()").fetchone()[0] != 1:
            print("Failed to apply correction atomically!")
        else:
            print(f"Corrected {r_id} to {new_status}, version incremented to {current_version + 1}")

apply_correction(engine, r_id)

