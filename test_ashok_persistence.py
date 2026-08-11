import sys, os
from datetime import datetime, timezone
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.api.routes import post_outcome_decision, OutcomeDecisionRequest
import backend.app.api.routes as routes_mod
from backend.app.domain.models import DomainStatus

engine = EncryptedPersistenceEngine()
routes_mod.persistence = engine

ashok_id = "8d20904a-62ef-4ba8-bd95-155b3e5dbe0d"
snapshot = engine.get_record_payload_snapshot(ashok_id)
payload, version, current_status = snapshot

print(f"Before Apply Decision: Status = {current_status}")

req = OutcomeDecisionRequest(
    record_id=ashok_id,
    graph_immutable_id=payload.get("graph_immutable_id", "graph-ashok"),
    conversation_id=payload.get("conversation_id", "conv-ashok"),
    record_version=version,
    outcome_category="Position Closed",
    notes="Confirmed position closed by client"
)

rec = post_outcome_decision(ashok_id, req, manager_identity="tarun@clifyx.com")

print(f"After Apply Decision: Status = {rec.domain_status.value}")
print(f"Structured Evidence Category = {rec.structured_evidence.category if rec.structured_evidence else None}")
print(f"Structured Evidence Workflow Status = {rec.structured_evidence.workflow_status if rec.structured_evidence else None}")

dash = engine.get_dashboard_summary()
ashok_in_dash = [r for r in dash.records if r.id == ashok_id]
print(f"Ashok in Dashboard records: {len(ashok_in_dash)} found (Domain status: {ashok_in_dash[0].domain_status.value if ashok_in_dash else 'None'})")

