import re

def fix_m5():
    with open("tests/test_m5_draft_workflow.py", "r") as f:
        content = f.read()

    # 1. test_content_modification_invalidates_approval
    # appr = create_and_store_approval("rec-hash-test", "conv-hash", "msg-hash", to, cc, bcc, content_orig)
    content = content.replace(
        'appr = create_and_store_approval("rec-hash-test", "conv-hash", "msg-hash", to, cc, bcc, content_orig)',
        'from backend.app.infrastructure.persistence import EncryptedPersistenceEngine\n        engine = EncryptedPersistenceEngine()\n        appr = create_and_store_approval("rec-hash-test", "conv-hash", "msg-hash", to, cc, bcc, content_orig, 1, engine)'
    )

    # 2. test_bcc_addition_invalidates_approval
    # appr = create_and_store_approval("rec-bcc-test", "conv-bcc", "msg-bcc", to, cc, bcc_orig, content)
    content = content.replace(
        'appr = create_and_store_approval("rec-bcc-test", "conv-bcc", "msg-bcc", to, cc, bcc_orig, content)',
        'from backend.app.infrastructure.persistence import EncryptedPersistenceEngine\n        engine = EncryptedPersistenceEngine()\n        appr = create_and_store_approval("rec-bcc-test", "conv-bcc", "msg-bcc", to, cc, bcc_orig, content, 1, engine)'
    )

    with open("tests/test_m5_draft_workflow.py", "w") as f:
        f.write(content)

def fix_m7():
    with open("tests/test_m7_release_readiness.py", "r") as f:
        content = f.read()

    # Fix appr2 = None # Stubbed for compilation
    content = content.replace(
        'appr2 = None # Stubbed for compilation',
        'appr2 = get_draft_operation(appr1.idempotency_key, engine)'
    )
    
    with open("tests/test_m7_release_readiness.py", "w") as f:
        f.write(content)

def fix_routes():
    with open("backend/app/api/routes.py", "r") as f:
        content = f.read()
    
    # In routes.py, when draft is created, store the draft_id
    success_str = """        # Success!
        op.payload_data["draft_id"] = result.draft_id
        persistence.store_draft_operation(op)
        persistence.update_draft_operation_state(op.idempotency_key, DraftOperationState.CREATED)"""
        
    old_success_str = """        # Success!
        persistence.update_draft_operation_state(op.idempotency_key, DraftOperationState.CREATED)"""
        
    content = content.replace(old_success_str, success_str)
    
    with open("backend/app/api/routes.py", "w") as f:
        f.write(content)

fix_m5()
fix_m7()
fix_routes()
print("Fixed phase 3!")
