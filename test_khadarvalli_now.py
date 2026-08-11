from datetime import datetime, timezone
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.consolidated_classifier import classify_record, PROPOSED_TO_DOMAIN_STATUS
from backend.app.domain.date_utils import TIMEZONE_NEW_YORK

engine = EncryptedPersistenceEngine()
rec_id = "cf53b6e1-cad0-43ed-a4db-7cf570d36b45"

snapshot = engine.get_record_payload_snapshot(rec_id)
payload, ver, ds = snapshot

print("=== KHADARVALLI SHAIK CURRENT CLASSIFICATION TEST ===")
print("Current DB Status:", ds)

# Test at current EDT time (10:40 AM EDT Tuesday Aug 11, after Monday Aug 10 6 PM interview)
current_time_edt = datetime.now(TIMEZONE_NEW_YORK)
res = classify_record(
    payload.get("graph_immutable_id", "graph-khadarvalli"),
    payload.get("thread_messages", []),
    current_time_edt,
    timeline=payload.get("timeline", [])
)

print(f"Current Time: {current_time_edt.isoformat()}")
print(f"Proposed Status: {res.proposed_status}")
print(f"Category: {res.category}")
print(f"Reason Code: {res.reason_code}")
print(f"Mapped Domain Status: {PROPOSED_TO_DOMAIN_STATUS.get(res.proposed_status).value}")

