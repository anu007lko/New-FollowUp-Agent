import sys
import os
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.interview_linker import normalize_full_subject, _PREFIX, _INTERVIEW_TERMS
from backend.app.domain.message_facts import is_automatic_reply
from backend.app.domain.consolidated_classifier import classify_record

APPROVED_DOMAINS = {"tcs.com"}

def link_exact_subject_filtered(
    original_subject: str,
    original_conversation_id: str,
    mailbox_messages: list,
    existing_conversation_ids: list = ()
) -> list:
    target = normalize_full_subject(original_subject)
    if not target:
        return []
    existing = set(existing_conversation_ids) | {original_conversation_id}
    grouped = {}
    
    for message in mailbox_messages:
        conversation_id = message.get("conversationId") or message.get("conversation_id")
        if not conversation_id or conversation_id in existing:
            continue
        if normalize_full_subject(message.get("subject")) != target:
            continue
            
        text = " ".join([
            str(message.get("subject") or ""),
            str(message.get("bodyPreview") or ""),
            str(((message.get("body") or {}).get("content") or "")),
        ]).casefold()
        
        role = "interview_coordination" if any(term in text for term in _INTERVIEW_TERMS) else "client_response"
        grouped.setdefault(conversation_id, []).append((message, role))

    now = datetime.now(timezone.utc).isoformat()
    filtered_links = []
    
    for cid, group in grouped.items():
        raw_msgs = [m[0] for m in group]
        
        # Rule check: Must contain at least 1 valid approved external inbound message
        has_approved_external = False
        for m in raw_msgs:
            sender = (m.get("from", {}).get("emailAddress", {}).get("address") or "").strip().lower()
            bp = m.get("bodyPreview", "")
            
            if not sender or sender.endswith("@clifyx.com"):
                continue
            if is_automatic_reply(sender, bp, m):
                continue
                
            domain = sender.split("@")[-1] if "@" in sender else ""
            if domain in APPROVED_DOMAINS or domain.endswith("tcs.com"):
                has_approved_external = True
                break

        if not has_approved_external:
            continue # Ignore internal-only or unapproved external threads

        thread_role = "interview_coordination" if any(m[1] == "interview_coordination" for m in group) else "client_response"
        filtered_links.append({
            "conversation_id": cid,
            "role": thread_role,
            "subject": raw_msgs[0].get("subject"),
            "received_at": min(
                (m.get("receivedDateTime") or m.get("sentDateTime") or now for m in raw_msgs)
            ),
            "linked_at": now,
            "linked_by": "automatic_exact_subject_rule",
            "thread_messages": sorted(
                raw_msgs,
                key=lambda m: m.get("sentDateTime") or m.get("receivedDateTime") or "",
            ),
        })

    return filtered_links

persistence = EncryptedPersistenceEngine()
headers = persistence.list_records()
now_dt = datetime.now(timezone.utc)

valid_count = 0
restored_records = []

for h in headers:
    snapshot = persistence.get_record_payload_snapshot(h.id)
    if not snapshot:
        continue
    payload, _, _ = snapshot
    subj = payload.get("subject", "")
    orig_conv_id = payload.get("conversation_id", "")
    orig_msg_id = payload.get("source_immutable_id") or h.graph_immutable_id
    linked = payload.get("linked_conversations", [])
    if not linked:
        continue

    # Evaluate classification with old linked vs new filtered linked
    cls_old_linked = classify_record(orig_msg_id, payload.get("thread_messages", []), now_dt, linked_conversations=linked)
    
    # Filter linked using new rule
    new_linked = []
    for lc in linked:
        lc_msgs = lc.get("thread_messages", [])
        if any(not (m.get("from", {}).get("emailAddress", {}).get("address") or "").lower().endswith("@clifyx.com") for m in lc_msgs):
            new_linked.append(lc)

    cls_new_linked = classify_record(orig_msg_id, payload.get("thread_messages", []), now_dt, linked_conversations=new_linked)

    if new_linked:
        valid_count += len(new_linked)
        print(f"VALID LINK PRESERVED: {h.id} | {subj} | Status: {cls_new_linked.category} ({cls_new_linked.proposed_status})")

    if cls_old_linked.proposed_status != cls_new_linked.proposed_status:
        restored_records.append({
            "record_id": h.id,
            "subject": subj,
            "prev_status": cls_old_linked.proposed_status,
            "restored_status": cls_new_linked.proposed_status
        })

print(f"\nTOTAL VALID LINKS PRESERVED: {valid_count}")
print(f"TOTAL RECORDS RESTORED: {len(restored_records)}")
