import os
import pytest
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine


def test_test_environment_blocks_authoritative_database(monkeypatch):
    """Ensure opening or connecting to authoritative database in test mode raises RuntimeError."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    authoritative_db = os.path.expanduser("~/.recruitment_agent/records.db")

    with pytest.raises(RuntimeError, match="FATAL: Test mode attempted"):
        EncryptedPersistenceEngine(db_path=authoritative_db)


def test_default_constructor_in_test_mode_creates_temp_db(monkeypatch):
    """Ensure default constructor in test mode creates an isolated temporary database."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    engine = EncryptedPersistenceEngine()
    assert "records.db" not in engine.db_path or "test_records_" in engine.db_path
    assert os.path.expanduser("~/.recruitment_agent/records.db") != engine.db_path
    records = engine.list_records()
    assert len(records) == 0
