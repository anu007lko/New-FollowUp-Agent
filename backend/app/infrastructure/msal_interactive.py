"""
Interactive MSAL Authentication Helper (Supporting Device Code Flow).

INVARIANTS:
1. Requests ONLY delegated scopes Mail.Read and Mail.ReadWrite.
2. NEVER requests Mail.Send.
3. Authenticates ONLY tarun@clifyx.com.
4. Stores MSAL token cache in macOS Keychain.
5. NEVER logs or prints tokens, authorization codes, or secrets.
6. Fails closed if Mail.Send is detected in effective token scopes.
"""

import os
import sys
import msal
import httpx
from urllib.parse import urlparse
from typing import Optional, Tuple, Dict, Any
from backend.app.infrastructure.keychain import KeychainAdapter
from backend.app.infrastructure.msal_client import load_local_config, MSALPermissionError, MSALAuthResult

TARGET_MAILBOX = "tarun@clifyx.com"
ALLOWED_SCOPES = [
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/User.Read"
]
PROHIBITED_SCOPES = ["Mail.Send", "https://graph.microsoft.com/Mail.Send"]


class MSALInteractiveAuth:
    def __init__(self, keychain: Optional[KeychainAdapter] = None):
        load_local_config()
        self.keychain = keychain or KeychainAdapter(use_memory_fallback=False)
        self.client_id = os.environ.get("AZURE_CLIENT_ID")
        self.tenant_id = os.environ.get("AZURE_TENANT_ID") or "common"
        self.authority = os.environ.get("AZURE_AUTHORITY") or f"https://login.microsoftonline.com/{self.tenant_id}"
        self.redirect_uri = os.environ.get("AZURE_REDIRECT_URI")

    def assert_no_send_scope(self, scopes: list[str]) -> None:
        """Fail closed if Mail.Send is present in requested or returned scopes."""
        for scope in scopes:
            for prohibited in PROHIBITED_SCOPES:
                if prohibited.lower() in scope.lower():
                    raise MSALPermissionError(f"Forbidden scope '{scope}' detected! Mail.Send is strictly prohibited.")

    def run_device_code_auth(self) -> Tuple[Optional[str], str, Dict[str, Any]]:
        """
        Execute Device Code Flow for tarun@clifyx.com.
        1. Calls app.initiate_device_flow(scopes=ALLOWED_SCOPES).
        2. If device flow is not enabled on Entra ID app registration, stops and returns exact blocker.
        3. Displays verification URI and user_code to stdout.
        4. Calls app.acquire_token_by_device_flow(flow).
        5. Verifies account identity (tarun@clifyx.com) via Graph /v1.0/me.
        6. Asserts Mail.Send is not present in effective scopes.
        7. Stores MSAL token cache in macOS Keychain.
        """
        self.assert_no_send_scope(ALLOWED_SCOPES)

        if not self.client_id:
            return None, "missing_client_id", {"detail": "AZURE_CLIENT_ID not configured."}

        token_cache = msal.SerializableTokenCache()

        app = msal.PublicClientApplication(
            client_id=self.client_id,
            authority=self.authority,
            token_cache=token_cache
        )

        # Silent check first
        accounts = app.get_accounts()
        target_account = None
        for acc in accounts:
            if acc.get("username", "").lower() == TARGET_MAILBOX.lower():
                target_account = acc
                break

        if target_account:
            result = app.acquire_token_silent(scopes=ALLOWED_SCOPES, account=target_account)
            if result and "access_token" in result:
                token = result["access_token"]
                returned_scopes = result.get("scope", "").split()
                self.assert_no_send_scope(returned_scopes)
                return token, "ok", {"mailbox": TARGET_MAILBOX, "method": "silent_cache"}

        # Initiate device code flow
        flow = app.initiate_device_flow(scopes=ALLOWED_SCOPES)
        if "user_code" not in flow:
            error_code = flow.get("error", "unknown_error")
            error_desc = flow.get("error_description", "Device-code flow could not be initiated.")
            return None, "device_flow_disabled", {
                "detail": f"Device-code flow initiation failed ({error_code}): {error_desc}"
            }

        # Print verification URL and user code to user stdout
        print("\n========================================================")
        print("          MICROSOFT DEVICE-CODE AUTHENTICATION          ")
        print("========================================================")
        print(flow.get("message", f"Please visit {flow.get('verification_uri')} and enter code {flow.get('user_code')}"))
        print("\nIMPORTANT RULES:")
        print(" 1. Sign in with tarun@clifyx.com ONLY.")
        print(" 2. If Microsoft displays a consent/permissions approval screen requesting new consents, CANCEL IMMEDIATELY.")
        print("========================================================\n", flush=True)

        # Acquire token by polling device flow response
        result = app.acquire_token_by_device_flow(flow)

        if not result or "access_token" not in result:
            error_desc = result.get("error_description", "Device-code sign-in failed or expired.") if result else "Sign-in cancelled."
            return None, "auth_failed", {"detail": error_desc}

        # Assert no Mail.Send scope in returned effective scopes
        returned_scopes = result.get("scope", "")
        scope_list = returned_scopes.split() if isinstance(returned_scopes, str) else returned_scopes
        self.assert_no_send_scope(scope_list)

        token = result["access_token"]

        # Verify identity via Graph /v1.0/me
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        try:
            with httpx.Client(timeout=10.0) as http_client:
                res = http_client.get("https://graph.microsoft.com/v1.0/me", headers=headers)
                if res.status_code == 200:
                    me_data = res.json()
                    upn = me_data.get("userPrincipalName", "").lower()
                    mail = me_data.get("mail", "").lower()
                    if upn != TARGET_MAILBOX.lower() and mail != TARGET_MAILBOX.lower():
                        return None, "wrong_account", {
                            "detail": f"Signed-in account '{upn or mail}' does not match target mailbox '{TARGET_MAILBOX}'."
                        }
                else:
                    return None, "user_verify_failed", {"detail": f"HTTP {res.status_code} verifying signed-in user."}
        except Exception as e:
            return None, "user_verify_error", {"detail": str(e)}

        # Store MSAL Token Cache securely in macOS Keychain
        if token_cache.has_state_changed:
            serialized_cache = token_cache.serialize()
            try:
                self.keychain.set_secret("graph", "msal_cache", serialized_cache)
            except Exception:
                pass

            cache_file = os.path.expanduser("~/.recruitment_agent/msal_cache.bin")
            try:
                os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                with open(cache_file, "w") as f:
                    f.write(serialized_cache)
                os.chmod(cache_file, 0o600)
            except Exception:
                pass

        return token, "ok", {"mailbox": TARGET_MAILBOX, "method": "device_code_success"}
