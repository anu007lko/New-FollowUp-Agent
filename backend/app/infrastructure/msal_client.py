"""
MSAL Authentication Adapter supporting silent token refresh only.

INVARIANTS:
1. NEVER asks user to paste, export, or manually store raw access tokens.
2. Supports secure MSAL token cache with silent refresh only.
3. NEVER launches interactive login or consent screens.
4. NEVER prints tokens or secrets.
5. If cache/configuration is unavailable, reports ONLY required non-secret configuration names.
6. Fails closed if Mail.Send is present.
"""

import os
import json
import base64
import msal
from typing import Optional, Tuple, Dict, Any
from backend.app.infrastructure.keychain import KeychainAdapter


def load_local_config():
    """Safely load non-secret configuration parameters into os.environ if present."""
    config_file = os.path.expanduser("~/.recruitment_agent/config.env")
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if line_str and not line_str.startswith("#") and "=" in line_str:
                        k, v = line_str.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass


class MSALPermissionError(PermissionError):
    """Raised when prohibited permissions (such as Mail.Send) are present."""
    pass


class MSALAuthResult:
    def __init__(self, token: Optional[str], status: str, config_diagnostics: Dict[str, Any], identity: Optional[str] = None, scopes: Optional[list[str]] = None):
        self.token = token
        self.status = status  # "ok", "auth_unavailable", "permission_prohibited", "synthetic_test_data"
        self.config_diagnostics = config_diagnostics
        self.identity = identity
        self.scopes = scopes or []


class MSALAuthenticationAdapter:
    DEFAULT_CACHE_PATH = os.path.expanduser("~/.recruitment_agent/msal_cache.bin")
    ALLOWED_SCOPES = [
        "https://graph.microsoft.com/Mail.Read",
        "https://graph.microsoft.com/Mail.ReadWrite",
        "https://graph.microsoft.com/User.Read"
    ]
    PROHIBITED_SCOPES = ["https://graph.microsoft.com/Mail.Send", "Mail.Send"]

    def __init__(self, keychain: Optional[KeychainAdapter] = None):
        load_local_config()
        self.keychain = keychain or KeychainAdapter(use_memory_fallback=False)
        self.cache_path = self.DEFAULT_CACHE_PATH

    def get_non_secret_config_requirements(self) -> Dict[str, Any]:
        """Report non-secret configuration parameter names and cache location."""
        return {
            "expected_cache_location": self.cache_path,
            "keychain_service_name": "com.clifyx.recruitment-follow-up.graph",
            "required_env_vars": {
                "client_id": "AZURE_CLIENT_ID",
                "tenant_id": "AZURE_TENANT_ID",
                "authority": "AZURE_AUTHORITY",
                "redirect_uri": "AZURE_REDIRECT_URI"
            },
            "configured_client_id_present": bool(os.environ.get("AZURE_CLIENT_ID")),
            "configured_tenant_id_present": bool(os.environ.get("AZURE_TENANT_ID")),
            "configured_redirect_uri_present": bool(os.environ.get("AZURE_REDIRECT_URI")),
            "msal_cache_file_exists": os.path.exists(self.cache_path)
        }

    def assert_scopes_allowed(self, scopes: list[str]) -> None:
        """Fail closed if Mail.Send is present in requested or effective scopes."""
        for scope in scopes:
            for prohibited in self.PROHIBITED_SCOPES:
                if prohibited.lower() in scope.lower():
                    raise MSALPermissionError(f"Forbidden scope '{scope}' detected. Mail.Send is strictly prohibited.")

    def acquire_token_silently(self) -> MSALAuthResult:
        """
        Attempt to acquire token silently from MSAL cache.
        NEVER launches interactive login or consent screens.
        NEVER prints tokens.
        """
        self.assert_scopes_allowed(self.ALLOWED_SCOPES)
        config_diag = self.get_non_secret_config_requirements()

        client_id = os.environ.get("AZURE_CLIENT_ID") or "00000000-0000-0000-0000-000000000000"
        tenant_id = os.environ.get("AZURE_TENANT_ID") or "common"
        authority = os.environ.get("AZURE_AUTHORITY") or f"https://login.microsoftonline.com/{tenant_id}"

        # Initialize MSAL Token Cache
        token_cache = msal.SerializableTokenCache()
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r") as f:
                    token_cache.deserialize(f.read())
            except Exception:
                pass

        # Try loading cache from Keychain if file cache empty
        if token_cache.has_state_changed is False:
            try:
                cache_str = self.keychain.get_secret("graph", "msal_cache")
                if cache_str:
                    token_cache.deserialize(cache_str)
            except Exception:
                pass

        # Build MSAL PublicClientApplication
        msal_app = msal.PublicClientApplication(
            client_id=client_id,
            authority=authority,
            token_cache=token_cache
        )

        expected_identity = os.environ.get("MANAGER_EMAIL", "tarun@clifyx.com").strip().lower()
        accounts = [a for a in msal_app.get_accounts() if (a.get("username") or "").strip().lower() == expected_identity]
        if not accounts:
            return MSALAuthResult(token=None, status="auth_unavailable", config_diagnostics=config_diag)

        # Attempt silent token acquisition
        result = msal_app.acquire_token_silent(scopes=self.ALLOWED_SCOPES, account=accounts[0])

        if result and "access_token" in result:
            # Check permissions on result scopes if present
            returned_scopes = result.get("scope", "").split() if isinstance(result.get("scope", ""), str) else result.get("scope", [])
            try:
                payload_b64 = result["access_token"].split(".")[1]
                payload_b64 += "=" * (-len(payload_b64) % 4)
                claims = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
            except Exception:
                return MSALAuthResult(token=None, status="identity_unverified", config_diagnostics=config_diag)
            effective_scopes = claims.get("scp", "").split()
            self.assert_scopes_allowed(returned_scopes + effective_scopes)
            effective_names = {s.lower().split("/")[-1] for s in effective_scopes}
            if not {"mail.read", "mail.readwrite"}.issubset(effective_names):
                return MSALAuthResult(token=None, status="required_scope_missing", config_diagnostics=config_diag)
            identity = (claims.get("preferred_username") or claims.get("upn") or accounts[0].get("username") or "").lower()
            if identity != expected_identity:
                return MSALAuthResult(token=None, status="identity_mismatch", config_diagnostics=config_diag)

            # Persist updated cache if refreshed silently with restrictive permissions
            if token_cache.has_state_changed:
                try:
                    os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
                    with open(self.cache_path, "w") as f:
                        f.write(token_cache.serialize())
                    os.chmod(self.cache_path, 0o600)
                except Exception:
                    pass

            return MSALAuthResult(token=result["access_token"], status="ok", config_diagnostics=config_diag, identity=identity, scopes=effective_scopes)

        return MSALAuthResult(token=None, status="auth_unavailable", config_diagnostics=config_diag)
