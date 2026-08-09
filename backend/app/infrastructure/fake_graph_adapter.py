"""
Fake Microsoft Graph Draft Adapter for Recruitment Follow-Up Agent.

INVARIANTS:
1. Simulates createReplyAll using immutable source message ID and exact conversationId.
2. Never uses Job ID, EP reference, subject, or candidate name to anchor the reply.
3. Implements strict idempotency key tracking to reconcile duplicates and prevent multiple drafts.
4. Returns synthetic draft ID with message: 'Draft created—not sent. Review and send in Outlook.'
5. Contains ZERO send methods, send permissions, or network mail transmission capabilities.
6. Does NOT access live Microsoft Graph, Outlook, or old-app LaunchAgent services.
"""

import uuid
from datetime import datetime
from typing import Callable, Dict, Any, List, Optional, Tuple
from backend.app.domain.models import DraftCreationResult
from backend.app.domain.date_utils import TIMEZONE_UTC


class FakeGraphDraftAdapter:
    """
    Simulates Microsoft Graph draft creation endpoint (POST /me/messages/{id}/createReplyAll).
    """

    def __init__(self):
        import os
        is_test = os.environ.get("ENVIRONMENT", "").lower() == "test"
        if not is_test:
            raise RuntimeError("FATAL: FakeGraphDraftAdapter may only be used when ENVIRONMENT=test")
        
        # In-memory draft registry keyed by idempotency_key
        self._drafts_by_idempotency: Dict[str, DraftCreationResult] = {}
        # In-memory draft registry keyed by draft_id
        self._drafts_by_id: Dict[str, DraftCreationResult] = {}

    def create_reply_all_draft(
        self,
        record_id: str,
        conversation_id: str,
        source_message_id: str,
        content: str,
        to_recipients: List[str],
        cc_recipients: List[str],
        bcc_recipients: List[str],
        approval_hash: str,
        idempotency_key: str,
        persist_created_id: Optional[Callable[[str], None]] = None,
    ) -> Tuple[DraftCreationResult, bool]:
        """
        Simulate createReplyAll draft in Outlook mailbox.
        
        Returns:
            Tuple[DraftCreationResult, bool]: (result, was_newly_created)
        """
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("idempotency_key is required for draft creation")

        if not source_message_id or not source_message_id.strip():
            raise ValueError("source_message_id (immutable Graph ID) is required for createReplyAll")

        if not conversation_id or not conversation_id.strip():
            raise ValueError("conversation_id is required for createReplyAll")

        # Check for existing draft with this idempotency key (idempotency / double-click protection)
        if idempotency_key in self._drafts_by_idempotency:
            existing = self._drafts_by_idempotency[idempotency_key]
            # Return existing draft with reconciled status
            reconciled = DraftCreationResult(
                draft_id=existing.draft_id,
                record_id=existing.record_id,
                conversation_id=existing.conversation_id,
                source_message_id=existing.source_message_id,
                status="reconciled_existing",
                message="Draft created—not sent. Review and send in Outlook.",
                to=existing.to,
                cc=existing.cc,
                bcc=existing.bcc,
                approval_hash=existing.approval_hash,
                idempotency_key=existing.idempotency_key,
                created_at=existing.created_at,
                is_synthetic=True
            )
            return reconciled, False

        # Create new synthetic draft
        draft_id = f"draft-syn-{uuid.uuid4().hex[:12]}"
        if persist_created_id:
            persist_created_id(draft_id)
        now_iso = datetime.now(TIMEZONE_UTC).isoformat()

        result = DraftCreationResult(
            draft_id=draft_id,
            record_id=record_id,
            conversation_id=conversation_id,
            source_message_id=source_message_id,
            status="created",
            message="Draft created—not sent. Review and send in Outlook.",
            to=list(to_recipients),
            cc=list(cc_recipients),
            bcc=list(bcc_recipients),
            approval_hash=approval_hash,
            idempotency_key=idempotency_key,
            created_at=now_iso,
            is_synthetic=True,
            verified=True,
            operation_state="CREATED",
        )

        self._drafts_by_idempotency[idempotency_key] = result
        self._drafts_by_id[draft_id] = result

        return result, True

    def get_draft_by_id(self, draft_id: str) -> Optional[DraftCreationResult]:
        """Fetch draft by draft_id."""
        return self._drafts_by_id.get(draft_id)

    def verify_draft(self, draft_id: str, conversation_id: str, content: str, to: List[str], cc: List[str], bcc: List[str], marker: str) -> Dict[str, Any]:
        draft = self._drafts_by_id.get(draft_id)
        if not draft or draft.conversation_id != conversation_id or sorted(draft.to) != sorted(to) or sorted(draft.cc) != sorted(cc) or sorted(draft.bcc) != sorted(bcc):
            raise RuntimeError("Synthetic draft verification failed")
        return {"id": draft_id, "isDraft": True, "conversationId": conversation_id}

    def list_drafts_for_record(self, record_id: str) -> List[DraftCreationResult]:
        """List all drafts created for a specific submission record."""
        return [d for d in self._drafts_by_id.values() if d.record_id == record_id]
