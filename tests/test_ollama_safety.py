import pytest
import os
import httpx
from unittest.mock import patch, MagicMock
from backend.app.infrastructure.ollama_client import OllamaAdvisoryClient
from backend.app.domain.models import TimelineEntry, CategoryEnum, DomainStatus

def test_default_disabled_behavior(monkeypatch):
    """Prove that with default env (OLLAMA_ENABLED not set or False), execution is rejected without network calls."""
    monkeypatch.setenv("OLLAMA_ENABLED", "False")
    client = OllamaAdvisoryClient()
    
    # 1. is_available
    assert client.is_available() is False
    
    # 2. check_preflight
    pref = client.check_preflight()
    assert pref.is_available is False
    assert pref.reason == "ollama_disabled"
    
    # 3. analyze_conversation
    res = client.analyze_conversation([])
    assert res.category == CategoryEnum.NEEDS_REVIEW
    assert "disabled" in res.reasoning.lower()
    
    # 4. suggest_reply
    reply = client.suggest_reply([], candidate_name="Jane Doe", requirement_name="Engineer")
    assert reply.is_eligible is True
    assert "Jane Doe" in reply.suggested_text
    assert "disabled" in reply.reasoning.lower()

def test_memory_limits_in_analyze_conversation(monkeypatch):
    """Prove num_ctx: 2048, num_predict: 128, keep_alive: 0 are sent in analyze_conversation payload."""
    monkeypatch.setenv("OLLAMA_ENABLED", "True")
    client = OllamaAdvisoryClient()
    
    timeline = [
        TimelineEntry(entry_id="e1", record_id="r1", sender="a@b.com", timestamp="2026-08-01T00:00:00Z", body_preview="Hello")
    ]
    
    with patch("httpx.Client.post") as mock_post:
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {
            "response": '{"category": "Acknowledgement", "confidence": 0.9, "summary": "Ack", "is_uncertain": false}'
        }
        mock_post.return_value = mock_res
        
        client.analyze_conversation(timeline)
        
        assert mock_post.called
        kwargs = mock_post.call_args[1]
        payload = kwargs["json"]
        
        assert payload["keep_alive"] == 0
        assert payload["options"]["num_ctx"] == 2048
        assert payload["options"]["num_predict"] == 128
        assert payload["options"]["temperature"] == 0.0

def test_memory_limits_in_suggest_reply(monkeypatch):
    """Prove num_ctx: 2048, num_predict: 128, keep_alive: 0 are sent in suggest_reply payload."""
    monkeypatch.setenv("OLLAMA_ENABLED", "True")
    client = OllamaAdvisoryClient()
    
    timeline = [
        TimelineEntry(entry_id="e1", record_id="r1", sender="a@b.com", timestamp="2026-08-01T00:00:00Z", body_preview="Hello")
    ]
    
    with patch("httpx.Client.post") as mock_post:
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {
            "response": '{"suggested_text": "Hi, following up...", "reasoning": "Standard"}'
        }
        mock_post.return_value = mock_res
        
        client.suggest_reply(timeline, candidate_name="Candidate A", requirement_name="Role B")
        
        assert mock_post.called
        kwargs = mock_post.call_args[1]
        payload = kwargs["json"]
        
        assert payload["keep_alive"] == 0
        assert payload["options"]["num_ctx"] == 2048
        assert payload["options"]["num_predict"] == 128

def test_direct_real_ollama_access_blocked_in_tests():
    """Prove that an unmocked real network call to Ollama (11434) is blocked by test guard."""
    with pytest.raises(RuntimeError) as exc_info:
        with httpx.Client(timeout=1.0) as client:
            client.get("http://127.0.0.1:11434/api/tags")
    assert "REAL OLLAMA NETWORK CALL BLOCKED IN TESTS" in str(exc_info.value)
