import os
import sys
import json
import sqlite3
from typing import Dict, Any

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.message_facts import analyze_conversation
from backend.app.domain.models import MessageDirection

def run():
    db_path = os.path.expanduser("~/.recruitment_agent/records.db")
    
    metrics = {
        "complete_records": 0,
        "incomplete_records_excluded": 0,
        "original_submissions_identified": 0,
        "multi_message_conversations": 0,
        "conversations_with_inbound": 0,
        "conversations_with_later_sent": 0,
        "automatic_replies_detected": 0,
        "delivery_failures_detected": 0,
        "conversations_requiring_classification": 0,
        "unknown_direction_messages": 0,
        "identity_chronology_errors": 0,
        "db_writes": 0,
        "graph_calls": 0,
        "ollama_calls": 0,
        "drafts_created": 0,
        "emails_sent": 0,
        "scheduler_changes": 0
    }
    
    # Initialize the persistence engine which sets up the keychain and encryptor
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
            
            # Exclude empty legacy placeholders (assuming incomplete == 0 messages)
            if not thread_messages:
                metrics["incomplete_records_excluded"] += 1
                continue
                
            metrics["complete_records"] += 1
            
            try:
                facts = analyze_conversation(source_immutable_id, thread_messages)
                
                # Metrics collection
                has_original = any(m.direction == MessageDirection.ORIGINAL_SUBMISSION for m in facts.messages)
                if has_original:
                    metrics["original_submissions_identified"] += 1
                else:
                    metrics["identity_chronology_errors"] += 1
                    
                if len(facts.messages) > 1:
                    metrics["multi_message_conversations"] += 1
                    
                if any(m.direction == MessageDirection.INBOUND_MESSAGE for m in facts.messages):
                    metrics["conversations_with_inbound"] += 1
                    
                if any(m.direction == MessageDirection.SENT_MESSAGE for m in facts.messages):
                    metrics["conversations_with_later_sent"] += 1
                    
                auto_replies = [m for m in facts.messages if m.direction == MessageDirection.AUTOMATIC_REPLY]
                metrics["automatic_replies_detected"] += len(auto_replies)
                
                unknowns = [m for m in facts.messages if m.direction == MessageDirection.UNKNOWN]
                metrics["unknown_direction_messages"] += len(unknowns)
                
                if facts.requires_classification:
                    metrics["conversations_requiring_classification"] += 1
                    
            except Exception as e:
                metrics["identity_chronology_errors"] += 1
                print(f"Error processing record {record_id[:8]}: {e}")

    # Output requested aggregate report
    print("--- Part 1: Deterministic Submission Detection Report ---")
    print(f"Complete records analyzed: {metrics['complete_records']}")
    print(f"Incomplete records excluded: {metrics['incomplete_records_excluded']}")
    print(f"Original submissions identified: {metrics['original_submissions_identified']}")
    print(f"Multi-message conversations: {metrics['multi_message_conversations']}")
    print(f"Conversations with inbound messages: {metrics['conversations_with_inbound']}")
    print(f"Conversations with later sent messages: {metrics['conversations_with_later_sent']}")
    print(f"Automatic replies detected: {metrics['automatic_replies_detected']}")
    print(f"Delivery failures detected: {metrics['delivery_failures_detected']} (counted in automatic replies)")
    print(f"Conversations requiring semantic classification: {metrics['conversations_requiring_classification']}")
    print(f"Unknown-direction messages: {metrics['unknown_direction_messages']}")
    print(f"Identity/chronology errors: {metrics['identity_chronology_errors']}")
    print("--- Safety Assertions ---")
    print(f"Database writes: {metrics['db_writes']}")
    print(f"Graph calls: {metrics['graph_calls']}")
    print(f"Ollama calls: {metrics['ollama_calls']}")
    print(f"Drafts created: {metrics['drafts_created']}")
    print(f"Emails sent: {metrics['emails_sent']}")
    print(f"Scheduler changes: {metrics['scheduler_changes']}")

if __name__ == "__main__":
    run()
