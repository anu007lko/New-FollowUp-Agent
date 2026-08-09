"""Mailbox-wide exact-subject reconciliation for separate interview chains."""

from dataclasses import dataclass
from typing import Optional

from backend.app.domain.interview_linker import (
    link_exact_subject_interview_conversations,
    normalize_full_subject,
)
from backend.app.domain.models import DomainStatus
from backend.app.infrastructure.graph_client import MicrosoftGraphClient
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine


@dataclass
class InterviewReconciliationResult:
    records_checked: int = 0
    conversations_linked: int = 0
    conflicts_skipped: int = 0
    errors: int = 0


class InterviewReconciliationService:
    """Automatically attach separate interview conversations to submissions.

    Discovery uses only an exact normalized *complete subject*.  Job ID, EP,
    candidate name and participants are never matching inputs.  After discovery,
    immutable Outlook conversation/message IDs are the authoritative boundaries.
    """

    def __init__(
        self,
        graph_client: Optional[MicrosoftGraphClient] = None,
        persistence: Optional[EncryptedPersistenceEngine] = None,
    ):
        self.graph_client = graph_client or MicrosoftGraphClient()
        self.persistence = persistence or EncryptedPersistenceEngine()

    def reconcile(self, date_str: str = "2026-07-10") -> InterviewReconciliationResult:
        result = InterviewReconciliationResult()
        mailbox_messages, auth_status, _ = self.graph_client.fetch_mailbox_messages_since(date_str)
        if auth_status != "ok":
            return result

        # A duplicate complete subject would violate the confirmed business rule.
        # Fail closed for that subject rather than guessing which record to link.
        records_by_subject: dict[str, list[tuple]] = {}
        for header in self.persistence.list_records():
            snapshot = self.persistence.get_record_payload_snapshot(header.id)
            if not snapshot:
                continue
            payload, version, status = snapshot
            subject = payload.get("subject") or ""
            normalized = normalize_full_subject(subject)
            if normalized:
                records_by_subject.setdefault(normalized, []).append(
                    (header, payload, version, status)
                )

        for matches in records_by_subject.values():
            if len(matches) != 1:
                result.conflicts_skipped += len(matches)
                continue
            header, payload, version, status = matches[0]
            result.records_checked += 1
            existing = payload.get("linked_conversations", []) or []
            existing_ids = {
                item.get("conversation_id") for item in existing if isinstance(item, dict)
            }
            discovered = link_exact_subject_interview_conversations(
                payload.get("subject") or "",
                header.conversation_id,
                mailbox_messages,
                existing_ids,
            )
            if not discovered:
                continue

            hydrated = []
            for link in discovered:
                messages, thread_status = self.graph_client.fetch_exact_conversation_messages(
                    link["conversation_id"]
                )
                if thread_status != "ok" or not messages:
                    result.errors += 1
                    continue
                # Revalidate the complete subject after fetching the exact thread.
                if any(
                    normalize_full_subject(message.get("subject"))
                    != normalize_full_subject(payload.get("subject"))
                    for message in messages
                ):
                    result.errors += 1
                    continue
                link["thread_messages"] = messages
                hydrated.append(link)

            if not hydrated:
                continue
            payload["linked_conversations"] = existing + hydrated
            try:
                self.persistence.update_record_optimistically(
                    header.id, payload, status, version
                )
                result.conversations_linked += len(hydrated)
            except ValueError:
                # A manager or another review changed the record concurrently.
                result.conflicts_skipped += 1

        return result
