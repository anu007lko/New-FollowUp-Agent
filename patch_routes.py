import re

with open("backend/app/api/routes.py", "r") as f:
    content = f.read()

# Add imports
import_str = """
from backend.app.application.workflow_engine import (
    validate_interview_transition, compute_domain_status_after_interview,
    compute_feedback_due_at, validate_close_action, append_manager_note,
    format_system_note, TIMER_STARTING_STATES, check_suggestion_eligibility,
    select_reply_anchor_message, compute_reply_all_recipients,
    validate_bcc_list, compute_draft_approval_hash, validate_draft_operation_match,
    create_and_store_approval, get_draft_operation, invalidate_server_approval
)
from backend.app.domain.models import DraftOperationState
from backend.app.infrastructure.live_graph_draft_adapter import LiveGraphDraftAdapter
"""

# Replace the old workflow_engine import block
content = re.sub(
    r'from backend\.app\.application\.workflow_engine import \([\s\S]*?invalidate_server_approval\n\)',
    import_str.strip(),
    content
)

# Replace FakeGraphDraftAdapter import with both fake and live
adapter_init_str = """
from backend.app.infrastructure.fake_graph_adapter import FakeGraphDraftAdapter
from backend.app.infrastructure.live_graph_draft_adapter import LiveGraphDraftAdapter
import os
"""
content = re.sub(
    r'from backend\.app\.infrastructure\.fake_graph_adapter import FakeGraphDraftAdapter\nimport os',
    adapter_init_str.strip(),
    content
)

# Initialize both adapters where fake is initialized
init_str = """
fake_graph_draft_adapter = None
try:
    fake_graph_draft_adapter = FakeGraphDraftAdapter()
except RuntimeError:
    pass
live_graph_draft_adapter = LiveGraphDraftAdapter()
"""
content = re.sub(r'fake_graph_draft_adapter = FakeGraphDraftAdapter\(\)', init_str.strip(), content)

# Rewrite approve_draft body end
approve_body = """
    # Create and store server-side approval record
    op = create_and_store_approval(
        record_id=record.id,
        conversation_id=record.conversation_id,
        immutable_anchor_id=source_msg_id,
        canonical_to=canonical_to,
        canonical_cc=canonical_cc,
        normalized_bcc=normalized_bcc,
        content=request.content,
        record_version=record.record_version,
        engine=persistence
    )

    summary = f"Approved for {len(canonical_to)} To, {len(canonical_cc)} CC, {len(normalized_bcc)} BCC"

    return DraftApprovalResponse(
        is_approved=True,
        approval_hash=op.approval_hash,
        idempotency_key=op.idempotency_key,
        approved_at=op.created_at,
        canonical_summary=summary
    )
"""
# Match the block in approve_draft and replace it
content = re.sub(
    r'    # Create and store server-side approval record\n    approval_rec = create_and_store_approval\([\s\S]*?canonical_summary=summary\n    \)',
    approve_body.strip('\n'),
    content
)

# Rewrite create_draft body end
create_body = """
    if not request.idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency key required")
        
    op = get_draft_operation(request.idempotency_key, persistence)
    if not op:
        raise HTTPException(status_code=400, detail="Approval record missing or invalid")
        
    # Validate against server-side approval record
    is_valid, validation_err = validate_draft_operation_match(
        op=op,
        current_conversation_id=record.conversation_id,
        current_anchor_id=source_msg_id,
        client_approval_hash=request.approval_hash,
        content=request.content,
        to_list=canonical_to,
        cc_list=canonical_cc,
        bcc_list=request.bcc
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail=validation_err)

    if op.state == DraftOperationState.CREATING:
        raise HTTPException(status_code=409, detail="Draft creation already in progress")
    if op.state == DraftOperationState.CREATED:
        # Reconcile returning stored draft_id
        return DraftCreationResult(
            draft_id=op.payload_data.get("draft_id", "unknown"),
            record_id=record.id,
            conversation_id=record.conversation_id,
            source_message_id=source_msg_id,
            status="reconciled_existing",
            message="Draft created—not sent. Review and send in Outlook.",
            to=canonical_to,
            cc=canonical_cc,
            bcc=op.payload_data.get("normalized_bcc", []),
            approval_hash=op.approval_hash,
            idempotency_key=op.idempotency_key,
            created_at=op.created_at,
            is_synthetic=False
        )

    # Set state to CREATING
    persistence.update_draft_operation_state(op.idempotency_key, DraftOperationState.CREATING)

    try:
        is_test = os.environ.get("ENVIRONMENT", "").lower() == "test"
        if is_test and fake_graph_draft_adapter:
            result, was_new = fake_graph_draft_adapter.create_reply_all_draft(
                record_id=record.id,
                conversation_id=record.conversation_id,
                source_message_id=source_msg_id,
                content=request.content,
                to_recipients=canonical_to,
                cc_recipients=canonical_cc,
                bcc_recipients=op.payload_data["normalized_bcc"],
                approval_hash=op.approval_hash,
                idempotency_key=op.idempotency_key
            )
        else:
            result, was_new = live_graph_draft_adapter.create_reply_all_draft(
                record_id=record.id,
                conversation_id=record.conversation_id,
                source_message_id=source_msg_id,
                content=request.content,
                to_recipients=canonical_to,
                cc_recipients=canonical_cc,
                bcc_recipients=op.payload_data["normalized_bcc"],
                approval_hash=op.approval_hash,
                idempotency_key=op.idempotency_key
            )
            
        # Success!
        persistence.update_draft_operation_state(op.idempotency_key, DraftOperationState.CREATED)
        return result
    except Exception as e:
        persistence.update_draft_operation_state(op.idempotency_key, DraftOperationState.FAILED_RECONCILABLE)
        raise HTTPException(status_code=500, detail=str(e))
"""
content = re.sub(
    r'    # Validate against server-side approval record\n    is_valid, validation_err, approval_rec = validate_draft_approval_match\([\s\S]*?return result',
    create_body.strip('\n'),
    content
)

with open("backend/app/api/routes.py", "w") as f:
    f.write(content)

print("routes.py updated successfully.")
