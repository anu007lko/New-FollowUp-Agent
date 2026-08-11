"""
Audit trail domain module.
Provides canonical audit event creation, discrimination, and verification helpers.
"""

import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timezone


def is_audit_event(entry: Any) -> bool:
    """
    Discriminates system audit events from raw email/thread messages.
    An entry is an audit event if audit_event is True or legacy is_system_note is True.
    """
    if not isinstance(entry, dict):
        return False
    return entry.get("audit_event") is True or entry.get("is_system_note") is True


def create_audit_event(
    record_id: str,
    event_type: str,
    actor: str,
    prior_status: str,
    resulting_status: str,
    record_version: int,
    note: Optional[str] = None,
    action_id: Optional[str] = None,
    body_preview: Optional[str] = None,
    extra_fields: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Factory creating a canonical audit event dict.
    Every newly created audit event contains mandatory metadata:
    - entry_id (server-generated unique identifier)
    - record_id
    - timestamp (UTC ISO-8601)
    - sender / actor
    - event_type
    - prior_status
    - resulting_status
    - record_version (resulting version produced by this mutation)
    - audit_event: True
    - is_system_note: True (for legacy UI/model compatibility)
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    entry_id = f"evt-{uuid.uuid4().hex[:12]}"

    if not body_preview:
        if note:
            body_preview = f"[Audit: {event_type}] {note}"
        else:
            body_preview = f"[Audit: {event_type}] Transitioned from {prior_status} to {resulting_status}"

    evt: Dict[str, Any] = {
        "entry_id": entry_id,
        "record_id": record_id,
        "sender": actor,
        "timestamp": now_iso,
        "body_preview": body_preview,
        "event_type": event_type,
        "action_id": action_id or event_type,
        "prior_status": prior_status,
        "resulting_status": resulting_status,
        "record_version": record_version,
        "note": note or "",
        "audit_event": True,
        "is_system_note": True,
    }

    if extra_fields and isinstance(extra_fields, dict):
        for k, v in extra_fields.items():
            if k not in evt:
                evt[k] = v

    return evt
