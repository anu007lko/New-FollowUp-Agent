"""
Automated tests for macOS Keychain adapter.
"""

import sys
import pytest
from backend.app.infrastructure.keychain import KeychainAdapter, KeychainUnavailableError


def test_keychain_memory_fallback_injected_in_tests():
    """Verify KeychainAdapter stores and retrieves secrets when memory fallback is explicitly injected."""
    adapter = KeychainAdapter(service_prefix="test.service", use_memory_fallback=True)
    
    assert adapter.set_secret("master_key", "account_1", "secret_value_123") is True
    assert adapter.get_secret("master_key", "account_1") == "secret_value_123"
    
    assert adapter.delete_secret("master_key", "account_1") is True
    assert adapter.get_secret("master_key", "account_1") is None


def test_keychain_default_fails_closed():
    """Verify default KeychainAdapter (use_memory_fallback=False) does not use memory fallback."""
    adapter = KeychainAdapter(service_prefix="test.service", use_memory_fallback=False)
    assert adapter.use_memory_fallback is False
