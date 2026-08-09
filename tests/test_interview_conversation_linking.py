import os
import json
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.domain.models import DomainStatus, InterviewState
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.application.workflow_engine import select_record_reply_context
from backend.app.api.routes import security_service

client = TestClient(app)
CSRF_HEADERS = {"x-csrf-token": security_service.generate_csrf_token()}

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Create a temporary isolated encrypted database for linking testing."""
    db_file = tmp_path / "temp_records.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    monkeypatch.delenv("USE_SYNTHETIC_DATA", raising=False)
    
    import backend.app.api.routes as routes_module
    old_persistence = routes_module.persistence

    engine = EncryptedPersistenceEngine(db_path=str(db_file))
    routes_module.persistence = engine
    
    record_id = "test-rec-linking-01"
    graph_id = "AAMkAGTest123"
    conv_id = "AAQkAGConvOrig123"
    
    payload = {
        "id": record_id,
        "graph_immutable_id": graph_id,
        "conversation_id": conv_id,
        "candidate_name": "Alice Candidate",
        "job_id": "JOB123",
        "ep_reference": "EP456",
        "tcs_eligibility": "eligible",
        "record_version": 1,
        "thread_messages": [
            {
                "id": graph_id,
                "conversationId": conv_id,
                "from": {"emailAddress": {"address": "vendor@agency.com"}},
                "sentDateTime": "2026-08-01T10:00:00Z",
                "bodyPreview": "Submitted candidate Alice Candidate for JOB123",
                "subject": "Candidate Submission: Alice Candidate - JOB123"
            }
        ],
        "interview_suggestions": [
            {
                "suggestion_id": "sugg_1",
                "record_id": record_id,
                "conversation_id": "AAQkAGConvInterviewSeparate",
                "candidate_name": "Alice Candidate",
                "job_id": "JOB123",
                "interview_subject": "Interview Scheduled: Alice Candidate",
                "interview_received_at": "2026-08-02T14:00:00Z",
                "latest_interview_message_excerpt": "Interview scheduled for Aug 3, 2026 at 2:00 PM EST.",
                "latest_interview_message_sender": "client@company.com",
                "thread_messages": [
                    {
                        "id": "imm_int_1",
                        "conversationId": "AAQkAGConvInterviewSeparate",
                        "from": {"emailAddress": {"address": "client@company.com"}},
                        "sentDateTime": "2026-08-02T14:00:00Z",
                        "bodyPreview": "Interview scheduled for Alice Candidate on Aug 3 at 2:00 PM EST.",
                        "subject": "Interview Scheduled: Alice Candidate"
                    }
                ]
            }
        ],
        "linked_conversations": []
    }
    
    engine.save_record_payload(record_id, payload, DomainStatus.PENDING_FOLLOW_UP.value)
    
    yield engine
    
    routes_module.persistence = old_persistence


def test_suggestion_does_not_automatically_link(temp_db):
    """Suggestions from metadata review must never automatically link or mutate status."""
    rec = temp_db.get_record_by_id("test-rec-linking-01")
    assert rec is not None
    assert rec.domain_status == DomainStatus.PENDING_FOLLOW_UP
    assert len(rec.linked_conversations) == 0
    assert len(rec.interview_suggestions) == 1


def test_link_and_unlink_interview_conversation(temp_db):
    """Manager explicitly links separate interview conversation, updating classification, then unlinks."""
    headers = CSRF_HEADERS

    # 1. Manager confirms linking
    link_req = {
        "record_id": "test-rec-linking-01",
        "graph_immutable_id": "AAMkAGTest123",
        "conversation_id": "AAQkAGConvOrig123",
        "record_version": 1,
        "linked_conversation_id": "AAQkAGConvInterviewSeparate",
        "interview_subject": "Interview Scheduled: Alice Candidate",
        "interview_received_at": "2026-08-02T14:00:00Z"
    }
    res = client.post("/api/v1/records/test-rec-linking-01/link-interview", json=link_req, headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["record_version"] == 2
    assert len(data["linked_conversations"]) == 1
    assert data["linked_conversations"][0]["conversation_id"] == "AAQkAGConvInterviewSeparate"
    assert data["domain_status"] == DomainStatus.INTERVIEW_AWAITING_CONFIRMATION.value

    # Interview workflow targets the latest real message in the explicitly linked thread.
    rec = temp_db.get_record_by_id("test-rec-linking-01")
    anchor, target_conversation = select_record_reply_context(rec)
    assert anchor is not None
    assert target_conversation == "AAQkAGConvInterviewSeparate"
    assert anchor.conversation_id == "AAQkAGConvInterviewSeparate"
    assert anchor.graph_immutable_id == "imm_int_1"

    # A first/no-response follow-up remains bound to the immutable original submission.
    rec.domain_status = DomainStatus.PENDING_FOLLOW_UP
    original_anchor, original_conversation = select_record_reply_context(rec)
    assert original_anchor is not None
    assert original_conversation == "AAQkAGConvOrig123"
    assert original_anchor.graph_immutable_id == "AAMkAGTest123"

    # After the interview, feedback follow-up returns to the original submission
    # chain even though the separate interview conversation remains linked.
    rec.domain_status = DomainStatus.FEEDBACK_DUE
    feedback_anchor, feedback_conversation = select_record_reply_context(rec)
    assert feedback_anchor is not None
    assert feedback_conversation == "AAQkAGConvOrig123"
    assert feedback_anchor.conversation_id == "AAQkAGConvOrig123"

    # 2. Test optimistic concurrency on stale version
    stale_unlink_req = {
        "record_id": "test-rec-linking-01",
        "graph_immutable_id": "AAMkAGTest123",
        "conversation_id": "AAQkAGConvOrig123",
        "record_version": 1,  # Stale! Current is 2
        "linked_conversation_id": "AAQkAGConvInterviewSeparate"
    }
    res_stale = client.post("/api/v1/records/test-rec-linking-01/unlink-interview", json=stale_unlink_req, headers=headers)
    assert res_stale.status_code == 409

    # 3. Manager confirms unlinking with correct version
    unlink_req = {
        "record_id": "test-rec-linking-01",
        "graph_immutable_id": "AAMkAGTest123",
        "conversation_id": "AAQkAGConvOrig123",
        "record_version": 2,
        "linked_conversation_id": "AAQkAGConvInterviewSeparate"
    }
    res_unlink = client.post("/api/v1/records/test-rec-linking-01/unlink-interview", json=unlink_req, headers=headers)
    assert res_unlink.status_code == 200, res_unlink.text
    data_unlinked = res_unlink.json()
    assert data_unlinked["record_version"] == 3
    assert len(data_unlinked["linked_conversations"]) == 0
    assert data_unlinked["domain_status"] == DomainStatus.PENDING_FOLLOW_UP.value
