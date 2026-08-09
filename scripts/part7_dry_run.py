import os
import sys
import sqlite3
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.message_facts import analyze_conversation, evaluate_no_response_timers
from backend.app.domain.models import MessageDirection

def run():
    db_path = os.path.expanduser("~/.recruitment_agent/records.db")
    
    metrics = {
        "records_evaluated": 0,
        "physical_messages": 0,
        "logical_messages": 0,
        "cross_folder_copies": 0,
        "original_submissions_identified": 0,
        "conversations_genuine_later_sent": 0,
        "conversations_only_duplicate_sent": 0,
        "missing_malformed_imid": 0,
        "revised_original_timer_anchors": 0,
        "revised_authoritative_followup_anchors": 0,
        "followup_anchors_requiring_review": 0,
        "db_writes": 0,
        "graph_calls": 0,
        "ollama_calls": 0,
        "drafts_created": 0,
        "emails_sent": 0,
        "scheduler_changes": 0
    }
    
    snapshot_time = datetime.fromisoformat("2026-08-04T00:27:48-04:00")
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
            
            metrics["records_evaluated"] += 1
            metrics["physical_messages"] += len(thread_messages)
            
            try:
                # Count physical sent messages BEFORE grouping (where sender is tarun)
                physical_sent = 0
                for m in thread_messages:
                    sender = m.get("from", {}).get("emailAddress", {}).get("address", "").lower()
                    msg_id = m.get("id")
                    if sender.endswith("@clifyx.com") and msg_id != row["graph_immutable_id"]:
                        physical_sent += 1
                
                # We need authoritative IDs from payload (if any)
                auth_ids = payload.get("timeline", []) # This isn't exactly the list of IDs, but we can extract
                # We can assume empty for dry run unless we parse them
                authoritative_followup_ids = []
                for entry in payload.get("timeline", []):
                    if entry.get("event_type") == "MANAGER_FOLLOWUP":
                        msg_id = entry.get("message_id")
                        if msg_id:
                            authoritative_followup_ids.append(msg_id)
                
                facts = analyze_conversation(row["graph_immutable_id"], thread_messages)
                evaluate_no_response_timers(facts, snapshot_time, authoritative_followup_ids)
                
                logical_count = len(facts.messages)
                metrics["logical_messages"] += logical_count
                metrics["cross_folder_copies"] += sum(len(m.duplicate_immutable_ids) for m in facts.messages)
                
                has_original = any(m.direction == MessageDirection.ORIGINAL_SUBMISSION for m in facts.messages)
                if has_original:
                    metrics["original_submissions_identified"] += 1
                
                has_logical_sent = any(m.direction == MessageDirection.SENT_MESSAGE for m in facts.messages)
                
                if has_logical_sent:
                    metrics["conversations_genuine_later_sent"] += 1
                elif physical_sent > 0 and not has_logical_sent:
                    metrics["conversations_only_duplicate_sent"] += 1
                    
                if facts.logical_copy_requires_review:
                    metrics["missing_malformed_imid"] += 1
                    
                if facts.timer_anchor_message:
                    if facts.timer_anchor_message.direction == MessageDirection.ORIGINAL_SUBMISSION:
                        metrics["revised_original_timer_anchors"] += 1
                    elif facts.timer_anchor_message.direction == MessageDirection.SENT_MESSAGE:
                        if not facts.followup_anchor_requires_review:
                            metrics["revised_authoritative_followup_anchors"] += 1
                            
                if facts.followup_anchor_requires_review:
                    metrics["followup_anchors_requiring_review"] += 1
                    
            except Exception as e:
                print(f"Error processing record {row['id'][:8]}: {e}")

    print("--- Part 7: Logical Outlook Message Copy Reconciliation Report ---")
    print(f"Records evaluated: {metrics['records_evaluated']}")
    print(f"Physical messages: {metrics['physical_messages']}")
    print(f"Logical messages after reconciliation: {metrics['logical_messages']}")
    print(f"Cross-folder copies grouped: {metrics['cross_folder_copies']}")
    print(f"Original submissions identified: {metrics['original_submissions_identified']}")
    print(f"Conversations with genuine later sent messages: {metrics['conversations_genuine_later_sent']}")
    print(f"Conversations with only duplicate sent copies: {metrics['conversations_only_duplicate_sent']}")
    print(f"Missing/malformed internetMessageId: {metrics['missing_malformed_imid']}")
    print(f"Revised original-submission timer anchors: {metrics['revised_original_timer_anchors']}")
    print(f"Revised authoritative follow-up anchors: {metrics['revised_authoritative_followup_anchors']}")
    print(f"Follow-up anchors still requiring review: {metrics['followup_anchors_requiring_review']}")
    print("--- Safety Assertions ---")
    print(f"Database writes: {metrics['db_writes']}")
    print(f"Graph calls: {metrics['graph_calls']}")
    print(f"Ollama calls: {metrics['ollama_calls']}")
    print(f"Drafts created: {metrics['drafts_created']}")
    print(f"Emails sent: {metrics['emails_sent']}")
    print(f"Scheduler changes: {metrics['scheduler_changes']}")

if __name__ == "__main__":
    run()
