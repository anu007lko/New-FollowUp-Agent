"""Deterministic linking for separate Outlook interview conversations."""

import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List


_PREFIX = re.compile(r"^(?:(?:re|fw|fwd|tcs\s+submission|submission|submissions)\s*:\s*)+", re.IGNORECASE)
_INTERVIEW_TERMS = ("interview", "invite", "schedule", "availability", "reschedule")


def normalize_full_subject(subject: str | None) -> str:
    """Normalize transport prefixes/spacing while retaining the complete subject."""
    value = _PREFIX.sub("", (subject or "").strip())
    return " ".join(value.split()).casefold()


def link_exact_subject_interview_conversations(
    original_subject: str,
    original_conversation_id: str,
    mailbox_messages: Iterable[Dict[str, Any]],
    existing_conversation_ids: Iterable[str] = (),
) -> List[Dict[str, Any]]:
    """Return separate interview conversations that exactly match the full subject.

    EP reference, Job ID, candidate name and participants are deliberately ignored.
    Exact immutable conversation identity remains the stored link boundary.
    """
    target = normalize_full_subject(original_subject)
    if not target:
        return []
    existing = set(existing_conversation_ids) | {original_conversation_id}
    grouped: Dict[str, List[Dict[str, Any]]] = {}
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
    def process_group(conversation_id, group):
        from backend.app.domain.message_facts import is_automatic_reply
        raw_msgs = [m[0] for m in group]

        # Must contain at least one valid external inbound client message
        has_approved_external = False
        for m in raw_msgs:
            sender = (m.get("from", {}).get("emailAddress", {}).get("address") or "").strip().lower()
            bp = m.get("bodyPreview", "")
            if not sender or sender.endswith("@clifyx.com"):
                continue
            if is_automatic_reply(sender, bp, m):
                continue
            has_approved_external = True
            break

        if not has_approved_external:
            return None

        thread_role = "interview_coordination" if any(m[1] == "interview_coordination" for m in group) else "client_response"
        return {
            "conversation_id": conversation_id,
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
        }

    results = []
    for cid, grp in grouped.items():
        processed = process_group(cid, grp)
        if processed:
            results.append(processed)
    return results
