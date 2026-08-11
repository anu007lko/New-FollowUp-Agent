import sys, os
from datetime import datetime, timezone
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.consolidated_classifier import classify_record

engine = EncryptedPersistenceEngine()
rec = engine.get_record_by_id("2a095c2d-724b-4cd7-8e6a-e2ca95aff93e")
snapshot = engine.get_record_payload_snapshot(rec.id)
payload, version, status = snapshot

print(f"DB Row domain_status column: {status}")

cls = classify_record(
    source_immutable_id=payload.get("source_immutable_id") or payload.get("graph_immutable_id"),
    thread_messages=payload.get("thread_messages", []),
    current_time=datetime.now(timezone.utc),
    linked_conversations=payload.get("linked_conversations", [])
)

print("=== CLASSIFY_RECORD OUTPUT ===")
print(f"Category: {cls.category}")
print(f"Proposed Status: {cls.proposed_status}")
print(f"Reason Code: {cls.reason_code}")

