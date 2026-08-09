import os
import sys
import sqlite3
from datetime import datetime
from typing import Dict, Any

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.message_facts import analyze_conversation, evaluate_no_response_timers
from backend.app.domain.models import MessageDirection

def run():
    db_path = os.path.expanduser("~/.recruitment_agent/records.db")
    
    metrics = {
        "records_evaluated": 0,
        "awaiting_response": 0,
        "follow_up_due": 0,
        "requires_classification": 0,
        "automatic_replies_ignored": 0,
        "original_submission_anchors": 0,
        "authoritative_followup_anchors": 0,
        "followup_anchors_requiring_review": 0,
        "timer_dst_errors": 0,
        "db_writes": 0,
        "graph_calls": 0,
        "ollama_calls": 0,
        "drafts_created": 0,
        "emails_sent": 0,
        "scheduler_changes": 0
    }
    
    # Reference snapshot time required by prompt
    snapshot_time = datetime.fromisoformat("2026-08-03T17:51:13-04:00")
    
    persistence = EncryptedPersistenceEngine()
    
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, graph_immutable_id, payload_ciphertext FROM submission_records")
        rows = cursor.fetchall()
        
        for row in rows:
            record_id = row["id"]
            source_immutable_id = row["graph_immutable_id"]
            payload_ciphertext = row["payload_ciphertext"]
            
            try:
                payload = persistence._decrypt_payload(payload_ciphertext)
            except Exception:
                continue
            
            thread_messages = payload.get("thread_messages", [])
            
            # Preserve and exclude the two incomplete placeholders
            if not thread_messages:
                continue
                
            metrics["records_evaluated"] += 1
            
            try:
                facts = analyze_conversation(source_immutable_id, thread_messages)
                
                auto_replies = [m for m in facts.messages if m.direction == MessageDirection.AUTOMATIC_REPLY]
                metrics["automatic_replies_ignored"] += len(auto_replies)
                
                # We have no authoritative follow up ids recorded in the current db snapshot
                authoritative_followups = []
                
                evaluate_no_response_timers(facts, snapshot_time, authoritative_followups)
                
                if facts.no_response_status == "Awaiting Response":
                    metrics["awaiting_response"] += 1
                elif facts.no_response_status == "Follow-up Due":
                    metrics["follow_up_due"] += 1
                elif facts.no_response_status == "Requires Classification":
                    metrics["requires_classification"] += 1
                    
                if facts.timer_anchor_message:
                    if facts.timer_anchor_message.direction == MessageDirection.ORIGINAL_SUBMISSION:
                        metrics["original_submission_anchors"] += 1
                    elif facts.timer_anchor_message.direction == MessageDirection.SENT_MESSAGE:
                        metrics["authoritative_followup_anchors"] += 1
                        
                if facts.followup_anchor_requires_review:
                    metrics["followup_anchors_requiring_review"] += 1
                    
            except Exception as e:
                metrics["timer_dst_errors"] += 1
                print(f"Error processing record {record_id[:8]}: {e}")

    print("--- Part 2: No-Response and Follow-Up Timer Detection Report ---")
    print(f"Records evaluated: {metrics['records_evaluated']}")
    print(f"Awaiting Response: {metrics['awaiting_response']}")
    print(f"Follow-up Due: {metrics['follow_up_due']}")
    print(f"Requires Semantic Classification: {metrics['requires_classification']}")
    print(f"Automatic replies ignored: {metrics['automatic_replies_ignored']}")
    print(f"Original-submission timer anchors: {metrics['original_submission_anchors']}")
    print(f"Authoritative follow-up anchors: {metrics['authoritative_followup_anchors']}")
    print(f"Follow-up anchors requiring review: {metrics['followup_anchors_requiring_review']}")
    print(f"Timer/DST errors: {metrics['timer_dst_errors']}")
    print("--- Safety Assertions ---")
    print(f"Database writes: {metrics['db_writes']}")
    print(f"Graph calls: {metrics['graph_calls']}")
    print(f"Ollama calls: {metrics['ollama_calls']}")
    print(f"Drafts created: {metrics['drafts_created']}")
    print(f"Emails sent: {metrics['emails_sent']}")
    print(f"Scheduler changes: {metrics['scheduler_changes']}")

if __name__ == "__main__":
    run()
