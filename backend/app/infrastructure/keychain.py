"""
macOS Keychain interface for secure secret management.
Uses /usr/bin/security CLI on macOS. Fails closed if unavailable in normal runtime.
Allows in-memory store ONLY when explicitly injected via use_memory_fallback=True in automated tests.
"""

import sys
import subprocess
from typing import Optional, Dict


class KeychainUnavailableError(RuntimeError):
    """Raised when macOS Keychain security tool is unavailable or fails in production runtime."""
    pass


class KeychainAdapter:
    def __init__(self, service_prefix: str = "RecruitmentFollowUpAgent", use_memory_fallback: bool = False):
        self.service_prefix = service_prefix
        # Memory fallback is STRICTLY prohibited in normal runtime; allowed ONLY if explicitly passed by tests
        self.use_memory_fallback = use_memory_fallback
        self._memory_store: Dict[str, str] = {}
        self._security_path = "/usr/bin/security"

    def _make_key(self, service: str, account: str) -> str:
        return f"{self.service_prefix}.{service}:{account}"

    def set_secret(self, service: str, account: str, secret: str) -> bool:
        """Store secret in Keychain. Fails closed if unavailable unless test fallback is explicitly injected."""
        key = self._make_key(service, account)
        if self.use_memory_fallback:
            self._memory_store[key] = secret
            return True

        if sys.platform != "darwin":
            raise KeychainUnavailableError("macOS Keychain is only supported on macOS platform.")

        try:
            # Delete existing item first to allow clean overwrite
            self.delete_secret(service, account)
            cmd = [
                self._security_path,
                "add-generic-password",
                "-a", account,
                "-s", f"{self.service_prefix}.{service}",
                "-w", secret,
                "-U"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return res.returncode == 0
        except Exception as e:
            raise KeychainUnavailableError(f"Failed to access macOS Keychain: {str(e)}") from e

    def get_secret(self, service: str, account: str) -> Optional[str]:
        """Retrieve secret from Keychain. Fails closed if unavailable unless test fallback is explicitly injected."""
        key = self._make_key(service, account)
        if self.use_memory_fallback:
            return self._memory_store.get(key)

        if sys.platform != "darwin":
            raise KeychainUnavailableError("macOS Keychain is only supported on macOS platform.")

        try:
            cmd = [
                self._security_path,
                "find-generic-password",
                "-a", account,
                "-s", f"{self.service_prefix}.{service}",
                "-w"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                return res.stdout.strip()
            return None
        except Exception as e:
            raise KeychainUnavailableError(f"Failed to access macOS Keychain: {str(e)}") from e

    def delete_secret(self, service: str, account: str) -> bool:
        """Delete secret from Keychain. Fails closed if unavailable unless test fallback is explicitly injected."""
        key = self._make_key(service, account)
        if self.use_memory_fallback:
            if key in self._memory_store:
                del self._memory_store[key]
            return True

        if sys.platform != "darwin":
            raise KeychainUnavailableError("macOS Keychain is only supported on macOS platform.")

        try:
            cmd = [
                self._security_path,
                "delete-generic-password",
                "-a", account,
                "-s", f"{self.service_prefix}.{service}"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            return res.returncode == 0
        except Exception:
            return True
