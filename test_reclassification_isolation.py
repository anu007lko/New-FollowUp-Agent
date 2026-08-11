from datetime import datetime, timezone
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.consolidated_classifier import classify_record
from backend.app.api.routes import post_outcome_decision, OutcomeDecisionRequest
import backend.app.api.routes as routes_mod

engine = EncryptedPersistenceEngine()
routes_mod.persistence = engine

rec_id = "test_closure_reclass_isolation"
payload = {
    "id": rec_id,
    "record_version": 1,
    "domain_status": "InterviewAwaitingConfirmation",
    "candidate_name": "Test Closure Candidate",
    "job_id": "555444",
    "graph_immutable_id": "graph-closure-test",
    "conversation_id": "conv-closure-test",
    "tcs_eligibility": "eligible",
    "timeline": [],
    "created_at": datetime.now(timezone.utc).isoformat(),
    "received_at": datetime.now(timezone.utc).isoformat(),
    "thread_messages": [{"id": "msg-cl1"}]
}
engine.save_record_payload(rec_id, payload, "InterviewAwaitingConfirmation")

print("=== STEP 1: BEFORE APPLY DECISION ===")
snapshot_before = engine.get_record_payload_snapshot(rec_id)
print(f"Status before decision: {snapshot_before[2]}")

print("\n=== STEP 2: APPLY OUTCOME DECISION 'Position Closed' ===")
req = OutcomeDecisionRequest(
    record_id=rec_id,
    graph_immutable_id="graph-closure-test",
    conversation_id="conv-closure-test",
    record_version=1,
    outcome_category="Position Closed",
    notes="Testing closure isolation against reclassification"
)
rec_after = post_outcome_decision(rec_id, req, manager_identity="tarun@clifyx.com")

print(f"API Returned Domain Status: {rec_after.domain_status.value}")
print(f"API Returned Closed At: {rec_after.closed_at}")
print(f"API Returned Close Reason: {rec_after.close_reason}")
assert rec_after.domain_status.value == "Closed"

print("\n=== STEP 3: RECLASSIFICATION PASS TEST ===")
snapshot_after = engine.get_record_payload_snapshot(rec_id)
payload_after, ver_after, ds_after = snapshot_after

res_reclass = classify_record(
    "graph-closure-test",
    payload_after.get("thread_messages", []),
    datetime.now(timezone.utc),
    timeline=payload_after.get("timeline", [])
)
print(f"Classifier Proposed Status after decision: {res_reclass.proposed_status}")
print(f"Classifier Category after decision: {res_reclass.category}")
assert res_reclass.proposed_status == "Closed"

print("\n=== STEP 4: REFRESH / DATABASE RELOAD TEST ===")
snapshot_reload = engine.get_record_payload_snapshot(rec_id)
_, _, ds_reload = snapshot_reload
print(f"SQLite Persisted Status after reload: {ds_reload}")
assert ds_reload == "Closed"

dash = engine.get_dashboard_summary()
in_active = [r for r in dash.records if r.id == rec_id and r.domain_status.value in ("PendingFollowUp", "ManagerActionRequired", "InterviewAwaitingConfirmation", "NeedsReview")]
print(f"Record present in Active/Pending/ActionRequired lists: {len(in_active)}")
assert len(in_active) == 0

print("\n✓ ALL RECLASSIFICATION ISOLATION CHECKS PASSED SUCCESSFULLY!")

