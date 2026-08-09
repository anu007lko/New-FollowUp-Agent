import sys
import os
import sqlite3
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.infrastructure.ollama_client import OllamaAdvisoryClient
from backend.app.domain.models import TimelineEntry

def run_resource_test():
    # Require explicit manual authorization and OLLAMA_ENABLED environment variable
    if os.environ.get("OLLAMA_ENABLED", "false").lower() not in ("true", "1", "yes"):
        print("EXPLICIT MANUAL AUTHORIZATION REQUIRED: Set OLLAMA_ENABLED=True to run resource test.")
        return

    client = OllamaAdvisoryClient()

    if not client.is_available():
        print("Ollama client unavailable or memory pressure too high. Aborting test.")
        return

    print("Running resource test via protected OllamaAdvisoryClient...")
    
    persistence = EncryptedPersistenceEngine()
    
    with sqlite3.connect(persistence.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT payload_ciphertext FROM submission_records LIMIT 1")
        row = cursor.fetchone()
        if not row:
            print("No records found to test.")
            return
            
        payload = persistence._decrypt_payload(row["payload_ciphertext"])
        thread = payload.get("thread_messages", [])
        
        timeline_entries = []
        for idx, m in enumerate(thread):
            timeline_entries.append(
                TimelineEntry(
                    entry_id=f"entry_{idx}",
                    sender=m.get("from", {}).get("emailAddress", {}).get("address", "unknown"),
                    timestamp=m.get("sentDateTime") or "2026-08-01T00:00:00Z",
                    body_preview=m.get("bodyPreview", "")
                )
            )

        res = client.analyze_conversation(timeline_entries)
        print(f"Result Category: {res.category}, Confidence: {res.confidence}")

if __name__ == "__main__":
    run_resource_test()
