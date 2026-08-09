"""
Application services for authorization orchestration, session management, and configuration.
"""

import hmac
import os
import secrets
from typing import Optional
from backend.app.domain.models import ConfigStatus, HealthStatus
from backend.app.infrastructure.keychain import KeychainAdapter
from backend.app.infrastructure.graph_stub import GraphAdapterStub


class SecurityService:
    """Manages local loopback session tokens and CSRF token validation."""
    
    def __init__(self, keychain: Optional[KeychainAdapter] = None):
        self.keychain = keychain or KeychainAdapter(use_memory_fallback=False)
        self._active_csrf_tokens: set[str] = set()
        # Pre-seed a default session token for local loopback manager
        self._master_csrf_secret = secrets.token_hex(32)

    def generate_csrf_token(self) -> str:
        """Generate a CSRF token for the local user session."""
        token = secrets.token_urlsafe(32)
        self._active_csrf_tokens.add(token)
        return token

    def validate_csrf_token(self, token: Optional[str]) -> bool:
        """Validate CSRF token header for mutating requests."""
        if not token:
            return False
        # Accept active token or timing-safe comparison with master token
        if token in self._active_csrf_tokens:
            return True
        return hmac.compare_digest(token, self._master_csrf_secret)


class ConfigService:
    """Provides readiness status and diagnostic information."""
    
    def __init__(self):
        self.graph_stub = GraphAdapterStub()

    def get_health_status(self) -> HealthStatus:
        return HealthStatus(status="ok", service="recruitment-follow-up-agent", version="1.0.0")

    def get_config_status(self) -> ConfigStatus:
        self.graph_stub.assert_permissions_allowed()
        graph_enabled = os.environ.get("GRAPH_ENABLED", "False").lower() == "true"
        drafts_enabled = os.environ.get("DRAFTS_ENABLED", "False").lower() == "true"
        mail_send_enabled = os.environ.get("MAIL_SEND_ENABLED", "False").lower() == "true"
        return ConfigStatus(
            status="ready",
            bound_address="127.0.0.1",
            time_zone="America/New_York",
            ollama_model="llama3.2:latest",
            graph_permissions="Mail.Read, Mail.ReadWrite (Mail.Send PROHIBITED)",
            mail_send_prohibited=True,
            secrets_redacted=True,
            graph_enabled=graph_enabled,
            drafts_enabled=drafts_enabled,
            draft_creation_available=graph_enabled and drafts_enabled and not mail_send_enabled,
        )
