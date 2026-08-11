from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.api.routes import post_close_record, CloseRecordRequest
import backend.app.api.routes as routes_mod

engine = EncryptedPersistenceEngine()
routes_mod.persistence = engine

rec_id = "23fe672a-96b1-4050-8512-0dc9a8373ff1"
snapshot = engine.get_record_payload_snapshot(rec_id)
payload, ver, ds = snapshot

print("=== VERIFYING FIX FOR SURESH K BADIGA ===")
print("Pre-Close Status:", ds)

req = CloseRecordRequest(
    record_id=rec_id,
    graph_immutable_id=payload.get("graph_immutable_id"),
    conversation_id=payload.get("conversation_id"),
    record_version=ver,
    reason="Duplicate submission entry",
    close_note="Duplicate submission confirmed by manager for Suresh K Badiga"
)

rec_after = post_close_record(rec_id, req, manager_identity="tarun@clifyx.com")

print("\n=== POST-CLOSE VERIFICATION ===")
print(f"Candidate Name: {rec_after.candidate_name}")
print(f"Domain Status: {rec_after.domain_status.value}")
print(f"Closed At: {rec_after.closed_at}")
print(f"Close Reason: {rec_after.close_reason}")
print(f"Close Note: {rec_after.close_note}")
print(f"Structured Evidence Category: {rec_after.structured_evidence.category if rec_after.structured_evidence else None}")

# Check database reload
snapshot_after = engine.get_record_payload_snapshot(rec_id)
_, _, ds_after = snapshot_after
print(f"Persisted Status in SQLite after reload: {ds_after}")

assert ds_after == "Closed"
assert rec_after.close_reason == "Duplicate submission entry"
print("✓ SURESH K BADIGA SUCCESSFULLY CLOSED WITH REASON 'Duplicate submission entry'!")

dash = engine.get_dashboard_summary()
in_active = [r for r in dash.records if r.id == rec_id and r.domain_status.value in ("PendingFollowUp", "ManagerActionRequired", "InterviewAwaitingConfirmation")]
print(f"Suresh K Badiga present in active queues: {len(in_active)}")
assert len(in_active) == 0

