"""Crash-safe Microsoft Graph Reply-All draft adapter.  It never sends mail."""

import hashlib
import html
import os
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Callable, List, Optional, Tuple
from urllib.parse import quote

import httpx

from backend.app.domain.date_utils import TIMEZONE_UTC
from backend.app.domain.models import DraftCreationResult
from backend.app.infrastructure.msal_client import MSALAuthenticationAdapter


class GraphDraftError(RuntimeError):
    """Sanitized Graph failure.  Response bodies are intentionally excluded."""


class LiveGraphDraftAdapter:
    BASE = "https://graph.microsoft.com/v1.0"
    IDEMPOTENCY_PROPERTY_ID = "String {7E5A7C8D-838B-46E4-88B9-5A266C3ECED3} Name ClifyxFollowupIdempotency"

    def __init__(self, auth_adapter: Optional[MSALAuthenticationAdapter] = None):
        self.auth_adapter = auth_adapter or MSALAuthenticationAdapter()

    @staticmethod
    def _enabled() -> bool:
        return (
            os.environ.get("GRAPH_ENABLED", "False").lower() == "true"
            and os.environ.get("DRAFTS_ENABLED", "False").lower() == "true"
            and os.environ.get("MAIL_SEND_ENABLED", "False").lower() != "true"
        )

    def _headers(self) -> dict:
        if not self._enabled():
            raise GraphDraftError("Live Graph draft capability is disabled")
        result = self.auth_adapter.acquire_token_silently()
        if result.status != "ok" or not result.token or result.identity != "tarun@clifyx.com":
            raise GraphDraftError("Microsoft Graph authentication or mailbox identity verification failed")
        return {
            "Authorization": f"Bearer {result.token}",
            "Prefer": 'IdType="ImmutableId"',
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _addresses(items: list) -> List[str]:
        return sorted({(i.get("emailAddress", {}).get("address") or "").strip().lower() for i in items if i.get("emailAddress", {}).get("address")})

    @staticmethod
    def marker(idempotency_key: str, approval_hash: str) -> str:
        return hashlib.sha256(f"{idempotency_key}:{approval_hash}".encode()).hexdigest()

    @staticmethod
    def _canonical_visible_text(value: str) -> str:
        """Compare manager-approved visible text while tolerating Graph's HTML wrapper."""
        value = re.sub(r"(?i)<br\s*/?>", "\n", value)
        value = re.sub(r"(?i)</(?:div|p|li)\s*>", "\n", value)
        value = re.sub(r"<[^>]+>", "", value)
        value = html.unescape(value).replace("\xa0", " ").replace("\r\n", "\n")
        return "\n".join(line.rstrip() for line in value.split("\n")).strip()

    @classmethod
    def _comparison_text(cls, value: str) -> str:
        """Normalize Graph's harmless HTML/whitespace rewrites for verification."""
        visible = unicodedata.normalize("NFKC", cls._canonical_visible_text(value))
        visible = visible.replace("\u200b", "").replace("\ufeff", "")
        return re.sub(r"\s+", " ", visible).strip()

    def create_skeleton(self, source_message_id: str, persist_created_id: Callable[[str], None]) -> str:
        headers = self._headers()
        url = f"{self.BASE}/me/messages/{quote(source_message_id, safe='')}/createReplyAll"
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, headers=headers, json={})
        if response.status_code not in (200, 201):
            raise GraphDraftError(f"Graph createReplyAll failed with HTTP {response.status_code}")
        try:
            draft_id = response.json().get("id")
        except Exception as exc:
            raise GraphDraftError("Graph createReplyAll returned no verifiable draft identity") from exc
        if not draft_id:
            raise GraphDraftError("Graph createReplyAll returned no verifiable draft identity")
        persist_created_id(draft_id)  # durable callback immediately after Graph reveals the ID
        return draft_id

    def _read_draft(self, draft_id: str) -> dict:
        headers = self._headers()
        prop = quote(self.IDEMPOTENCY_PROPERTY_ID, safe="")
        url = (f"{self.BASE}/me/messages/{quote(draft_id, safe='')}?"
               "$select=id,isDraft,conversationId,body,toRecipients,ccRecipients,bccRecipients&"
               f"$expand=singleValueExtendedProperties($filter=id%20eq%20'{prop}')")
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, headers=headers)
        if response.status_code != 200:
            raise GraphDraftError(f"Graph draft verification failed with HTTP {response.status_code}")
        return response.json()

    def verify_draft(self, draft_id: str, conversation_id: str, content: str, to: List[str], cc: List[str], bcc: List[str], marker: str, preserved_chain_text: Optional[str] = None) -> dict:
        data = self._read_draft(draft_id)
        returned_body = (data.get("body") or {}).get("content") or ""
        visible_body = self._canonical_visible_text(returned_body)
        approved_visible = self._canonical_visible_text(content)
        properties = data.get("singleValueExtendedProperties", [])
        stored_marker = next((
            item.get("value") for item in properties
            if (item.get("id") or "").casefold() == self.IDEMPOTENCY_PROPERTY_ID.casefold()
        ), None)
        checks = [
            data.get("isDraft") is True,
            data.get("conversationId") == conversation_id,
            self._addresses(data.get("toRecipients", [])) == sorted({x.lower() for x in to}),
            self._addresses(data.get("ccRecipients", [])) == sorted({x.lower() for x in cc}),
            self._addresses(data.get("bccRecipients", [])) == sorted({x.lower() for x in bcc}),
            stored_marker == marker,
            visible_body.startswith(approved_visible),
            len(visible_body) > len(approved_visible),
        ]
        if preserved_chain_text:
            preserved = self._comparison_text(preserved_chain_text)
            returned = self._comparison_text(returned_body)
            checks.append(bool(preserved) and preserved in returned)
        if not all(checks) or any(not x.endswith("@clifyx.com") for x in self._addresses(data.get("bccRecipients", []))):
            raise GraphDraftError("Graph draft read-back did not preserve the approved reply, original conversation, and recipients")
        return data

    def finalize_existing(self, draft_id: str, conversation_id: str, content: str, to: List[str], cc: List[str], bcc: List[str], approval_hash: str, idempotency_key: str) -> None:
        headers = self._headers()
        marker = self.marker(idempotency_key, approval_hash)
        existing = self._read_draft(draft_id)
        existing_properties = existing.get("singleValueExtendedProperties", [])
        existing_marker = next((
            item.get("value") for item in existing_properties
            if (item.get("id") or "").casefold() == self.IDEMPOTENCY_PROPERTY_ID.casefold()
        ), None)
        if existing_marker == marker:
            self.verify_draft(draft_id, conversation_id, content, to, cc, bcc, marker)
            return

        quoted_chain_html = (existing.get("body") or {}).get("content") or ""
        quoted_chain_text = self._canonical_visible_text(quoted_chain_html)
        if not quoted_chain_text:
            raise GraphDraftError("Outlook Reply All draft did not contain the original conversation history")
        approved_html = html.escape(content).replace("\r\n", "\n").replace("\n", "<br>")
        combined_body = f"<div>{approved_html}</div><br><br>{quoted_chain_html}"
        payload = {
            "body": {"contentType": "html", "content": combined_body},
            "toRecipients": [{"emailAddress": {"address": x}} for x in to],
            "ccRecipients": [{"emailAddress": {"address": x}} for x in cc],
            "bccRecipients": [{"emailAddress": {"address": x}} for x in bcc],
            "singleValueExtendedProperties": [{"id": self.IDEMPOTENCY_PROPERTY_ID, "value": marker}],
        }
        url = f"{self.BASE}/me/messages/{quote(draft_id, safe='')}"
        with httpx.Client(timeout=30.0) as client:
            response = client.patch(url, headers=headers, json=payload)
        if response.status_code not in (200, 204):
            raise GraphDraftError(f"Graph draft update failed with HTTP {response.status_code}")
        self.verify_draft(draft_id, conversation_id, content, to, cc, bcc, marker, quoted_chain_text)

    def find_reconciliation_candidates(self, conversation_id: str, started_at: str) -> List[str]:
        """Read Drafts and match only exact conversation identity and creation window."""
        headers = self._headers()
        lower = datetime.fromisoformat(started_at) - timedelta(minutes=2)
        url = f"{self.BASE}/me/mailFolders/drafts/messages?$select=id,isDraft,conversationId,createdDateTime&$top=100"
        found: List[str] = []
        with httpx.Client(timeout=30.0) as client:
            while url:
                response = client.get(url, headers=headers)
                if response.status_code != 200:
                    raise GraphDraftError(f"Graph draft reconciliation failed with HTTP {response.status_code}")
                page = response.json()
                for item in page.get("value", []):
                    created = item.get("createdDateTime")
                    if item.get("isDraft") is True and item.get("conversationId") == conversation_id and created:
                        if datetime.fromisoformat(created.replace("Z", "+00:00")) >= lower:
                            found.append(item["id"])
                url = page.get("@odata.nextLink")
        return sorted(set(found))

    def create_reply_all_draft(self, *, record_id: str, conversation_id: str, source_message_id: str, content: str, to_recipients: List[str], cc_recipients: List[str], bcc_recipients: List[str], approval_hash: str, idempotency_key: str, persist_created_id: Optional[Callable[[str], None]] = None) -> Tuple[DraftCreationResult, bool]:
        if persist_created_id is None:
            raise GraphDraftError("A durable draft-ID persistence callback is required")
        draft_id = self.create_skeleton(source_message_id, persist_created_id)
        self.finalize_existing(draft_id, conversation_id, content, to_recipients, cc_recipients, bcc_recipients, approval_hash, idempotency_key)
        return DraftCreationResult(
            draft_id=draft_id, record_id=record_id, conversation_id=conversation_id,
            source_message_id=source_message_id, status="created",
            message="Draft created—not sent. Review and send in Outlook.", to=to_recipients,
            cc=cc_recipients, bcc=bcc_recipients, approval_hash=approval_hash,
            idempotency_key=idempotency_key, created_at=datetime.now(TIMEZONE_UTC).isoformat(),
            is_synthetic=False, verified=True, operation_state="CREATED",
        ), True
