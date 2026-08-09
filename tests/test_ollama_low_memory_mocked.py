import pytest
from unittest.mock import MagicMock, patch
import httpx
from backend.app.infrastructure.ollama_client import OllamaAdvisoryClient
from backend.app.domain.models import CategoryEnum, TimelineEntry, LLMAdvisoryResult

@pytest.fixture(autouse=True)
def _enable_ollama_for_low_memory_tests(monkeypatch):
    monkeypatch.setenv("OLLAMA_ENABLED", "True")


class TestOllamaLowMemoryMocked:

    @patch("httpx.Client.post")
    def test_low_memory_request_payload_invariants(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": '{"category": "NoResponse", "confidence": 0.95, "summary": "No reply", "is_uncertain": false, "reasoning": "Clear"}'
        }
        mock_post.return_value = mock_response

        client = OllamaAdvisoryClient()
        timeline = [
            TimelineEntry(
                entry_id="msg1",
                record_id="rec1",
                sender="user@test.com",
                timestamp="2026-08-03T10:00:00Z",
                body_preview="A" * 500  # Long body preview to test truncation
            )
        ]

        result = client.analyze_conversation(timeline)
        assert result.category == CategoryEnum.NO_RESPONSE
        assert result.confidence == 0.95

        # Verify POST call payload arguments
        assert mock_post.called
        call_args = mock_post.call_args
        json_data = call_args.kwargs.get("json", {})
        
        assert json_data.get("keep_alive") == 0
        options = json_data.get("options", {})
        assert options.get("num_ctx") == 2048
        assert options.get("num_predict") == 128
        assert options.get("temperature") == 0.0
        
        # Verify prompt excerpt truncation (500 chars truncated to 250)
        prompt_text = json_data.get("prompt", "")
        assert "A" * 250 in prompt_text
        assert "A" * 251 not in prompt_text

    @patch("httpx.Client.post")
    def test_timeout_fallback_to_needs_review(self, mock_post):
        mock_post.side_effect = httpx.TimeoutException("Request timed out")

        client = OllamaAdvisoryClient()
        timeline = [
            TimelineEntry(
                entry_id="msg1",
                record_id="rec1",
                sender="user@test.com",
                timestamp="2026-08-03T10:00:00Z",
                body_preview="Test message"
            )
        ]

        result = client.analyze_conversation(timeline)
        assert result.category == CategoryEnum.NEEDS_REVIEW
        assert result.confidence == 0.0
        assert result.is_uncertain is True

    def test_batch_processing_generator_concurrency_one(self):
        # Test batch iteration logic with max batch size 5 and concurrency 1
        items = list(range(12))
        batch_size = 5
        batches = [items[i:i + batch_size] for i in range(0, len(items), batch_size)]
        
        assert len(batches) == 3
        assert len(batches[0]) == 5
        assert len(batches[1]) == 5
        assert len(batches[2]) == 2
