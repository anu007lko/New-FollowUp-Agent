import sys
import os
import sqlite3
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine

def main():
    persistence = EncryptedPersistenceEngine()
    db_path = persistence.db_path
    
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        records = conn.execute("SELECT * FROM submission_records").fetchall()
        
        extra_records = []
        for row in records:
            cipher = row['payload_ciphertext']
            payload = json.loads(persistence.encryptor.decrypt(cipher))
            msgs = payload.get('thread_messages')
            if msgs is None or len(msgs) == 0:
                extra_records.append(row)
                
        print(f"Found {len(extra_records)} records with 0 messages.")
        for r in extra_records:
            print(f"Record {r['id'][:8]}... Created: {r['created_at']}")
            # inspect the payload keys and metadata without printing PII
            payload = json.loads(persistence.encryptor.decrypt(r['payload_ciphertext']))
            meta = payload.get('metadata', {})
            print(f"  Has metadata job_id? {'job_id' in meta}")
            print(f"  Is synthetic/test? {r['id'].startswith('test') or 'synthetic' in payload.get('conversation_id', '')}")
            
if __name__ == '__main__':
    main()
