"""
Automated integration tests for manual import preview and execution.
"""

import os
import tempfile
import pytest
from backend.app.application.import_service import ImportService
from backend.app.infrastructure.graph_client import MicrosoftGraphClient
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine


@pytest.fixture
def test_import_environment(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("USE_SYNTHETIC_DATA", "True")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "import_test.db")
        persistence = EncryptedPersistenceEngine(db_path=db_path, master_key="test_key_xyz")
        graph_client = MicrosoftGraphClient()
        graph_client.get_auth_status = lambda: (None, "synthetic_test_data", {})
        service = ImportService(graph_client=graph_client, persistence=persistence)
        yield service, persistence


def test_production_auth_failure_never_returns_synthetic(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("USE_SYNTHETIC_DATA", "True")
    client = MicrosoftGraphClient()
    client.get_auth_status = lambda: (None, "auth_unavailable", {})

    messages, status, _ = client.fetch_submissions_folder_messages()

    assert messages == []
    assert status == "auth_unavailable"


def test_import_preview_read_only(test_import_environment):
    """Verify preview mode is read-only, returns correct counts, and writes zero records to DB."""
    service, persistence = test_import_environment

    report = service.run_import(preview=True)

    assert report.is_preview is True
    assert report.messages_scanned == 3
    assert report.messages_eligible == 2
    assert report.excluded_count == 1
    assert len(report.items) == 3

    # Assert ZERO records were written to DB during preview
    records = persistence.list_records()
    assert len(records) == 0


def test_import_execution_idempotent(test_import_environment):
    """Verify execution mode persists eligible records and second run skips duplicates."""
    service, persistence = test_import_environment

    # Run 1: Execution
    report_1 = service.run_import(preview=False)
    assert report_1.is_preview is False
    assert report_1.messages_imported == 2
    assert report_1.duplicates_skipped == 0

    records_1 = persistence.list_records()
    assert len(records_1) == 2

    # Run 2: Re-run execution (Idempotency test)
    report_2 = service.run_import(preview=False)
    assert report_2.is_preview is False
    assert report_2.messages_imported == 0
    assert report_2.duplicates_skipped == 2

    records_2 = persistence.list_records()
    assert len(records_2) == 2
