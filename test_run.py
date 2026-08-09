from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

preview_res = client.get("/api/v1/records/syn-rec-001/draft-preview")
preview = preview_res.json()
print("Preview:", preview)

approve_payload = {
    "record_id": "syn-rec-001",
    "content": "Hi recruiter, following up on candidate progress.",
    "to": preview["to"],
    "cc": preview["cc"],
    "bcc": ["manager@clifyx.com"]
}
appr_res = client.post("/api/v1/records/syn-rec-001/draft-approve", json=approve_payload)
appr_data = appr_res.json()
print("Approve:", appr_data)

create_payload = {
    "record_id": "syn-rec-001",
    "content": "Hi recruiter, following up on candidate progress.",
    "to": preview["to"],
    "cc": preview["cc"],
    "bcc": ["manager@clifyx.com"],
    "approval_hash": appr_data["approval_hash"],
    "idempotency_key": appr_data["idempotency_key"]
}
create_res = client.post("/api/v1/records/syn-rec-001/draft-create", json=create_payload)
print("Create:", create_res.status_code, create_res.text)
