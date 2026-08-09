"""
Microsoft Graph Integration Client (Read-Only Import & Review).

INVARIANTS:
1. Reuses only existing MSAL token cache with silent refresh only.
2. NEVER launches interactive login or consent screens.
3. NEVER requests or modifies permissions.
4. Fails closed if Mail.Send is present in effective permissions.
5. Requests immutable Graph message IDs via Prefer: IdType="ImmutableId".
6. Explicitly labels synthetic fixtures as synthetic_test_data when live auth is unavailable.
"""

import os
import httpx
from typing import Optional, List, Dict, Any, Tuple
from backend.app.infrastructure.msal_client import MSALAuthenticationAdapter, MSALPermissionError
from backend.app.domain.date_utils import get_new_york_midnight_utc_iso


class MicrosoftGraphClient:
    ALLOWED_SCOPES = ["Mail.Read", "Mail.ReadWrite"]
    PROHIBITED_SCOPES = ["Mail.Send"]
    DEFAULT_MAILBOX = "tarun@clifyx.com"
    DEFAULT_FOLDER_NAME = "Submissions"

    def __init__(self, auth_adapter: Optional[MSALAuthenticationAdapter] = None):
        self.auth_adapter = auth_adapter or MSALAuthenticationAdapter()
        self.assert_permissions_allowed()

    def assert_permissions_allowed(self) -> None:
        """Verify effective permissions strictly exclude Mail.Send."""
        self.auth_adapter.assert_scopes_allowed(self.ALLOWED_SCOPES)

    def get_auth_status(self) -> Tuple[Optional[str], str, Dict[str, Any]]:
        """
        Check silent authentication status.
        Returns: (token_or_none, status_string, config_diagnostics)
        """
        res = self.auth_adapter.acquire_token_silently()
        if res.status == "ok" and res.token:
            return res.token, "ok", res.config_diagnostics
        return None, "synthetic_test_data", res.config_diagnostics

    def fetch_submissions_folder_messages(
        self,
        mailbox: str = DEFAULT_MAILBOX,
        folder_name: str = DEFAULT_FOLDER_NAME,
        date_str: str = "2026-07-10",
        top: int = 100
    ) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
        """
        Page messages from Submissions folder starting July 10, 2026 (America/New_York midnight converted to UTC) using Immutable IDs.
        Returns: (messages_list, auth_status, config_diagnostics)
        """
        start_date_utc = get_new_york_midnight_utc_iso(date_str)
        token, auth_status, diagnostics = self.get_auth_status()

        if auth_status != "ok" or not token:
            # Synthetic mailbox data is a test fixture only.  Production and local
            # manager modes must fail closed so an authentication outage can never
            # create plausible-looking recruitment records.
            is_test = os.environ.get("ENVIRONMENT", "").strip().lower() == "test"
            synthetic_enabled = os.environ.get(
                "USE_SYNTHETIC_DATA", "False"
            ).strip().lower() in ("true", "1", "yes")
            if is_test and synthetic_enabled:
                return self._generate_synthetic_preview_dataset(), "synthetic_test_data", diagnostics
            return [], auth_status or "auth_unavailable", diagnostics

        headers = {
            "Authorization": f"Bearer {token}",
            "Prefer": 'IdType="ImmutableId"',
            "Accept": "application/json"
        }

        # Step 1: Resolve Submissions folder ID using /me/mailFolders or /users/{mailbox}/mailFolders
        folder_url = f"https://graph.microsoft.com/v1.0/me/mailFolders?$top=250"
        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.get(folder_url, headers=headers)
                if res.status_code == 404 or res.status_code == 400:
                    folder_url = f"https://graph.microsoft.com/v1.0/users/{mailbox}/mailFolders?$top=250"
                    res = client.get(folder_url, headers=headers)

                if res.status_code != 200:
                    return [], f"http_folder_error_{res.status_code}", diagnostics

                target_folder_id = None
                folders_url_next = folder_url
                while folders_url_next and not target_folder_id:
                    res = client.get(folders_url_next, headers=headers)
                    if res.status_code != 200:
                        break
                    res_json = res.json()
                    folders_data = res_json.get("value", [])
                    for f in folders_data:
                        if f.get("displayName", "").strip().lower() == folder_name.lower():
                            target_folder_id = f.get("id")
                            break
                    folders_url_next = res_json.get("@odata.nextLink")

                if not target_folder_id:
                    return [], "folder_not_found", diagnostics

                # Step 2: Query messages received on or after July 10, 2026 America/New_York midnight in UTC (2026-07-10T04:00:00Z)
                messages_url = (
                    f"https://graph.microsoft.com/v1.0/me/mailFolders/{target_folder_id}/messages"
                    f"?$filter=receivedDateTime ge {start_date_utc}"
                    f"&$select=id,conversationId,internetMessageId,subject,sentDateTime,receivedDateTime,from,toRecipients,ccRecipients,hasAttachments,bodyPreview"
                    f"&$top={top}"
                )

                all_messages: List[Dict[str, Any]] = []
                next_url: Optional[str] = messages_url

                while next_url:
                    msg_res = client.get(next_url, headers=headers)
                    if msg_res.status_code != 200:
                        if not all_messages:
                            return [], f"http_msg_error_{msg_res.status_code}", diagnostics
                        break
                    res_body = msg_res.json()
                    page_messages = res_body.get("value", [])
                    all_messages.extend(page_messages)
                    next_url = res_body.get("@odata.nextLink")

                return all_messages, "ok", diagnostics

        except Exception as e:
            return [], f"error_{str(e)}", diagnostics

    def fetch_mailbox_messages_since(
        self, date_str: str = "2026-07-10", top: int = 100
    ) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
        """Read mailbox-wide message headers for exact-subject interview discovery.

        This is read-only and returns no synthetic fallback: automatic linking must
        never be based on fixtures or partial authentication.
        """
        start_date_utc = get_new_york_midnight_utc_iso(date_str)
        token, auth_status, diagnostics = self.get_auth_status()
        if auth_status != "ok" or not token:
            return [], auth_status, diagnostics
        headers = {
            "Authorization": f"Bearer {token}",
            "Prefer": 'IdType="ImmutableId"',
            "Accept": "application/json",
        }
        next_url: Optional[str] = (
            "https://graph.microsoft.com/v1.0/me/messages"
            f"?$filter=receivedDateTime ge {start_date_utc}"
            "&$select=id,conversationId,internetMessageId,subject,sentDateTime,"
            "receivedDateTime,from,toRecipients,ccRecipients,replyTo,hasAttachments,bodyPreview"
            f"&$top={top}"
        )
        messages: List[Dict[str, Any]] = []
        try:
            with httpx.Client(timeout=20.0) as client:
                while next_url:
                    response = client.get(next_url, headers=headers)
                    if response.status_code != 200:
                        return [], f"http_mailbox_error_{response.status_code}", diagnostics
                    data = response.json()
                    messages.extend(data.get("value", []))
                    next_url = data.get("@odata.nextLink")
            return messages, "ok", diagnostics
        except Exception as exc:
            return [], f"error_{type(exc).__name__}", diagnostics

    def fetch_exact_conversation_messages(
        self, conversation_id: str, top: int = 100
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Fetch one immutable Outlook conversation across all mailbox folders."""
        token, auth_status, _ = self.get_auth_status()
        if auth_status != "ok" or not token or not conversation_id:
            return [], auth_status
        safe_conversation_id = conversation_id.replace("'", "''")
        headers = {
            "Authorization": f"Bearer {token}",
            "Prefer": 'IdType="ImmutableId"',
            "Accept": "application/json",
        }
        next_url: Optional[str] = (
            "https://graph.microsoft.com/v1.0/me/messages"
            f"?$filter=conversationId eq '{safe_conversation_id}'"
            "&$select=id,conversationId,internetMessageId,subject,sentDateTime,"
            "receivedDateTime,from,toRecipients,ccRecipients,replyTo,hasAttachments,bodyPreview,parentFolderId"
            "&$expand=attachments($select=id,name,contentType,size,isInline)"
            f"&$top={top}"
        )
        messages: List[Dict[str, Any]] = []
        try:
            with httpx.Client(timeout=20.0) as client:
                while next_url:
                    response = client.get(next_url, headers=headers)
                    if response.status_code != 200:
                        return [], f"http_conversation_error_{response.status_code}"
                    data = response.json()
                    messages.extend(data.get("value", []))
                    next_url = data.get("@odata.nextLink")
            return messages, "ok"
        except Exception as exc:
            return [], f"error_{type(exc).__name__}"

    def _generate_synthetic_preview_dataset(self) -> List[Dict[str, Any]]:
        """
        Generate reproducible synthetic candidates for read-only preview mode
        when live Graph token is unavailable.
        Uses actual production subject line format:
        418326 - EP2026RA7415469 - Govinda Mundra - Technical Program Manager for AI PM - AMEX - Phoenix, AZ
        """
        return [
            {
                "id": "AAMkAGExM2FiYjQ0LTY3ODktNDEyMy05ODc2LTAxMjM0NTY3ODkwMQAAAAA1",
                "conversationId": "AAQkAGExM2FiYjQ0LTY3ODktNDEyMy05ODc2LTAxMjM0NTY3ODkwMQAQAJ2M1",
                "internetMessageId": "<msg-001@clifyx.com>",
                "subject": "418326 - EP2026RA7415469 - Govinda Mundra - Technical Program Manager for AI PM - AMEX - Phoenix, AZ",
                "receivedDateTime": "2026-07-15T14:30:00Z",
                "sentDateTime": "2026-07-15T14:29:30Z",
                "toRecipients": [{"emailAddress": {"address": "recruiter@tcs.com", "name": "TCS Recruiter"}}],
                "ccRecipients": [{"emailAddress": {"address": "bofa_manager@bankofamerica.com", "name": "BofA Manager"}}],
            },
            {
                "id": "AAMkAGExM2FiYjQ0LTY3ODktNDEyMy05ODc2LTAxMjM0NTY3ODkwMQAAAAA2",
                "conversationId": "AAQkAGExM2FiYjQ0LTY3ODktNDEyMy05ODc2LTAxMjM0NTY3ODkwMQAQAJ2M2",
                "internetMessageId": "<msg-002@clifyx.com>",
                "subject": "771209 - EP2026RA9981240 - Priya Patel - React Frontend Architect - Apple - Remote",
                "receivedDateTime": "2026-07-18T09:15:00Z",
                "sentDateTime": "2026-07-18T09:14:00Z",
                "toRecipients": [{"emailAddress": {"address": "hr.us@tcs.com", "name": "TCS HR"}}],
                "ccRecipients": [],
            },
            {
                "id": "AAMkAGExM2FiYjQ0LTY3ODktNDEyMy05ODc2LTAxMjM0NTY3ODkwMQAAAAA3",
                "conversationId": "AAQkAGExM2FiYjQ0LTY3ODktNDEyMy05ODc2LTAxMjM0NTY3ODkwMQAQAJ2M3",
                "internetMessageId": "<msg-003@clifyx.com>",
                "subject": "991284 - EP2026RA1122334 - Alex Mercer - DevOps Engineer - Citi - New York, NY",
                "receivedDateTime": "2026-07-20T11:00:00Z",
                "sentDateTime": "2026-07-20T10:59:00Z",
                "toRecipients": [{"emailAddress": {"address": "alex@directclient.com", "name": "Direct Client"}}],
                "ccRecipients": [],
            }
        ]
