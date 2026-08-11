import sys, os
from datetime import datetime, timezone
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.consolidated_classifier import classify_record
from backend.app.domain.message_facts import analyze_conversation
from backend.app.domain.interview_parser import evaluate_interview_status

engine = EncryptedPersistenceEngine()
rec_id = "0305792b-2ef1-4b06-98a1-6f74ab58c0d1"
rec = engine.get_record_by_id(rec_id)
snapshot = engine.get_record_payload_snapshot(rec_id)
payload, ver, status = snapshot

thread_msgs = payload.get("thread_messages", [])
facts = analyze_conversation(rec.graph_immutable_id, thread_msgs)

print("=== FACTS ANALYSIS ===")
print(f"Facts total messages: {len(facts.messages)}")
for m in facts.messages:
    print(f"  Sender: {m.sender_email} | Direction: {m.direction} | Meaningful: {m.is_meaningful} | Bounce/Auto: {m.is_auto_reply or m.is_bounce}")
    print(f"  Subject: {m.subject}")
    print(f"  Body Preview: {m.body_preview}")

evaluate_interview_status(facts)
print(f"Outcome Interview Status: {facts.interview_status}")
print(f"Outcome Interview State: {facts.interview_state}")

cls = classify_record(
    rec.graph_immutable_id,
    thread_msgs,
    datetime.now(timezone.utc)
)

print(f"Classify Record Proposed Status: {cls.proposed_status} | Category: {cls.category} | Reason Code: {cls.reason_code}")

