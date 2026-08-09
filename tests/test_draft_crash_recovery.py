"""Crash/restart invariants for Outlook draft creation.  No real network calls."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.app.application.workflow_engine import create_and_store_approval, validate_draft_operation_match
from backend.app.domain.models import DraftOperationState
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine


def make_operation(tmp_path):
    engine = EncryptedPersistenceEngine(str(tmp_path / "records.db"), master_key="isolated-draft-test-key")
    op = create_and_store_approval(
        record_id="record-1", conversation_id="conversation-1", immutable_anchor_id="immutable-1",
        canonical_to=["recruiter@tcs.com"], canonical_cc=[], normalized_bcc=["manager@clifyx.com"],
        content="Approved body", record_version=7, engine=engine,
    )
    return engine, op


def test_compare_and_set_allows_only_one_creator(tmp_path):
    engine, op = make_operation(tmp_path)
    barrier = threading.Barrier(2)

    def contend():
        barrier.wait()
        return engine.compare_and_set_draft_operation(
            op.idempotency_key, [DraftOperationState.APPROVED], DraftOperationState.CREATING
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: contend(), range(2)))
    assert sorted(results) == [False, True]


def test_failed_reconcilable_is_never_valid_for_create(tmp_path):
    engine, op = make_operation(tmp_path)
    assert engine.compare_and_set_draft_operation(
        op.idempotency_key, [DraftOperationState.APPROVED], DraftOperationState.FAILED_RECONCILABLE
    )
    failed = engine.get_draft_operation(op.idempotency_key)
    valid, reason = validate_draft_operation_match(
        failed, "conversation-1", "immutable-1", op.approval_hash, "Approved body",
        ["recruiter@tcs.com"], [], ["manager@clifyx.com"],
    )
    assert valid is False
    assert "cannot create" in reason


def test_graph_id_is_durable_before_finalization(tmp_path):
    engine, op = make_operation(tmp_path)
    assert engine.compare_and_set_draft_operation(op.idempotency_key, [DraftOperationState.APPROVED], DraftOperationState.CREATING)
    payload = dict(op.payload_data)
    payload["draft_id"] = "immutable-draft-id"
    assert engine.compare_and_set_draft_operation(
        op.idempotency_key, [DraftOperationState.CREATING], DraftOperationState.RECOVERED_PENDING_FINALIZATION, payload
    )
    restarted = EncryptedPersistenceEngine(str(tmp_path / "records.db"), master_key="isolated-draft-test-key")
    recovered = restarted.get_draft_operation(op.idempotency_key)
    assert recovered.state == DraftOperationState.RECOVERED_PENDING_FINALIZATION
    assert recovered.payload_data["draft_id"] == "immutable-draft-id"


def test_authenticated_draft_payload_rejects_tampering(tmp_path):
    engine, op = make_operation(tmp_path)
    with engine._get_connection() as conn:
        value = conn.execute("SELECT payload_ciphertext FROM draft_operations WHERE idempotency_key = ?", (op.idempotency_key,)).fetchone()[0]
        changed = value[:-1] + ("A" if value[-1] != "A" else "B")
        conn.execute("UPDATE draft_operations SET payload_ciphertext = ? WHERE idempotency_key = ?", (changed, op.idempotency_key))
        conn.commit()
    with pytest.raises(RuntimeError, match="authentication failed"):
        engine.get_draft_operation(op.idempotency_key)


def test_new_approval_supersedes_previous_active_generation(tmp_path):
    engine, first = make_operation(tmp_path)
    second = create_and_store_approval(
        record_id="record-1", conversation_id="conversation-1", immutable_anchor_id="immutable-1",
        canonical_to=["recruiter@tcs.com"], canonical_cc=[], normalized_bcc=[],
        content="New approval", record_version=7, engine=engine,
    )
    assert engine.get_draft_operation(first.idempotency_key).state == DraftOperationState.SUPERSEDED
    assert engine.get_draft_operation(second.idempotency_key).state == DraftOperationState.APPROVED
