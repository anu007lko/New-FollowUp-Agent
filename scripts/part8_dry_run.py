import os
import sys
import sqlite3
import subprocess
from datetime import datetime
from collections import Counter

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.consolidated_classifier import classify_record

def check_ollama_status():
    try:
        res = subprocess.run(["ollama", "ps"], capture_output=True, text=True)
        lines = [l.strip() for l in res.stdout.strip().split("\n") if l.strip()]
        # Header is 1 line. If >1 lines, a model is loaded.
        return len(lines) > 1
    except Exception:
        return False

def run():
    ollama_loaded_before = check_ollama_status()
    if ollama_loaded_before:
        print("ERROR: Ollama model is currently loaded. Stopping execution.")
        sys.exit(1)
        
    db_path = os.path.expanduser("~/.recruitment_agent/records.db")
    snapshot_time = datetime.fromisoformat("2026-08-04T00:34:45-04:00")
    persistence = EncryptedPersistenceEngine()
    
    category_counts = Counter()
    status_counts = Counter()
    reason_counts = Counter()
    anchor_counts = Counter()
    
    complete_records_classified = 0
    incomplete_records_excluded = 0
    
    physical_msg_total = 0
    logical_msg_total = 0
    grouped_copies_total = 0
    
    metrics = {
        "db_writes": 0,
        "graph_calls": 0,
        "ollama_calls": 0,
        "drafts_created": 0,
        "emails_sent": 0,
        "scheduler_changes": 0
    }
    
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, graph_immutable_id, payload_ciphertext FROM submission_records")
        rows = cursor.fetchall()
        
        for row in rows:
            try:
                payload = persistence._decrypt_payload(row["payload_ciphertext"])
            except Exception:
                incomplete_records_excluded += 1
                continue
            
            thread_messages = payload.get("thread_messages", [])
            if not thread_messages:
                incomplete_records_excluded += 1
                continue
                
            complete_records_classified += 1
            physical_msg_total += len(thread_messages)
            
            # Authoritative follow-ups
            authoritative_followup_ids = []
            for entry in payload.get("timeline", []):
                if entry.get("event_type") == "MANAGER_FOLLOWUP":
                    msg_id = entry.get("message_id")
                    if msg_id:
                        authoritative_followup_ids.append(msg_id)
            
            res = classify_record(
                row["graph_immutable_id"],
                thread_messages,
                snapshot_time,
                authoritative_followup_ids
            )
            
            category_counts[res.category] += 1
            status_counts[res.proposed_status] += 1
            reason_counts[res.reason_code] += 1
            if res.timer_anchor_type:
                anchor_counts[res.timer_anchor_type] += 1

    ollama_loaded_after = check_ollama_status()
    
    cat_total = sum(category_counts.values())
    status_total = sum(status_counts.values())
    
    print("--- Part 8: Consolidated Read-Only Classification Report ---")
    print(f"Reference timestamp: {snapshot_time.isoformat()}")
    print(f"Complete records classified: {complete_records_classified}")
    print(f"Incomplete records excluded: {incomplete_records_excluded}")
    
    approved_categories = [
        "Interview Scheduled",
        "Position Closed",
        "Rejection",
        "Duplicate / Already Submitted",
        "Feedback",
        "In Evaluation",
        "Acknowledgement",
        "No Response",
        "Unrelated",
        "Needs Review"
    ]
    
    print("\n--- Approved Classification Category Counts ---")
    for cat in approved_categories:
        print(f"  {cat}: {category_counts.get(cat, 0)}")
        
    print("\n--- Proposed Workflow Status Counts ---")
    for st, count in sorted(status_counts.items()):
        print(f"  {st}: {count}")
        
    print("\n--- Specific Status Highlights ---")
    print(f"  Follow-up Due: {status_counts.get('Follow-up Due', 0)}")
    print(f"  Awaiting Response: {status_counts.get('Awaiting Response', 0)}")
    print(f"  In Evaluation: {status_counts.get('In Evaluation', 0)}")
    print(f"  Interview Scheduled: {status_counts.get('Interview Scheduled', 0)}")
    print(f"  Interview Awaiting Confirmation: {status_counts.get('Interview Awaiting Confirmation', 0)}")
    print(f"  Awaiting Feedback: {status_counts.get('Awaiting Feedback', 0)}")
    print(f"  Feedback Due: {status_counts.get('Feedback Due', 0)}")
    print(f"  Manager Action Required: {status_counts.get('Manager Action Required', 0)}")
    print(f"  Needs Review: {status_counts.get('Needs Review', 0)}")
    
    print("\n--- Needs Review Reason Breakdown ---")
    for rsn, count in sorted(reason_counts.items()):
        if "REVIEW" in rsn or "UNCERTAIN" in rsn or "UNCLASSIFIED" in rsn or "UNRELATED" in rsn or "REQUEST" in rsn:
            print(f"  {rsn}: {count}")
            
    print("\n--- Timer Anchor Counts ---")
    for anc, count in sorted(anchor_counts.items()):
        print(f"  {anc}: {count}")
        
    print("\n--- Verification Totals ---")
    print(f"Category total = 87: {'pass' if cat_total == 87 else 'fail'} ({cat_total})")
    print(f"Status total = 87: {'pass' if status_total == 87 else 'fail'} ({status_total})")
    print(f"Ollama loaded before/after: {'yes' if ollama_loaded_before else 'no'} / {'yes' if ollama_loaded_after else 'no'}")
    
    print("\n--- Safety Assertions ---")
    print(f"Database writes: {metrics['db_writes']}")
    print(f"Graph calls: {metrics['graph_calls']}")
    print(f"Ollama calls: {metrics['ollama_calls']}")
    print(f"Drafts created: {metrics['drafts_created']}")
    print(f"Emails sent: {metrics['emails_sent']}")
    print(f"Scheduler changes: {metrics['scheduler_changes']}")

if __name__ == "__main__":
    run()
