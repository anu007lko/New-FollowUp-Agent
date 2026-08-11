from datetime import datetime, timezone
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.consolidated_classifier import classify_record

engine = EncryptedPersistenceEngine()
rec_id = "cf53b6e1-cad0-43ed-a4db-7cf570d36b45"

snapshot = engine.get_record_payload_snapshot(rec_id)
payload, ver, ds = snapshot

print("=== KHADARVALLI SHAIK CLASSIFICATION VERIFICATION ===")
print(f"Record ID: {rec_id}")
print(f"Candidate Name: {payload.get('candidate_name')}")
print(f"Original Status in DB: {ds}")

res = classify_record(
    payload.get("graph_immutable_id", "graph-khadarvalli"),
    payload.get("thread_messages", []),
    datetime.now(timezone.utc),
    timeline=payload.get("timeline", [])
)

print(f"\nClassifier Result Proposed Status: {res.proposed_status}")
print(f"Classifier Result Category: {res.category}")
print(f"Classifier Result Reason Code: {res.reason_code}")
print(f"Classifier Result Interview Datetime: {res.interview_datetime}")

