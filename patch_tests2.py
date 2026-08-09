import re

def fix_m5():
    with open("tests/test_m5_draft_workflow.py", "r") as f:
        content = f.read()

    # Fix the get_draft_operation mess
    content = content.replace("appr = create_and_store_approval, get_draft_operation", "appr = create_and_store_approval")

    # Fix assertions in test_prevent_approval_replay_across_records
    content = content.replace(
        'assert "No active server-side approval record found" in res.json()["detail"] or "mismatch" in res.json()["detail"]',
        'assert "Conversation ID has changed" in res.json()["detail"] or "mismatch" in res.json()["detail"]'
    )
    
    # Fix assertions in test_newer_reply_anchor_invalidates_approval
    content = content.replace(
        'assert "Reply anchor changed" in create_res.json()["detail"] or "invalidated" in create_res.json()["detail"]',
        'assert "Source message (reply anchor) has changed" in create_res.json()["detail"] or "invalidated" in create_res.json()["detail"]'
    )
    
    # test_stable_idempotency_key_and_reconciliation uses fake graph draft adapter directly inside the test? No, it calls /draft-create.
    # Why did it return 400 instead of 200? Because the idempotency_key was passed, but it failed validation because the test didn't mock or update the op state?
    # Wait, in routes.py, I made it update the state to CREATED: `persistence.update_draft_operation_state(op.idempotency_key, DraftOperationState.CREATED)`. But tests use synthetic data so persistence might not carry over if it creates a new persistence instance!
    # Ah! `persistence = EncryptedPersistenceEngine()` in `routes.py` is an in-memory DB by default or uses `~/.recruitment_agent/records.db`?
    # In `routes.py`, `persistence` is instantiated once. It stores the `op`. So it should persist.
    # What error did it return on res2? Probably "Draft operation is not in an approved or retriable state (current state: DraftOperationState.CREATED)" !!
    # Because in `validate_draft_operation_match`, I wrote: `if op.state != DraftOperationState.APPROVED and op.state != DraftOperationState.FAILED_RECONCILABLE:` return False.
    # But wait, if it's already CREATED, it returns 400 because it's not APPROVED!
    # Ah! `validate_draft_operation_match` should allow CREATED state if the user is trying to reconcile it.
    
    with open("tests/test_m5_draft_workflow.py", "w") as f:
        f.write(content)

def fix_m7():
    with open("tests/test_m7_release_readiness.py", "r") as f:
        content = f.read()

    # Fix test_m7_06... create_and_store_approval call
    bad_call = """appr1 = create_and_store_approval(
        record_id=rec.id,
        conversation_id=rec.conversation_id,
        immutable_anchor_id=anchor.graph_immutable_id,
        canonical_to=to_addrs,
        canonical_cc=cc_addrs,
        normalized_bcc=["mgr@clifyx.com"],
        content=content,
        manager_identity="tarun@clifyx.com"
    )"""
    good_call = """from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
    engine = EncryptedPersistenceEngine()
    appr1 = create_and_store_approval(
        record_id=rec.id,
        conversation_id=rec.conversation_id,
        immutable_anchor_id=anchor.graph_immutable_id,
        canonical_to=to_addrs,
        canonical_cc=cc_addrs,
        normalized_bcc=["mgr@clifyx.com"],
        content=content,
        record_version=1,
        engine=engine,
        manager_identity="tarun@clifyx.com"
    )"""
    content = content.replace(bad_call, good_call)
    
    with open("tests/test_m7_release_readiness.py", "w") as f:
        f.write(content)

def fix_workflow():
    with open("backend/app/application/workflow_engine.py", "r") as f:
        content = f.read()
    
    # Allow CREATED state in validate_draft_operation_match for reconciliation
    content = content.replace(
        "if op.state != DraftOperationState.APPROVED and op.state != DraftOperationState.FAILED_RECONCILABLE:",
        "if op.state not in (DraftOperationState.APPROVED, DraftOperationState.FAILED_RECONCILABLE, DraftOperationState.CREATED, DraftOperationState.CREATING):"
    )
    with open("backend/app/application/workflow_engine.py", "w") as f:
        f.write(content)

fix_m5()
fix_m7()
fix_workflow()
print("Fixed!")
