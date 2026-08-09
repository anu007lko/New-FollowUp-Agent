"""
Regression tests for the metadata read-path and record-detail endpoint.
Uses an isolated temporary database — zero mutations to the authoritative database.
"""
import json
import os
import tempfile
import pytest

os.environ["ENVIRONMENT"] = "test"

from backend.app.infrastructure.persistence import EncryptedPersistenceEngine, _coerce_notes


# --- Test _coerce_notes helper ---

class TestCoerceNotes:
    def test_string_passthrough(self):
        assert _coerce_notes("hello") == "hello"

    def test_empty_string(self):
        assert _coerce_notes("") == ""

    def test_none_returns_empty(self):
        assert _coerce_notes(None) == ""

    def test_list_single_empty(self):
        """Authoritative payload stores manager_notes as [''] — should coerce to ''."""
        assert _coerce_notes(['']) == ""

    def test_list_with_content(self):
        assert _coerce_notes(['note1', 'note2']) == "note1\nnote2"

    def test_list_mixed_empty(self):
        assert _coerce_notes(['', 'real note', '']) == "real note"


# --- Test metadata extraction from payload ---

def _make_test_engine():
    """Create an EncryptedPersistenceEngine with an isolated temp database."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_records.db")
    engine = EncryptedPersistenceEngine(db_path=db_path, master_key="test-key-for-unit-tests")
    return engine


def _insert_test_record(engine, payload_dict, record_id="test-rec-1"):
    """Insert a record directly into the test database."""
    import sqlite3
    payload_json = json.dumps(payload_dict)
    cipher = engine.encryptor.encrypt(payload_json)
    with engine._get_connection() as conn:
        conn.execute("""
            INSERT INTO submission_records
            (id, graph_immutable_id, conversation_id, job_id, ep_reference,
             candidate_name, tcs_eligibility, domain_status, received_at, created_at,
             payload_ciphertext, record_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record_id, "AAMkAGTest", "AAQkAGTest",
            None, None, None,  # Let payload supply these
            "eligible", "NewSubmission",
            "2026-07-01T10:00:00Z", "2026-07-01T10:00:00Z",
            cipher, 1
        ))
        conn.commit()


class TestMetadataExtraction:
    """Test that skill/customer/location are read from the correct payload path."""

    def test_top_level_metadata_extraction(self):
        """Current format: metadata at top level of payload."""
        engine = _make_test_engine()
        payload = {
            "skill": "Python Developer",
            "customer": "Acme Corp",
            "location": "Remote",
            "job_id": "123456",
            "ep_reference": "EP-100",
            "candidate_name": "Test Candidate",
            "manager_notes": [""],
            "system_notes": "",
            "thread_messages": [
                {
                    "id": "AAMkAGTest",
                    "from": {"emailAddress": {"name": "Recruiter", "address": "recruiter@test.com"}},
                    "sentDateTime": "2026-07-01T10:00:00Z",
                    "receivedDateTime": "2026-07-01T10:00:00Z",
                    "subject": "Candidate Submission",
                    "bodyPreview": "Please review this candidate.",
                    "body": {"content": "Please review this candidate.", "contentType": "text"},
                    "toRecipients": [{"emailAddress": {"address": "manager@test.com"}}],
                    "ccRecipients": [],
                    "internetMessageId": "<test@test.com>",
                }
            ],
        }
        _insert_test_record(engine, payload)

        # Test list_records
        headers = engine.list_records()
        assert len(headers) == 1
        h = headers[0]
        assert h.skill == "Python Developer"
        assert h.customer == "Acme Corp"
        assert h.location == "Remote"

        # Test get_record_by_id
        rec = engine.get_record_by_id("test-rec-1")
        assert rec is not None
        assert rec.skill == "Python Developer"
        assert rec.customer == "Acme Corp"
        assert rec.location == "Remote"
        assert rec.manager_notes == ""  # coerced from ['']

    def test_missing_display_metadata_falls_back_to_original_subject(self):
        """Legacy records remain usable when parsed metadata was not persisted."""
        engine = _make_test_engine()
        payload = {
            "candidate_name": "Test Candidate",
            "thread_messages": [{
                "id": "AAMkAGTest",
                "subject": "418881 -EP2026RA6870770 - Test Candidate - Technical Program Manager (TPM)- Oracle Cloud - Phoenix, AZ (Local Candidate)",
                "from": {"emailAddress": {"address": "manager@test.com"}},
                "sentDateTime": "2026-07-01T10:00:00Z",
                "receivedDateTime": "2026-07-01T10:00:00Z",
                "bodyPreview": "Submission",
                "toRecipients": [],
                "ccRecipients": [],
                "internetMessageId": "<test@test.com>",
            }],
        }
        _insert_test_record(engine, payload)

        header = engine.list_records()[0]
        detail = engine.get_record_by_id("test-rec-1")
        assert header.skill == "Technical Program Manager (TPM)"
        assert header.customer == "Oracle Cloud"
        assert header.location == "Phoenix, AZ (Local Candidate)"
        assert detail.skill == header.skill
        assert detail.customer == header.customer
        assert detail.location == header.location

    def test_legacy_nested_metadata_extraction(self):
        """Legacy format: metadata nested under payload.metadata dict."""
        engine = _make_test_engine()
        payload = {
            "metadata": {
                "skill": "Java Developer",
                "customer": "Widget Inc",
                "location": "NYC",
            },
            "job_id": "654321",
            "ep_reference": "EP-200",
            "candidate_name": "Legacy Candidate",
            "manager_notes": "",
            "system_notes": "",
            "thread_messages": [
                {
                    "id": "AAMkAGTest2",
                    "from": {"emailAddress": {"name": "Recruiter", "address": "recruiter@test.com"}},
                    "sentDateTime": "2026-07-01T10:00:00Z",
                    "receivedDateTime": "2026-07-01T10:00:00Z",
                    "subject": "Candidate Submission",
                    "bodyPreview": "Legacy submission.",
                    "body": {"content": "Legacy submission.", "contentType": "text"},
                    "toRecipients": [{"emailAddress": {"address": "manager@test.com"}}],
                    "ccRecipients": [],
                    "internetMessageId": "<test2@test.com>",
                }
            ],
        }
        _insert_test_record(engine, payload, record_id="test-rec-2")

        headers = engine.list_records()
        assert len(headers) == 1
        h = headers[0]
        assert h.skill == "Java Developer"
        assert h.customer == "Widget Inc"
        assert h.location == "NYC"

    def test_missing_metadata_shows_none(self):
        """When neither top-level nor nested metadata exists, fields should be None."""
        engine = _make_test_engine()
        payload = {
            "job_id": "999999",
            "candidate_name": "No Metadata",
            "manager_notes": "",
            "system_notes": "",
            "thread_messages": [
                {
                    "id": "AAMkAGTest3",
                    "from": {"emailAddress": {"name": "R", "address": "r@test.com"}},
                    "sentDateTime": "2026-07-01T10:00:00Z",
                    "receivedDateTime": "2026-07-01T10:00:00Z",
                    "subject": "Sub",
                    "bodyPreview": "Body",
                    "body": {"content": "Body", "contentType": "text"},
                    "toRecipients": [{"emailAddress": {"address": "m@test.com"}}],
                    "ccRecipients": [],
                    "internetMessageId": "<test3@test.com>",
                }
            ],
        }
        _insert_test_record(engine, payload, record_id="test-rec-3")

        headers = engine.list_records()
        h = headers[0]
        assert h.skill is None
        assert h.customer is None
        assert h.location is None

    def test_interview_fields_surfaced_in_header(self):
        """feedback_due_at, interview_state, interview_updated_at should appear in headers."""
        engine = _make_test_engine()
        payload = {
            "candidate_name": "Interview Candidate",
            "manager_notes": "",
            "system_notes": "",
            "feedback_due_at": "2026-08-10T17:00:00Z",
            "interview_state": "AWAITING_FEEDBACK",
            "interview_updated_at": "2026-08-05T14:30:00Z",
            "thread_messages": [
                {
                    "id": "AAMkAGTest4",
                    "from": {"emailAddress": {"name": "R", "address": "r@test.com"}},
                    "sentDateTime": "2026-07-01T10:00:00Z",
                    "receivedDateTime": "2026-07-01T10:00:00Z",
                    "subject": "Sub",
                    "bodyPreview": "Body",
                    "body": {"content": "Body", "contentType": "text"},
                    "toRecipients": [{"emailAddress": {"address": "m@test.com"}}],
                    "ccRecipients": [],
                    "internetMessageId": "<test4@test.com>",
                }
            ],
        }
        _insert_test_record(engine, payload, record_id="test-rec-4")

        headers = engine.list_records()
        h = headers[0]
        assert h.feedback_due_at == "2026-08-10T17:00:00Z"
        assert h.interview_state == "AWAITING_FEEDBACK"
        assert h.interview_updated_at == "2026-08-05T14:30:00Z"

    def test_record_detail_with_list_manager_notes(self):
        """Regression: manager_notes stored as list should not crash get_record_by_id."""
        engine = _make_test_engine()
        payload = {
            "candidate_name": "Notes Test",
            "manager_notes": ["Manager said something", "Another note"],
            "system_notes": [""],
            "thread_messages": [
                {
                    "id": "AAMkAGTest5",
                    "from": {"emailAddress": {"name": "R", "address": "r@test.com"}},
                    "sentDateTime": "2026-07-01T10:00:00Z",
                    "receivedDateTime": "2026-07-01T10:00:00Z",
                    "subject": "Sub",
                    "bodyPreview": "Body",
                    "body": {"content": "Body", "contentType": "text"},
                    "toRecipients": [{"emailAddress": {"address": "m@test.com"}}],
                    "ccRecipients": [],
                    "internetMessageId": "<test5@test.com>",
                }
            ],
        }
        _insert_test_record(engine, payload, record_id="test-rec-5")

        rec = engine.get_record_by_id("test-rec-5")
        assert rec is not None
        assert isinstance(rec.manager_notes, str)
        assert "Manager said something" in rec.manager_notes
        assert "Another note" in rec.manager_notes
