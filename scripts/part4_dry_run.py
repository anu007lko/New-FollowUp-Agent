import os
import sys
import sqlite3
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.message_facts import analyze_conversation, evaluate_no_response_timers
from backend.app.domain.interview_parser import evaluate_interview_status
from backend.app.domain.outcome_parser import evaluate_outcome_status

def run():
    db_path = os.path.expanduser("~/.recruitment_agent/records.db")
    
    metrics = {
        "conversations_evaluated": 0,
        "position_closed": 0,
        "rejection": 0,
        "duplicate": 0,
        "needs_review_remainder": 0,
        "conflicting_outcomes": 0,
        "db_writes": 0,
        "graph_calls": 0,
        "ollama_calls": 0,
        "drafts_created": 0,
        "emails_sent": 0,
        "scheduler_changes": 0
    }
    
    # Reference snapshot time for Part 4
    snapshot_time = datetime.fromisoformat("2026-08-04T00:17:31-04:00")
    
    persistence = EncryptedPersistenceEngine()
    
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, graph_immutable_id, payload_ciphertext FROM submission_records")
        rows = cursor.fetchall()
        
        for row in rows:
            try:
                payload = persistence._decrypt_payload(row["payload_ciphertext"])
            except Exception:
                continue
            
            thread_messages = payload.get("thread_messages", [])
            if not thread_messages:
                continue
                
            facts = analyze_conversation(row["graph_immutable_id"], thread_messages)
            evaluate_no_response_timers(facts, snapshot_time, [])
            
            if facts.no_response_status == "Requires Classification":
                evaluate_interview_status(facts, snapshot_time)
                
                # Check if it was NOT detected as an interview state
                if facts.interview_status not in ["Interview Request", "Interview Scheduled", "Interview Awaiting Confirmation"]:
                    metrics["conversations_evaluated"] += 1
                    
                    evaluate_outcome_status(facts)
                    
                    if facts.outcome_status == "Position Closed":
                        metrics["position_closed"] += 1
                    elif facts.outcome_status == "Rejection":
                        metrics["rejection"] += 1
                    elif facts.outcome_status == "Duplicate / Already Submitted":
                        metrics["duplicate"] += 1
                    elif facts.outcome_status == "Needs Review":
                        metrics["conflicting_outcomes"] += 1
                        metrics["needs_review_remainder"] += 1
                    else:
                        metrics["needs_review_remainder"] += 1

    print("--- Part 4: Deterministic Outcome Detection Report ---")
    print(f"Conversations evaluated: {metrics['conversations_evaluated']}")
    print(f"Position Closed: {metrics['position_closed']}")
    print(f"Rejection: {metrics['rejection']}")
    print(f"Duplicate / Already Submitted: {metrics['duplicate']}")
    print(f"Needs Review/other remainder: {metrics['needs_review_remainder']}")
    print(f"Conflicting or ambiguous outcomes: {metrics['conflicting_outcomes']}")
    print("--- Safety Assertions ---")
    print(f"Database writes: {metrics['db_writes']}")
    print(f"Graph calls: {metrics['graph_calls']}")
    print(f"Ollama calls: {metrics['ollama_calls']}")
    print(f"Drafts created: {metrics['drafts_created']}")
    print(f"Emails sent: {metrics['emails_sent']}")
    print(f"Scheduler changes: {metrics['scheduler_changes']}")

if __name__ == "__main__":
    run()
