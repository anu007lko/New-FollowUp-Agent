import sqlite3
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine

def find_draft():
    persistence = EncryptedPersistenceEngine()
    with sqlite3.connect(persistence.db_path) as conn:
        conn.row_factory = sqlite3.Row
        records = conn.execute("SELECT id, graph_immutable_id, conversation_id, payload_ciphertext FROM submission_records").fetchall()
        
        for row in records:
            payload = persistence._decrypt_payload(row["payload_ciphertext"])
            audit_events = payload.get("audit_events", [])
            timeline = payload.get("timeline", [])
            
            if audit_events:
                print(f"Record {row['id']} has audit_events: {audit_events}")
            
            for t in timeline:
                # check if timeline item mentions audit
                if "audit" in str(t).lower():
                    print(f"Record {row['id']} Timeline Audit: {t}")
                    
if __name__ == "__main__":
    find_draft()

