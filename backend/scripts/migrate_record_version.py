import sys
import os
import sqlite3
import json
import uuid

# Add the project root to sys.path so we can import backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.infrastructure.keychain import KeychainAdapter
from backend.app.application.backup_engine import create_encrypted_backup, restore_backup_to_quarantine

def migrate_database(db_path: str):
    if not os.path.exists(db_path):
        print(f"Error: Database {db_path} does not exist.")
        sys.exit(1)

    print(f"Starting explicit migration on {db_path}...")
    
    # Init persistence to read records for backup
    # Before the migration, the engine must still be able to read (since it uses SELECT *)
    engine = EncryptedPersistenceEngine(db_path=db_path)
    
    # 1. Create verified pre-migration checkpoint
    keychain = KeychainAdapter()
    print("Creating encrypted pre-migration backup via Keychain...")
    records = []
    
    # Read raw rows because schema migration hasn't happened yet, so list_records() will fail
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM submission_records").fetchall()
        for r in rows:
            # Reconstruct SubmissionRecord
            cipher = r['payload_ciphertext']
            payload = json.loads(engine.encryptor.decrypt(cipher))
            
            r_dict = dict(r)
            
            # Since this is just for backup, we need a SubmissionRecord object
            from backend.app.domain.models import SubmissionRecord
            sr = SubmissionRecord(
                id=r_dict['id'],
                graph_immutable_id=r_dict['graph_immutable_id'],
                conversation_id=r_dict['conversation_id'],
                job_id=r_dict.get('job_id'),
                ep_reference=r_dict.get('ep_reference'),
                candidate_name=r_dict.get('candidate_name'),
                skill=payload.get('skill'),
                customer=payload.get('customer'),
                location=payload.get('location'),
                tcs_eligibility=r_dict.get('tcs_eligibility') or 'eligible',
                domain_status=r_dict['domain_status'],
                received_at=r_dict['received_at'],
                created_at=r_dict['created_at'],
                payload=payload,
                record_version=1,  # Default for backup purposes
                manager_notes=payload.get('manager_notes', ''),
                system_notes=payload.get('system_notes', '')
            )
            records.append(sr)
            
    backup_result = create_encrypted_backup(
        records=records,
        manager_identity="tarun@clifyx.com",
        keychain_adapter=keychain
    )
    
    # Verify backup integrity
    quarantine_path = f"{backup_result.backup_file_path}.restore_rehearsal.db"
    try:
        restore_result, restored_records = restore_backup_to_quarantine(
            backup_file_path=backup_result.backup_file_path,
            keychain_adapter=keychain
        )
        print(f"Backup rehearsal restored {len(restored_records)} records to quarantine.")
        assert len(restored_records) == 89
    finally:
        if os.path.exists(quarantine_path):
            os.remove(quarantine_path)
    
    # 2. Begin a transaction
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        
        # Check if column exists
        cur = conn.execute("PRAGMA table_info(submission_records);")
        columns = [row[1] for row in cur.fetchall()]
        if 'record_version' in columns:
            print("Column 'record_version' already exists. Aborting migration.")
            sys.exit(0)
            
        try:
            # 3. Add the integer column only if missing
            # 4. Initialize existing records to version 1
            conn.execute("ALTER TABLE submission_records ADD COLUMN record_version INTEGER NOT NULL DEFAULT 1;")
            
            # 5. Preserve all other columns and encrypted payloads
            # 6. Validate 89 records and approved status/classification totals
            rows = conn.execute("SELECT * FROM submission_records").fetchall()
            if len(rows) != 89:
                raise ValueError(f"Expected 89 records, got {len(rows)}")
                
            complete = 0
            incomplete = 0
            needs_review = 0
            pending_follow_up = 0
            awaiting_response = 0
            manager_action_required = 0
            interview_awaiting_confirmation = 0
            
            for r in rows:
                if r['record_version'] != 1:
                    raise ValueError(f"Record {r['id']} does not have version 1.")
                
                cipher = r['payload_ciphertext']
                payload = json.loads(engine.encryptor.decrypt(cipher))
                msgs = payload.get('thread_messages', [])
                
                if not msgs:
                    incomplete += 1
                else:
                    complete += 1
                    status = r['domain_status']
                    if status == "NeedsReview": needs_review += 1
                    elif status == "PendingFollowUp": pending_follow_up += 1
                    elif status == "AwaitingResponse": awaiting_response += 1
                    elif status == "ManagerActionRequired": manager_action_required += 1
                    elif status == "InterviewAwaitingConfirmation": interview_awaiting_confirmation += 1
            
            if complete != 87: raise ValueError(f"Expected 87 complete records, got {complete}")
            if incomplete != 2: raise ValueError(f"Expected 2 incomplete records, got {incomplete}")
            if pending_follow_up != 44: raise ValueError(f"Expected 44 PendingFollowUp, got {pending_follow_up}")
            if awaiting_response != 3: raise ValueError(f"Expected 3 AwaitingResponse, got {awaiting_response}")
            if manager_action_required != 3: raise ValueError(f"Expected 3 ManagerActionRequired, got {manager_action_required}")
            if needs_review != 36: raise ValueError(f"Expected 36 NeedsReview, got {needs_review}")
            if interview_awaiting_confirmation != 1: raise ValueError(f"Expected 1 InterviewAwaitingConfirmation, got {interview_awaiting_confirmation}")
            
            print("Validation successful. Transaction will be committed.")
            # 7. Commit only after validation (automatic context manager commit)
        except Exception as e:
            # 8. Roll back completely on error (automatic context manager rollback)
            print(f"Error during migration: {e}. Transaction rolling back.")
            raise

if __name__ == "__main__":
    db = os.path.expanduser("~/.recruitment_agent/records.db")
    if len(sys.argv) > 1:
        db = sys.argv[1]
    migrate_database(db)
