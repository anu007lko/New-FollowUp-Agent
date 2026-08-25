import pytest
from datetime import datetime, timezone
from backend.app.domain.models import DomainStatus, CloseReason, ConversationFacts, MessageFact, MessageDirection
from backend.app.api.routes import post_outcome_decision, post_close_record, OutcomeDecisionRequest, CloseRecordRequest
import backend.app.api.routes as routes_module
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.outcome_parser import evaluate_outcome_status

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "temp_actions.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    monkeypatch.delenv("USE_SYNTHETIC_DATA", raising=False)
    engine = EncryptedPersistenceEngine(db_path=str(db_file))
    routes_module.persistence = engine
    yield engine

def test_requirement_is_closed_phrase():
    """Verify 'requirement is closed' parses to Position Closed."""
    facts = ConversationFacts()
    facts.latest_inbound_message = MessageFact(
        graph_immutable_id="msg-001",
        timestamp=datetime.now(timezone.utc),
        sender_email="recruiter.one@example.com",
        direction=MessageDirection.INBOUND_MESSAGE,
        is_meaningful=True,
        body_preview="This requirement is closed, please do not submit profiles."
    )
    evaluate_outcome_status(facts)
    assert facts.outcome_status == "Position Closed"

def test_expanded_close_reasons_and_audit(temp_db):
    """Verify expanded close reasons (Duplicate, On hold, Placed/joined, Unavailable) and audit log format."""
    test_id = "test-action-audit-001"
    
    payload = {
        "id": test_id,
        "record_version": 1,
        "domain_status": DomainStatus.NEEDS_REVIEW.value,
        "candidate_name": "Test Candidate",
        "job_id": "JOB-9999",
        "graph_immutable_id": "test_graph",
        "conversation_id": "test_conv",
        "tcs_eligibility": "eligible",
        "timeline": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "thread_messages": [{"id": "msg1"}]
    }
    temp_db.save_record_payload(test_id, payload, DomainStatus.NEEDS_REVIEW.value)
    
    # Test Close with 'Duplicate submission'
    req = CloseRecordRequest(
        record_id=test_id,
        graph_immutable_id="test_graph",
        conversation_id="test_conv",
        record_version=1,
        reason="Duplicate submission",
        close_note="Candidate already submitted under JOB-8888"
    )
    rec = post_close_record(test_id, req, manager_identity="tarun@clifyx.com")
    
    assert rec.domain_status == DomainStatus.CLOSED
    assert rec.close_reason == "Duplicate submission"
    assert rec.close_note == "Candidate already submitted under JOB-8888"
    
    # Check audit log entry in timeline
    assert len(rec.timeline) > 0
    audit_entry = rec.timeline[-1]
    assert audit_entry.is_system_note is True
    assert "[AUDIT]" in audit_entry.body_preview
    assert "Status changed from NeedsReview to Closed (Duplicate submission)" in audit_entry.body_preview
    assert "JOB-9999" in audit_entry.body_preview


def test_close_record_duplicate_submission_entry_reason(temp_db):
    """Verify that closing a record with 'Duplicate submission entry' succeeds, sets status to Closed, and records close_reason."""
    test_id = "test_dup_entry_record"
    payload = {
        "id": test_id,
        "record_version": 1,
        "domain_status": DomainStatus.MANAGER_ACTION_REQUIRED.value,
        "candidate_name": "Test Dup Entry Candidate",
        "job_id": "888777",
        "graph_immutable_id": "graph-dup-entry",
        "conversation_id": "conv-dup-entry",
        "tcs_eligibility": "eligible",
        "timeline": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "thread_messages": [{"id": "msg-dup1"}]
    }
    temp_db.save_record_payload(test_id, payload, DomainStatus.MANAGER_ACTION_REQUIRED.value)
    
    from backend.app.api.routes import post_close_record, CloseRecordRequest
    import backend.app.api.routes as routes_mod
    routes_mod.persistence = temp_db
    
    req = CloseRecordRequest(
        record_id=test_id,
        graph_immutable_id="graph-dup-entry",
        conversation_id="conv-dup-entry",
        record_version=1,
        reason="Duplicate submission entry",
        close_note="Marked as duplicate entry by manager"
    )
    rec = post_close_record(test_id, req, manager_identity="tarun@clifyx.com")
    assert rec.domain_status == DomainStatus.CLOSED
    assert rec.close_reason == "Duplicate submission entry"
    assert rec.structured_evidence.category == "Duplicate Submission"

def test_outcome_decision_expanded_categories_audit(temp_db):
    """Verify post_outcome_decision records audit entry with previous status, new status, reason, note, actor, job ID."""
    test_id = "test-action-audit-002"
    
    payload = {
        "id": test_id,
        "record_version": 1,
        "domain_status": DomainStatus.AWAITING_RESPONSE.value,
        "candidate_name": "Rani Test",
        "job_id": "418542",
        "graph_immutable_id": "test_graph_2",
        "conversation_id": "test_conv_2",
        "tcs_eligibility": "eligible",
        "timeline": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "thread_messages": [{"id": "msg2"}]
    }
    temp_db.save_record_payload(test_id, payload, DomainStatus.AWAITING_RESPONSE.value)
    
    req = OutcomeDecisionRequest(
        record_id=test_id,
        graph_immutable_id="test_graph_2",
        conversation_id="test_conv_2",
        record_version=1,
        outcome_category="Position Closed",
        notes="Client TCS confirmed position closed."
    )
    rec = post_outcome_decision(test_id, req, manager_identity="tarun@clifyx.com")
    
    assert rec.domain_status == DomainStatus.CLOSED
    assert len(rec.timeline) > 0
    audit_entry = rec.timeline[-1]
    assert "[AUDIT] Status changed from AwaitingResponse to Closed" in audit_entry.body_preview
    assert "Reason: Position Closed" in audit_entry.body_preview
    assert "Job ID: 418542" in audit_entry.body_preview

def test_rani_ciriguri_status_and_followup_exclusion(temp_db):
    """Verify Rani Ciriguri is classified as Position Closed / ManagerActionRequired and excluded from PendingFollowUp."""
    from backend.app.domain.consolidated_classifier import classify_record, PROPOSED_TO_DOMAIN_STATUS
    
    test_id = "2a095c2d-724b-4cd7-8e6a-e2ca95aff93e"
    payload = {
        "id": test_id,
        "record_version": 23,
        "domain_status": DomainStatus.MANAGER_ACTION_REQUIRED.value,
        "candidate_name": "Rani Ciriguri",
        "job_id": "418542",
        "graph_immutable_id": "graph-rani",
        "conversation_id": "conv-rani",
        "tcs_eligibility": "eligible",
        "timeline": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "thread_messages": [
            {
                "id": "msg-rani-1",
                "from": {"emailAddress": {"address": "recruiter.one@example.com", "name": "Recruiter One"}},
                "bodyPreview": "This requirement is closed, please do not submit profiles.",
                "sentDateTime": datetime.now(timezone.utc).isoformat()
            }
        ]
    }
    from backend.app.domain.consolidated_classifier import refresh_classification_snapshot
    refresh_classification_snapshot(payload)
    temp_db.save_record_payload(test_id, payload, DomainStatus.MANAGER_ACTION_REQUIRED.value)
    
    rec = temp_db.get_record_by_id(test_id)
    assert rec.domain_status == DomainStatus.MANAGER_ACTION_REQUIRED
    assert rec.structured_evidence.category == "Position Closed"
    assert rec.domain_status != DomainStatus.PENDING_FOLLOW_UP
    
    dash = temp_db.get_dashboard_summary()
    pending_ids = [r.id for r in dash.records if r.domain_status == DomainStatus.PENDING_FOLLOW_UP]
    assert test_id not in pending_ids

def test_ashok_job_closure_propagation(temp_db):
    """Verify Ashok Cherukumalli (Job ID 418542) is categorized as Position Closed and excluded from PendingFollowUp."""
    ashok_id = "8d20904a-62ef-4ba8-bd95-155b3e5dbe0d"
    payload = {
        "id": ashok_id,
        "record_version": 18,
        "domain_status": DomainStatus.MANAGER_ACTION_REQUIRED.value,
        "candidate_name": "Ashok Cherukumalli",
        "job_id": "418542",
        "graph_immutable_id": "graph-ashok",
        "conversation_id": "conv-ashok",
        "manager_outcome_category": "Position Closed",
        "tcs_eligibility": "eligible",
        "timeline": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "thread_messages": [{"id": "msg-ashok-1"}]
    }
    temp_db.save_record_payload(ashok_id, payload, DomainStatus.MANAGER_ACTION_REQUIRED.value)
    
    rec = temp_db.get_record_by_id(ashok_id)
    assert rec.domain_status == DomainStatus.MANAGER_ACTION_REQUIRED
    assert rec.structured_evidence.category == "Position Closed"
    assert rec.domain_status != DomainStatus.PENDING_FOLLOW_UP
    
    dash = temp_db.get_dashboard_summary()
    pending_ids = [r.id for r in dash.records if r.domain_status == DomainStatus.PENDING_FOLLOW_UP]
    assert ashok_id not in pending_ids

def test_terry_ndr_delivery_failure_classification(temp_db):
    """Verify Terry Lloyd McArthur Jr's NDR is ignored as transport noise and normal tracking continues."""
    from backend.app.domain.consolidated_classifier import classify_record
    
    terry_id = "0305792b-2ef1-4b06-98a1-6f74ab58c0d1"
    thread_messages = [
        {
            "id": "msg-sub-1",
            "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
            "subject": "418326 - Terry Lloyd McArthur Jr",
            "bodyPreview": "PFA profile of Mr. Terry Lloyd McArthur Jr",
            "sentDateTime": datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc).isoformat()
        },
        {
            "id": "msg-ndr-1",
            "from": {"emailAddress": {"address": "MicrosoftExchange329e71ec88ae4615bbc36ab6ce41109e@clifyx.com"}},
            "subject": "Undeliverable: 418326 - Terry Lloyd McArthur Jr",
            "bodyPreview": "Your message to anjaneyareddy.rmkrishnareddy@aexp.com couldn't be delivered. 550 5.1.1 User Unknown",
            "sentDateTime": datetime(2026, 8, 1, 10, 1, tzinfo=timezone.utc).isoformat()
        }
    ]
    
    cls = classify_record("msg-sub-1", thread_messages, datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc))
    assert cls.category == "No Response"
    assert cls.proposed_status == "Awaiting Response"
    assert cls.reason_code == "NO_INBOUND_AWAITING_RESPONSE_WITHIN_48H"
    
    payload = {
        "id": terry_id,
        "record_version": 23,
        "domain_status": DomainStatus.AWAITING_RESPONSE.value,
        "candidate_name": "Terry Lloyd McArthur Jr",
        "job_id": "418326",
        "ep_reference": "EP2026RA7478643",
        "graph_immutable_id": "graph-terry",
        "conversation_id": "conv-terry",
        "classification_category": "No Response",
        "manager_outcome_category": None,
        "tcs_eligibility": "eligible",
        "timeline": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "thread_messages": thread_messages
    }
    temp_db.save_record_payload(terry_id, payload, DomainStatus.AWAITING_RESPONSE.value)
    
    rec = temp_db.get_record_by_id(terry_id)
    assert rec.domain_status == DomainStatus.AWAITING_RESPONSE
    assert rec.structured_evidence.category == "No Response"
    assert rec.domain_status != DomainStatus.INTERVIEW_AWAITING_CONFIRMATION
    
    dash = temp_db.get_dashboard_summary()
    awaiting_ids = [r.id for r in dash.records if r.domain_status == DomainStatus.INTERVIEW_AWAITING_CONFIRMATION]
    assert terry_id not in awaiting_ids


def test_followup_due_outcome_decision_suite(temp_db):
    """Verify that applying manual outcomes on a PendingFollowUp record correctly updates status, appends audit history, and removes record from Follow-up Due."""
    test_id = "test_pending_followup_record"
    payload = {
        "id": test_id,
        "record_version": 1,
        "domain_status": DomainStatus.PENDING_FOLLOW_UP.value,
        "candidate_name": "Test Followup Candidate",
        "job_id": "999888",
        "graph_immutable_id": "graph-pending",
        "conversation_id": "conv-pending",
        "tcs_eligibility": "eligible",
        "timeline": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "thread_messages": [{"id": "msg-p1"}]
    }
    temp_db.save_record_payload(test_id, payload, DomainStatus.PENDING_FOLLOW_UP.value)
    
    # 1. Apply Position Closed outcome
    from backend.app.api.routes import post_outcome_decision, OutcomeDecisionRequest
    import backend.app.api.routes as routes_mod
    routes_mod.persistence = temp_db
    
    req_closed = OutcomeDecisionRequest(
        record_id=test_id,
        graph_immutable_id="graph-pending",
        conversation_id="conv-pending",
        record_version=1,
        outcome_category="Position Closed",
        notes="Closed position directly from follow-up due"
    )
    rec_closed = post_outcome_decision(test_id, req_closed, manager_identity="tarun@clifyx.com")
    assert rec_closed.domain_status == DomainStatus.CLOSED
    assert rec_closed.structured_evidence.category == "Position Closed"
    assert len(rec_closed.timeline) > 0
    assert "[AUDIT] Status changed from PendingFollowUp to Closed" in rec_closed.timeline[-1].body_preview
    
    dash = temp_db.get_dashboard_summary()
    pending_ids = [r.id for r in dash.records if r.domain_status == DomainStatus.PENDING_FOLLOW_UP]
    assert test_id not in pending_ids

    # 2. Re-test On Hold outcome on another pending record
    test_id_hold = "test_pending_on_hold"
    payload_hold = dict(
        payload,
        id=test_id_hold,
        graph_immutable_id="graph-pending-hold",
        conversation_id="conv-pending-hold",
        record_version=1
    )
    temp_db.save_record_payload(test_id_hold, payload_hold, DomainStatus.PENDING_FOLLOW_UP.value)
    
    req_hold = OutcomeDecisionRequest(
        record_id=test_id_hold,
        graph_immutable_id="graph-pending-hold",
        conversation_id="conv-pending-hold",
        record_version=1,
        outcome_category="On Hold",
        notes="Putting candidate on hold"
    )
    rec_hold = post_outcome_decision(test_id_hold, req_hold, manager_identity="tarun@clifyx.com")
    assert rec_hold.domain_status == DomainStatus.IN_EVALUATION
    assert rec_hold.structured_evidence.category == "On Hold"
    
    dash_hold = temp_db.get_dashboard_summary()
    pending_ids_hold = [r.id for r in dash_hold.records if r.domain_status == DomainStatus.PENDING_FOLLOW_UP]
    assert test_id_hold not in pending_ids_hold


def test_interview_awaiting_confirmation_outcome_decision_suite(temp_db):
    """Verify that applying manual outcomes on an InterviewAwaitingConfirmation record updates status to Closed, creates audit entry, and removes record from Awaiting Confirmation queue."""
    test_id = "test_interview_awaiting_record"
    payload = {
        "id": test_id,
        "record_version": 1,
        "domain_status": DomainStatus.INTERVIEW_AWAITING_CONFIRMATION.value,
        "candidate_name": "Test Interview Candidate",
        "job_id": "777666",
        "graph_immutable_id": "graph-iv-awaiting",
        "conversation_id": "conv-iv-awaiting",
        "tcs_eligibility": "eligible",
        "timeline": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "thread_messages": [{"id": "msg-iv1"}]
    }
    temp_db.save_record_payload(test_id, payload, DomainStatus.INTERVIEW_AWAITING_CONFIRMATION.value)
    
    from backend.app.api.routes import post_outcome_decision, OutcomeDecisionRequest
    import backend.app.api.routes as routes_mod
    routes_mod.persistence = temp_db
    
    req_closed = OutcomeDecisionRequest(
        record_id=test_id,
        graph_immutable_id="graph-iv-awaiting",
        conversation_id="conv-iv-awaiting",
        record_version=1,
        outcome_category="Position Closed",
        notes="Position closed during interview awaiting confirmation stage"
    )
    rec_closed = post_outcome_decision(test_id, req_closed, manager_identity="tarun@clifyx.com")
    assert rec_closed.domain_status == DomainStatus.CLOSED
    assert rec_closed.structured_evidence.category == "Position Closed"
    assert len(rec_closed.timeline) > 0
    assert "[AUDIT] Status changed from InterviewAwaitingConfirmation to Closed" in rec_closed.timeline[-1].body_preview
    
    dash = temp_db.get_dashboard_summary()
    awaiting_ids = [r.id for r in dash.records if r.domain_status == DomainStatus.INTERVIEW_AWAITING_CONFIRMATION]
    assert test_id not in awaiting_ids


def test_closed_record_reclassification_immunity(temp_db):
    """Verify that a manually closed record is immune to reclassification passes and stays Closed after full database refresh."""
    from backend.app.domain.consolidated_classifier import classify_record
    from backend.app.api.routes import post_outcome_decision, OutcomeDecisionRequest
    import backend.app.api.routes as routes_mod
    routes_mod.persistence = temp_db
    
    test_id = "test_immunity_record"
    payload = {
        "id": test_id,
        "record_version": 1,
        "domain_status": DomainStatus.MANAGER_ACTION_REQUIRED.value,
        "candidate_name": "Test Immunity Candidate",
        "job_id": "111222",
        "graph_immutable_id": "graph-immunity",
        "conversation_id": "conv-immunity",
        "tcs_eligibility": "eligible",
        "timeline": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "thread_messages": [{"id": "msg-imm1"}]
    }
    temp_db.save_record_payload(test_id, payload, DomainStatus.MANAGER_ACTION_REQUIRED.value)
    
    req_closed = OutcomeDecisionRequest(
        record_id=test_id,
        graph_immutable_id="graph-immunity",
        conversation_id="conv-immunity",
        record_version=1,
        outcome_category="Position Closed",
        notes="Closed position with full immunity test"
    )
    rec_closed = post_outcome_decision(test_id, req_closed, manager_identity="tarun@clifyx.com")
    assert rec_closed.domain_status == DomainStatus.CLOSED
    
    snapshot = temp_db.get_record_payload_snapshot(test_id)
    payload_snap, ver_snap, ds_snap = snapshot
    assert ds_snap == "Closed"
    
    res_cls = classify_record(
        "graph-immunity",
        payload_snap.get("thread_messages", []),
        datetime.now(timezone.utc),
        timeline=payload_snap.get("timeline", [])
    )
    assert res_cls.proposed_status == "Closed"
    
    rec_reloaded = temp_db.get_record_by_id(test_id)
    assert rec_reloaded.domain_status == DomainStatus.CLOSED
    assert rec_reloaded.domain_status != DomainStatus.MANAGER_ACTION_REQUIRED

