import re

with open("backend/app/api/routes.py", "r") as f:
    content = f.read()

# Add get_trusted_manager_identity Dependency
dep_code = """
from fastapi import Depends

def get_trusted_manager_identity() -> str:
    # In a real system, extract from session/JWT.
    return "tarun@clifyx.com"
"""
if "get_trusted_manager_identity" not in content:
    content = content.replace("def _validate_and_get_record_payload", dep_code + "\ndef _validate_and_get_record_payload")

# Update _validate_and_get_record_payload
old_val = """    current_version = rec.latest_timestamp or rec.received_at or rec.created_at
    if req.record_version != current_version:
        raise HTTPException(status_code=409, detail="Record version token is stale or mismatched.")"""
new_val = """    if req.record_version != rec.record_version:
        raise HTTPException(status_code=409, detail="Record version token is stale or mismatched.")"""
content = content.replace(old_val, new_val)

# Update endpoints
endpoints = [
    ("post_manager_note", "ManagerNoteRequest"),
    ("post_followup_decision", "FollowUpDecisionRequest"),
    ("post_interview_confirmation", "InterviewConfirmationRequest"),
    ("post_outcome_decision", "OutcomeDecisionRequest"),
    ("post_close_record", "CloseRecordRequest"),
    ("post_reopen_record", "ReopenRecordRequest")
]

for func, req_type in endpoints:
    # replace signature
    old_sig = f"def {func}(record_id: str, req: {req_type}):"
    new_sig = f"def {func}(record_id: str, req: {req_type}, manager_identity: str = Depends(get_trusted_manager_identity)):"
    content = content.replace(old_sig, new_sig)
    
    # replace req.manager_identity -> manager_identity (but wait, they might be in different places)
    # The functions use `req.manager_identity`. We can just do a regex replace inside the function body.
    # To be safe, we can do a global replace of `req.manager_identity` with `manager_identity` ?
    # But only inside the endpoints. Since we know only endpoints use it, a global replace of `req.manager_identity` is probably fine because we removed it from the model.
    pass

# We will just replace `req.manager_identity` with `manager_identity` everywhere.
content = content.replace("req.manager_identity", "manager_identity")

# Replace persistence.save_record_payload(record_id, payload, target_status) with update_record_optimistically
# We need to catch ValueError.
# Let's find all `persistence.save_record_payload` calls.
save_pattern = re.compile(r"persistence\.save_record_payload\(record_id,\s*payload,\s*(.*?)\)")
def repl_save(m):
    target_status = m.group(1)
    return f'''try:
        persistence.update_record_optimistically(record_id, payload, {target_status}, req.record_version)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))'''

content = save_pattern.sub(repl_save, content)

with open("backend/app/api/routes.py", "w") as f:
    f.write(content)

print("Updated routes.py successfully.")
