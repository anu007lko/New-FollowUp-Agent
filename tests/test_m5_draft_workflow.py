"""
M5 Synthetic Draft Workflow Tests.

Tests:
1. Reply anchor selection (latest real mailbox message with immutable Graph ID, never metadata/system notes).
2. Reply All recipient computation (preserves To/CC, excludes self tarun@clifyx.com, honors replyTo, BCC empty).
3. Strict BCC validation (case/whitespace normalization, strictly requires @clifyx.com, rejects external/malformed).
4. Stage 1 Approval Hashing & Invalidation (SHA-256 hash, any edit invalidates approval).
5. Stage 2 Draft Creation (requires valid approval hash, simulates createReplyAll, idempotency protection).
6. Zero send invariants (no send surface, no auto-drafts in daily review engine).
"""

import pytest
import hashlib
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.domain.models import (
    TimelineEntry, DomainStatus, DraftApprovalRequest, DraftCreateRequest
)
from backend.app.application.workflow_engine import (
    select_reply_anchor_message, compute_reply_all_recipients,
    validate_bcc_list, compute_draft_approval_hash,
    validate_draft_operation_match, create_and_store_approval, get_draft_operation
)
from backend.app.infrastructure.fake_graph_adapter import FakeGraphDraftAdapter
from backend.app.infrastructure.synthetic_data import get_synthetic_record_by_id, get_synthetic_records
from backend.app.application.daily_review_engine import DailyReviewEngine
from backend.app.api.routes import security_service

client = TestClient(app)
client.headers.update({"x-csrf-token": security_service.generate_csrf_token()})


# --- 1. Reply Anchor Selection Tests ---

class TestReplyAnchorSelection:
    def test_selects_latest_real_mailbox_message_with_immutable_id(self):
        timeline = [
            TimelineEntry(
                entry_id="e1", record_id="r1", sender="tarun@clifyx.com",
                timestamp="2026-07-20T10:00:00Z", body_preview="Submission email",
                graph_immutable_id="immutable-msg-001"
            ),
            TimelineEntry(
                entry_id="e2", record_id="r1", sender="recruiter@tcs.com",
                timestamp="2026-07-21T11:00:00Z", body_preview="Interview scheduled",
                graph_immutable_id="immutable-msg-002"
            ),
            TimelineEntry(
                entry_id="e3", record_id="r1", sender="system",
                timestamp="2026-07-22T09:00:00Z", body_preview="Status changed to In Evaluation",
                is_system_note=True, graph_immutable_id=None
            )
        ]
        anchor = select_reply_anchor_message(timeline)
        assert anchor is not None
        assert anchor.entry_id == "e2"
        assert anchor.graph_immutable_id == "immutable-msg-002"
        assert anchor.sender == "recruiter@tcs.com"

    def test_never_selects_system_notes_or_manager_actions(self):
        timeline = [
            TimelineEntry(
                entry_id="e1", record_id="r1", sender="tarun@clifyx.com",
                timestamp="2026-07-20T10:00:00Z", body_preview="Submission email",
                graph_immutable_id="immutable-msg-001"
            ),
            TimelineEntry(
                entry_id="e2", record_id="r1", sender="Manager Action Required",
                timestamp="2026-07-21T11:00:00Z", body_preview="Manual confirmation",
                is_system_note=True, graph_immutable_id="fake-id"
            ),
            TimelineEntry(
                entry_id="e3", record_id="r1", sender="System Note: Internal timer",
                timestamp="2026-07-22T09:00:00Z", body_preview="48h timer expired",
                is_system_note=True, graph_immutable_id=None
            )
        ]
        anchor = select_reply_anchor_message(timeline)
        assert anchor is not None
        assert anchor.entry_id == "e1"
        assert anchor.sender == "tarun@clifyx.com"

    def test_single_outgoing_submission_uses_sent_message_as_anchor(self):
        timeline = [
            TimelineEntry(
                entry_id="e1", record_id="r1", sender="tarun@clifyx.com",
                timestamp="2026-07-20T10:00:00Z", body_preview="Initial submission",
                graph_immutable_id="immutable-sub-001",
                to_recipients=["recruiter@tcs.com"]
            )
        ]
        anchor = select_reply_anchor_message(timeline)
        assert anchor is not None
        assert anchor.entry_id == "e1"
        assert anchor.graph_immutable_id == "immutable-sub-001"


# --- 2. Reply All Recipient Computation Tests ---

class TestReplyAllRecipients:
    def test_preserves_to_and_cc_and_excludes_self(self):
        source = TimelineEntry(
            entry_id="msg-1", record_id="r1", sender="recruiter@tcs.com",
            timestamp="2026-07-20T10:00:00Z", body_preview="Interview scheduled",
            graph_immutable_id="imm-1",
            to_recipients=["tarun@clifyx.com", "lead@tcs.com"],
            cc_recipients=["coordinator@tcs.com", "tarun@clifyx.com", "hr@tcs.com"]
        )
        to_list, cc_list, bcc_list, reply_to = compute_reply_all_recipients(source)
        # To should contain sender (recruiter@tcs.com) + other To recipients (lead@tcs.com), excluding tarun@clifyx.com
        assert to_list == ["recruiter@tcs.com", "lead@tcs.com"]
        # CC should contain coordinator@tcs.com and hr@tcs.com, excluding tarun@clifyx.com
        assert cc_list == ["coordinator@tcs.com", "hr@tcs.com"]
        # BCC must start strictly empty
        assert bcc_list == []
        assert reply_to is None

    def test_honors_reply_to_header_when_present(self):
        source = TimelineEntry(
            entry_id="msg-2", record_id="r1", sender="recruiting-noreply@tcs.com",
            timestamp="2026-07-20T10:00:00Z", body_preview="Interview details",
            graph_immutable_id="imm-2",
            reply_to="recruiter-direct@tcs.com",
            to_recipients=["tarun@clifyx.com"],
            cc_recipients=["manager@tcs.com"]
        )
        to_list, cc_list, bcc_list, reply_to = compute_reply_all_recipients(source)
        assert to_list == ["recruiter-direct@tcs.com"]
        assert cc_list == ["manager@tcs.com"]
        assert bcc_list == []
        assert reply_to == "recruiter-direct@tcs.com"

    def test_self_submission_anchor_replies_to_original_recipients(self):
        source = TimelineEntry(
            entry_id="msg-sub", record_id="r1", sender="tarun@clifyx.com",
            timestamp="2026-07-20T10:00:00Z", body_preview="Candidate Submission",
            graph_immutable_id="imm-sub",
            to_recipients=["recruiter@tcs.com", "tarun@clifyx.com"],
            cc_recipients=["team@tcs.com"]
        )
        to_list, cc_list, bcc_list, reply_to = compute_reply_all_recipients(source)
        assert to_list == ["recruiter@tcs.com"]
        assert cc_list == ["team@tcs.com"]
        assert bcc_list == []


# --- 3. Strict BCC Validation Tests ---

class TestBccValidation:
    def test_accepts_valid_clifyx_addresses_and_normalizes(self):
        input_bcc = ["  tarun@clifyx.com  ", "SUPPORT@CLIFYX.COM", "lead.dev@clifyx.com"]
        is_valid, normalized, err = validate_bcc_list(input_bcc)
        assert is_valid is True
        assert err is None
        assert normalized == ["tarun@clifyx.com", "support@clifyx.com", "lead.dev@clifyx.com"]

    def test_rejects_external_domains(self):
        external_bcc = ["colleague@clifyx.com", "recruiter@tcs.com"]
        is_valid, normalized, err = validate_bcc_list(external_bcc)
        assert is_valid is False
        assert "must end exactly in @clifyx.com" in err

    def test_rejects_gmail_and_other_providers(self):
        external_bcc = ["personal@gmail.com"]
        is_valid, normalized, err = validate_bcc_list(external_bcc)
        assert is_valid is False
        assert "must end exactly in @clifyx.com" in err

    def test_rejects_malformed_email_strings(self):
        malformed_bcc = ["not-an-email", "system note", "tarun@clifyx.com"]
        is_valid, normalized, err = validate_bcc_list(malformed_bcc)
        assert is_valid is False
        assert "not a valid email address" in err

    def test_empty_bcc_list_is_valid(self):
        is_valid, normalized, err = validate_bcc_list([])
        assert is_valid is True
        assert normalized == []
        assert err is None


# --- 4. Stage 1 Approval Hashing & Invalidation Tests ---

class TestApprovalHashing:
    def test_deterministic_hash_generation(self):
        content = "Hi, following up on the candidate submission."
        to = ["recruiter@tcs.com"]
        cc = ["team@tcs.com"]
        bcc = ["manager@clifyx.com"]

        hash1 = compute_draft_approval_hash("rec-1", "conv-1", "msg-1", content, to, cc, bcc)
        hash2 = compute_draft_approval_hash("rec-1", "conv-1", "msg-1", content, to, cc, bcc)
        assert hash1 == hash2
        assert len(hash1) == 64

    def test_content_modification_invalidates_approval(self):
        content_orig = "Hi, following up on the candidate submission."
        content_mod = "Hi, following up on the candidate submission. Please reply ASAP."
        to = ["recruiter@tcs.com"]
        cc = []
        bcc = []

        from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
        engine = EncryptedPersistenceEngine()
        appr = create_and_store_approval("rec-hash-test", "conv-hash", "msg-hash", to, cc, bcc, content_orig, 1, engine)
        
        # Validating original matches
        is_valid, msg = validate_draft_operation_match(appr, "conv-hash", "msg-hash", appr.approval_hash, content_orig, to, cc, bcc)
        assert is_valid is True

        # Validating modified fails closed
        is_valid_mod, msg_mod = validate_draft_operation_match(appr, "conv-hash", "msg-hash", appr.approval_hash, content_mod, to, cc, bcc)
        assert is_valid_mod is False

    def test_bcc_addition_invalidates_approval(self):
        content = "Hi, following up on the candidate submission."
        to = ["recruiter@tcs.com"]
        cc = []
        bcc_orig = []
        bcc_new = ["extra@clifyx.com"]

        from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
        engine = EncryptedPersistenceEngine()
        appr = create_and_store_approval("rec-bcc-test", "conv-bcc", "msg-bcc", to, cc, bcc_orig, content, 1, engine)

        is_valid, msg = validate_draft_operation_match(appr, "conv-bcc", "msg-bcc", appr.approval_hash, content, to, cc, bcc_new)
        assert is_valid is False



# --- 5. Stage 2 Draft Creation & Fake Graph Adapter Tests ---

class TestFakeGraphDraftAdapter:
    def test_create_reply_all_draft_success(self):
        adapter = FakeGraphDraftAdapter()
        res, was_new = adapter.create_reply_all_draft(
            record_id="rec-001",
            conversation_id="conv-001",
            source_message_id="msg-imm-001",
            content="Follow up text",
            to_recipients=["recruiter@tcs.com"],
            cc_recipients=["lead@tcs.com"],
            bcc_recipients=["audit@clifyx.com"],
            approval_hash="a1b2c3d4e5",
            idempotency_key="idemp-key-101"
        )
        assert was_new is True
        assert res.draft_id.startswith("draft-syn-")
        assert res.status == "created"
        assert res.message == "Draft created—not sent. Review and send in Outlook."
        assert res.is_synthetic is True
        assert res.source_message_id == "msg-imm-001"

    def test_idempotency_duplicate_protection(self):
        adapter = FakeGraphDraftAdapter()
        res1, was_new1 = adapter.create_reply_all_draft(
            record_id="rec-001",
            conversation_id="conv-001",
            source_message_id="msg-imm-001",
            content="Follow up text",
            to_recipients=["recruiter@tcs.com"],
            cc_recipients=[],
            bcc_recipients=[],
            approval_hash="hash1",
            idempotency_key="idemp-duplicate-test"
        )
        assert was_new1 is True
        assert res1.status == "created"

        # Second call with same idempotency key (simulating double click / retry)
        res2, was_new2 = adapter.create_reply_all_draft(
            record_id="rec-001",
            conversation_id="conv-001",
            source_message_id="msg-imm-001",
            content="Follow up text",
            to_recipients=["recruiter@tcs.com"],
            cc_recipients=[],
            bcc_recipients=[],
            approval_hash="hash1",
            idempotency_key="idemp-duplicate-test"
        )
        assert was_new2 is False
        assert res2.status == "reconciled_existing"
        assert res2.draft_id == res1.draft_id


# --- 6. End-to-End API Routes & Integrity Tests ---

class TestDraftWorkflowEndpoints:
    def test_get_draft_preview_endpoint(self):
        res = client.get("/api/v1/records/syn-rec-001/draft-preview")
        assert res.status_code == 200
        data = res.json()
        assert data["record_id"] == "syn-rec-001"
        assert data["conversation_id"] == "AAQkSynthConv001"
        assert "recruiter@tcs.com" in data["to"]
        assert "tarun@clifyx.com" not in data["to"]
        assert "tarun@clifyx.com" not in data["cc"]
        assert data["bcc"] == []
        assert data["source_message_id"] is not None

    def test_stage1_approve_and_stage2_create_flow(self):
        # 1. Preview
        preview_res = client.get("/api/v1/records/syn-rec-001/draft-preview")
        assert preview_res.status_code == 200
        preview = preview_res.json()

        # 2. Stage 1: Approve
        approve_payload = {
            "record_id": "syn-rec-001",
            "content": "Hi recruiter, following up on candidate progress.",
            "to": preview["to"],
            "cc": preview["cc"],
            "bcc": ["manager@clifyx.com"]
        }
        appr_res = client.post("/api/v1/records/syn-rec-001/draft-approve", json=approve_payload)
        assert appr_res.status_code == 200
        appr_data = appr_res.json()
        assert appr_data["is_approved"] is True
        approval_hash = appr_data["approval_hash"]
        idempotency_key = appr_data["idempotency_key"]
        assert approval_hash is not None
        assert idempotency_key.startswith("idemp-")

        # 3. Stage 2: Create Draft using server-generated idempotency key
        create_payload = {
            "record_id": "syn-rec-001",
            "content": "Hi recruiter, following up on candidate progress.",
            "to": preview["to"],
            "cc": preview["cc"],
            "bcc": ["manager@clifyx.com"],
            "approval_hash": approval_hash,
            "idempotency_key": idempotency_key
        }
        create_res = client.post("/api/v1/records/syn-rec-001/draft-create", json=create_payload)
        assert create_res.status_code == 200
        create_data = create_res.json()
        assert create_data["draft_id"].startswith("draft-syn-")
        assert create_data["message"] == "Draft created—not sent. Review and send in Outlook."
        assert create_data["status"] == "created"

    def test_reject_forged_client_to_cc(self):
        # 1. Approve normally
        preview = client.get("/api/v1/records/syn-rec-001/draft-preview").json()
        appr_payload = {
            "record_id": "syn-rec-001",
            "content": "Valid content for test",
            "bcc": []
        }
        appr_data = client.post("/api/v1/records/syn-rec-001/draft-approve", json=appr_payload).json()
        hash_val = appr_data["approval_hash"]
        idemp_val = appr_data["idempotency_key"]

        # 2. Attempt Stage 2 with forged client To recipient
        forged_payload = {
            "record_id": "syn-rec-001",
            "content": "Valid content for test",
            "to": ["hacker@external.com"],
            "cc": preview["cc"],
            "bcc": [],
            "approval_hash": hash_val,
            "idempotency_key": idemp_val
        }
        res = client.post("/api/v1/records/syn-rec-001/draft-create", json=forged_payload)
        assert res.status_code == 400
        assert "do not match server-authoritative" in res.json()["detail"]

    def test_reject_forged_conversation_or_source_id(self):
        appr_data = client.post("/api/v1/records/syn-rec-001/draft-approve", json={
            "record_id": "syn-rec-001", "content": "Sample email content", "bcc": []
        }).json()
        hash_val = appr_data["approval_hash"]
        idemp_val = appr_data["idempotency_key"]

        forged_conv = {
            "record_id": "syn-rec-001",
            "content": "Sample email content",
            "conversation_id": "FORGED_CONVERSATION_ID",
            "approval_hash": hash_val,
            "idempotency_key": idemp_val
        }
        res = client.post("/api/v1/records/syn-rec-001/draft-create", json=forged_conv)
        assert res.status_code == 400
        assert "does not match server record identity" in res.json()["detail"]

    def test_prevent_approval_replay_across_records(self):
        # Approve on syn-rec-001
        appr_rec1 = client.post("/api/v1/records/syn-rec-001/draft-approve", json={
            "record_id": "syn-rec-001", "content": "Cross-record replay content", "bcc": []
        }).json()
        hash1 = appr_rec1["approval_hash"]
        idemp1 = appr_rec1["idempotency_key"]

        # Attempt to use hash1 on syn-rec-002
        replay_payload = {
            "record_id": "syn-rec-002",
            "content": "Cross-record replay content",
            "bcc": [],
            "approval_hash": hash1,
            "idempotency_key": idemp1
        }
        res = client.post("/api/v1/records/syn-rec-002/draft-create", json=replay_payload)
        assert res.status_code == 400
        assert "Conversation ID has changed" in res.json()["detail"] or "mismatch" in res.json()["detail"]

    def test_newer_reply_anchor_invalidates_approval(self):
        record = get_synthetic_record_by_id("syn-rec-001")
        # Approve
        appr_data = client.post("/api/v1/records/syn-rec-001/draft-approve", json={
            "record_id": "syn-rec-001", "content": "Anchor test text", "bcc": []
        }).json()

        # Simulate arrival of a newer real mailbox message in timeline
        new_msg = TimelineEntry(
            entry_id="new-msg-999",
            record_id="syn-rec-001",
            sender="recruiter@tcs.com",
            timestamp="2026-08-03T10:00:00Z",
            body_preview="Newer update email",
            graph_immutable_id="immutable-new-999"
        )
        record.timeline.append(new_msg)

        # Attempt Stage 2 creation
        create_res = client.post("/api/v1/records/syn-rec-001/draft-create", json={
            "record_id": "syn-rec-001",
            "content": "Anchor test text",
            "bcc": [],
            "approval_hash": appr_data["approval_hash"],
            "idempotency_key": appr_data["idempotency_key"]
        })
        assert create_res.status_code == 400
        assert "Source message (reply anchor) has changed" in create_res.json()["detail"] or "invalidated" in create_res.json()["detail"]

    def test_stable_idempotency_key_and_reconciliation(self):
        # 1. Approve
        appr_data = client.post("/api/v1/records/syn-rec-002/draft-approve", json={
            "record_id": "syn-rec-002", "content": "Idempotency test content", "bcc": []
        }).json()
        idemp_key = appr_data["idempotency_key"]

        # 2. Stage 2 Create (Initial)
        res1 = client.post("/api/v1/records/syn-rec-002/draft-create", json={
            "record_id": "syn-rec-002",
            "content": "Idempotency test content",
            "bcc": [],
            "approval_hash": appr_data["approval_hash"],
            "idempotency_key": idemp_key
        })
        assert res1.status_code == 200
        d1 = res1.json()
        assert d1["status"] == "created"

        # 3. Stage 2 Create (Retry / Double-click with same key)
        res2 = client.post("/api/v1/records/syn-rec-002/draft-create", json={
            "record_id": "syn-rec-002",
            "content": "Idempotency test content",
            "bcc": [],
            "approval_hash": appr_data["approval_hash"],
            "idempotency_key": idemp_key
        })
        assert res2.status_code == 200
        d2 = res2.json()
        assert d2["status"] == "reconciled_existing"
        assert d2["draft_id"] == d1["draft_id"]


# --- 7. Zero Send & Daily Review Isolation Tests ---

class TestZeroSendInvariants:
    def test_zero_send_methods_on_graph_adapters(self):
        adapter = FakeGraphDraftAdapter()
        # Verify no send methods exist on fake adapter
        for attr in ["send", "send_mail", "send_message", "send_draft"]:
            assert not hasattr(adapter, attr), f"Found prohibited send attribute: {attr}"

    @patch(
        "backend.app.api.routes.daily_review_engine.import_service.graph_client.fetch_submissions_folder_messages",
        return_value=([], "test", {}),
    )
    def test_daily_review_does_not_create_drafts(self, mock_fetch):
        adapter = FakeGraphDraftAdapter()
        # Ensure fake adapter draft store is empty before review
        assert len(adapter._drafts_by_id) == 0
        # Trigger review endpoint
        res = client.post("/api/v1/daily-review/run")
        assert res.status_code == 200
        # Ensure no drafts were created by daily review
        assert len(adapter._drafts_by_id) == 0

