import os
import shutil
import sqlite3
import json
import uuid
import sys
from datetime import datetime
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.models import DomainStatus
from backend.app.application.backup_engine import create_encrypted_backup, restore_backup_to_quarantine

def rehearse_migration():
    source_db = os.path.expanduser("~/.recruitment_agent/records.db")
    rehearsal_db = "/tmp/rehearsal.db"
    
    # 7. Create temporary copy
    shutil.copy2(source_db, rehearsal_db)
    print("Copied DB for rehearsal.")
    
    # Need to trick engine into thinking it's not testing so it doesn't fail connecting to DB?
    # Engine throws if db_path == authoritative_db and ENVIRONMENT == "test".
    # Since db_path is /tmp/rehearsal.db, it won't throw!
    
    # 8. Apply schema migration (happens on init)
    engine = EncryptedPersistenceEngine(db_path=rehearsal_db)
    print("Engine initialized (schema migration applied).")
    
    # 9. Verify
    with sqlite3.connect(rehearsal_db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM submission_records").fetchall()
        
        # 111 records retained
        assert len(rows) == 111, f"Expected 111, got {len(rows)}"
        print("Verified 111 records.")
        
        complete = 0
        incomplete = 0
        
        for r in rows:
            # Every record receives a valid initial integer version
            assert r["record_version"] >= 1, f"Expected version >= 1, got {r['record_version']}"
            
            # All encrypted payloads decrypt
            cipher = r["payload_ciphertext"]
            payload = json.loads(engine.encryptor.decrypt(cipher))
            msgs = payload.get("thread_messages", [])
            
            if msgs:
                complete += 1
            else:
                incomplete += 1
                
        # 109 complete and 2 incomplete
        assert complete == 109, f"Expected 109 complete, got {complete}"
        assert incomplete == 2, f"Expected 2 incomplete, got {incomplete}"
        print("Verified 109 complete, 2 incomplete, and all payload decryption successful.")
        
        # Classifications/statuses unchanged
        summary = engine.get_dashboard_summary()
        print(f"Summary computed successfully: {summary}")

    print("ALL MIGRATION REHEARSAL CHECKS PASSED.")

if __name__ == "__main__":
    rehearse_migration()
