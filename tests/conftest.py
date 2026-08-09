"""
Shared test fixtures.
By default, tests run against synthetic data and block any real network connections to Ollama.
"""
import os
import pytest
import httpx

os.environ["ENVIRONMENT"] = "test"


@pytest.fixture(autouse=True)
def _use_synthetic_data_for_tests(monkeypatch):
    """Ensure all existing tests use synthetic data provider unless explicitly overridden."""
    monkeypatch.setenv("USE_SYNTHETIC_DATA", "True")
    monkeypatch.setenv("ENVIRONMENT", "test")
    # Exercise draft routes through the guarded fake adapter only.
    monkeypatch.setenv("GRAPH_ENABLED", "True")
    monkeypatch.setenv("DRAFTS_ENABLED", "True")
    monkeypatch.setenv("MAIL_SEND_ENABLED", "False")


@pytest.fixture(autouse=True)
def block_real_ollama_network(monkeypatch):
    """
    Automatic test guard: Ensures real network calls to Ollama (127.0.0.1:11434)
    are strictly blocked in all tests. Unmocked network attempts raise RuntimeError.
    """
    # Ensure Ollama is disabled by default in test environment
    monkeypatch.setenv("OLLAMA_ENABLED", "False")

    original_send = httpx.Client.send

    def guarded_send(self, request, *args, **kwargs):
        url_str = str(request.url)
        if "11434" in url_str or "/api/generate" in url_str or "/api/chat" in url_str:
            raise RuntimeError(f"REAL OLLAMA NETWORK CALL BLOCKED IN TESTS: {url_str}")
        return original_send(self, request, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "send", guarded_send)
