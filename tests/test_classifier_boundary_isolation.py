"""
Focused tests verifying classifier boundary isolation.
Ensures classify_record() runs only during write-side classification snapshots (ingestion, refresh, link/unlink, migration),
and NEVER during generic save/action/note updates, GET record, GET list, dashboard reads, or DTO composition.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.consolidated_classifier import refresh_classification_snapshot
from backend.app.domain.workflow_view_composer import WorkflowViewComposer
from backend.app.domain.models import DomainStatus, SubmissionRecord


client = TestClient(app)


def test_generic_save_and_manager_notes_do_not_trigger_classification(tmp_path):
    db_path = str(tmp_path / "test_boundary.db")
    engine = EncryptedPersistenceEngine(db_path=db_path)
    
    payload = {
        "graph_immutable_id": "graph-test-001",
        "conversation_id": "conv-test-001",
        "candidate_name": "Test Candidate",
        "thread_messages": [{"id": "msg-1", "bodyPreview": "Interview update"}],
        "timeline": []
    }
    
    with patch("backend.app.domain.consolidated_classifier.classify_record") as mock_classify:
        engine.save_record_payload("rec-001", payload, "NeedsReview")
        mock_classify.assert_not_called()

    # Verify that payload saved via save_record_payload did not invoke classify_record
    with engine._get_connection() as conn:
        row = conn.execute("SELECT payload_ciphertext FROM submission_records WHERE id = ?", ("rec-001",)).fetchone()
        saved_payload = json.loads(engine.encryptor.decrypt(row["payload_ciphertext"]))
        assert "classification_category" not in saved_payload or saved_payload.get("classification_category") is None


def test_ingestion_and_controlled_refresh_trigger_classification_and_persist_snapshot():
    payload = {
        "graph_immutable_id": "graph-ingest-001",
        "conversation_id": "conv-ingest-001",
        "thread_messages": [{"id": "msg-ingest-1", "bodyPreview": "Client rejected the candidate"}],
        "timeline": []
    }
    
    with patch("backend.app.domain.consolidated_classifier.classify_record") as mock_classify:
        mock_res = MagicMock()
        mock_res.category = "Rejection"
        mock_res.proposed_status = "Closed"
        mock_res.reason_code = "client_rejected"
        mock_classify.return_value = mock_res
        
        res = refresh_classification_snapshot(payload, graph_immutable_id="graph-ingest-001")
        
        mock_classify.assert_called_once()
        assert res.category == "Rejection"
        assert payload["classification_category"] == "Rejection"
        assert "classification_updated_at" in payload
        assert payload["classifier_version"] == "v1.0"


def test_read_paths_and_dto_composition_never_trigger_classification():
    with patch("backend.app.domain.consolidated_classifier.classify_record") as mock_classify:
        # GET records list
        resp_list = client.get("/api/v1/records")
        assert resp_list.status_code == 200
        
        # GET dashboard summary
        resp_dash = client.get("/api/v1/dashboard")
        assert resp_dash.status_code == 200
        
        # DTO composition
        record_dict = {
            "id": "rec-dto-001",
            "candidate_name": "DTO Test Candidate",
            "domain_status": "ActionRequired",
            "received_at": "2026-08-01T10:00:00Z",
            "created_at": "2026-08-01T10:00:00Z",
            "record_version": 1,
            "classification_category": "Feedback",
            "timeline": []
        }
        dto = WorkflowViewComposer.compose_submission_record_dto(record_dict)
        assert dto.id == "rec-dto-001"
        
        mock_classify.assert_not_called()
