"""
Local Ollama LLM integration adapter boundary (M1 stub).
"""

class OllamaAdapterStub:
    """Stub representing local Ollama advisory integration for future milestones."""
    
    MODEL_NAME = "llama3.2:latest"
    
    def is_available(self) -> bool:
        """Check if local Ollama daemon is reachable."""
        return False
