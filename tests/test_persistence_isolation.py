import os
import pytest
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine

def test_test_mode_isolation_guard():
    # Set ENVIRONMENT=test
    os.environ["ENVIRONMENT"] = "test"
    
    # Attempting to explicitly initialize with authoritative db in test mode should raise RuntimeError
    authoritative_path = os.path.expanduser("~/.recruitment_agent/records.db")
    with pytest.raises(RuntimeError) as exc_info:
        engine = EncryptedPersistenceEngine(db_path=authoritative_path)
    
    assert "FATAL: Test mode attempted to connect to the authoritative database" in str(exc_info.value)
    
    # Providing a test path should succeed
    engine_safe = EncryptedPersistenceEngine(db_path=":memory:")
    assert engine_safe.db_path == ":memory:"
