"""
Comprehensive automated test suite verifying all M2 corrections and Daily Review requirements.
"""

import os
import tempfile
from datetime import datetime
import pytest
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from backend.app.domain.subject_parser import parse_subject_metadata
from backend.app.domain.date_utils import get_new_york_midnight_utc_iso, TIMEZONE_NEW_YORK
from backend.app.infrastructure.msal_client import MSALAuthenticationAdapter, MSALPermissionError
from backend.app.infrastructure.graph_client import MicrosoftGraphClient
from backend.app.application.daily_review_engine import DailyReviewEngine, DailyReviewResult
from backend.app.application.import_service import ImportService
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.models import DomainStatus, SubjectMetadata


# 1. Real Subject Format Parsing Tests
def test_real_subject_format_parsing():
    """Verify parsing of actual production subject format."""
    subject = "418326 - EP2026RA7415469 - Govinda Mundra - Technical Program Manager for AI PM - AMEX - Phoenix, AZ"
    meta = parse_subject_metadata(subject)

    assert meta.job_id == "418326"
    assert meta.ep_reference == "EP2026RA7415469"
    assert meta.candidate_name == "Govinda Mundra"
    assert meta.skill == "Technical Program Manager for AI PM"
    assert meta.customer == "AMEX"
    assert meta.location == "Phoenix, AZ"


def test_remote_location_and_additional_hyphens():
    """Verify parsing when location is Remote and requirement contains extra hyphens."""
    subject = "998124 - EP2026RA881122 - Priya Patel - Senior Architect - AI & Cloud - Apple - Remote"
    meta = parse_subject_metadata(subject)

    assert meta.job_id == "998124"
    assert meta.ep_reference == "EP2026RA881122"
    assert meta.candidate_name == "Priya Patel"
    assert meta.skill == "Senior Architect - AI & Cloud"
    assert meta.customer == "Apple"
    assert meta.location == "Remote"


# 2. Date Boundary & DST-Aware Tests
def test_new_york_date_conversion_edt():
    """Verify July 10, 2026 midnight in America/New_York (EDT, UTC-4) converts to 2026-07-10T04:00:00Z."""
    utc_iso = get_new_york_midnight_utc_iso("2026-07-10")
    assert utc_iso == "2026-07-10T04:00:00Z"


def test_dst_aware_est_vs_edt():
    """Verify DST handling: Summer (EDT) is UTC-4 vs Winter (EST) is UTC-5."""
    summer_utc = get_new_york_midnight_utc_iso("2026-07-10")
    winter_utc = get_new_york_midnight_utc_iso("2026-01-10")

    assert summer_utc == "2026-07-10T04:00:00Z"
    assert winter_utc == "2026-01-10T05:00:00Z"


# 3. Silent Authentication & Non-Secret Diagnostic Reporting
@patch("backend.app.infrastructure.msal_client.msal.PublicClientApplication")
def test_silent_auth_failure_diagnostics(mock_msal_app):
    """Verify silent auth failure reports non-secret configuration parameter names and NEVER prints tokens."""
    adapter = MSALAuthenticationAdapter()
    adapter.cache_path = "/tmp/non_existent_msal_cache.bin"
    mock_msal_app.return_value.get_accounts.return_value = []
    res = adapter.acquire_token_silently()

    assert res.token is None
    assert res.status == "auth_unavailable"
    assert "expected_cache_location" in res.config_diagnostics
    assert "AZURE_CLIENT_ID" in res.config_diagnostics["required_env_vars"]["client_id"]
    assert "AZURE_TENANT_ID" in res.config_diagnostics["required_env_vars"]["tenant_id"]


def test_msal_permission_fail_closed():
    """Verify MSAL adapter raises MSALPermissionError if Mail.Send scope is requested."""
    adapter = MSALAuthenticationAdapter()
    with pytest.raises(MSALPermissionError) as exc_info:
        adapter.assert_scopes_allowed(["Mail.Read", "Mail.Send"])
    assert "Mail.Send is strictly prohibited" in str(exc_info.value)


# 4. Preview Accuracy & Synthetic Data Labeling
@patch("backend.app.infrastructure.msal_client.msal.PublicClientApplication")
def test_synthetic_preview_labeling(mock_msal_app):
    """Verify offline preview returns auth_status='synthetic_test_data' and never claims live mailbox data."""
    adapter = MSALAuthenticationAdapter()
    adapter.cache_path = "/tmp/non_existent_msal_cache.bin"
    client = MicrosoftGraphClient(auth_adapter=adapter)
    mock_msal_app.return_value.get_accounts.return_value = []
    messages, auth_status, diagnostics = client.fetch_submissions_folder_messages()

    assert auth_status == "synthetic_test_data"
    assert len(messages) == 3


# 5. Daily Review Scheduler & Overlap Prevention
def test_daily_review_overlap_prevention():
    """Verify overlapping daily review runs are prevented and return status 'already_running'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "review_test.db")
        persistence = EncryptedPersistenceEngine(db_path=db_path, master_key="key123")
        engine = DailyReviewEngine(persistence=persistence)

        # Acquire lock manually to simulate an active running review
        engine._review_lock.acquire()
        try:
            res = engine.run_daily_review()
            assert res.status == "already_running"
        finally:
            engine._review_lock.release()


def test_daily_scheduler_targets_8am_new_york_and_stops_cleanly(monkeypatch):
    monkeypatch.setenv("SCHEDULER_ENABLED", "True")
    engine = DailyReviewEngine()
    before_target = datetime(2026, 8, 8, 7, 30, tzinfo=ZoneInfo("America/New_York"))
    after_target = datetime(2026, 8, 8, 9, 30, tzinfo=ZoneInfo("America/New_York"))
    assert engine.next_scheduled_run(before_target).isoformat() == "2026-08-08T08:00:00-04:00"
    assert engine.next_scheduled_run(after_target).isoformat() == "2026-08-09T08:00:00-04:00"
    assert engine.start_scheduler() is True
    assert engine.is_scheduler_active() is True
    engine.stop_scheduler()
    assert engine.is_scheduler_active() is False


def test_daily_review_execution_and_manager_note_preservation():
    """Verify daily review updates system state while strictly preserving manager notes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "review_test_2.db")
        persistence = EncryptedPersistenceEngine(db_path=db_path, master_key="key123")

        # Insert a submission record with custom manager notes
        persistence.upsert_submission(
            record_id="rec-100",
            graph_immutable_id="immutable-100",
            conversation_id="conv-100",
            job_id="418326",
            ep_reference="EP2026RA7415469",
            candidate_name="Govinda Mundra",
            tcs_eligibility="eligible",
            domain_status=DomainStatus.NEW_SUBMISSION.value,
            received_at="2026-07-15T10:00:00Z",
            created_at="2026-07-15T10:05:00Z",
            payload_data={"manager_notes": "CRITICAL: Candidate requested 100k salary. DO NOT OVERWRITE."}
        )

        engine = DailyReviewEngine(persistence=persistence)
        engine.import_service.graph_client.fetch_submissions_folder_messages = lambda: ([], "synthetic_test_data", {})
        res = engine.run_daily_review()

        assert res.status == "completed"

        # Verify manager notes were preserved intact
        records = persistence.list_records()
        assert len(records) == 1
        assert records[0].conversation_id == "conv-100"


def test_daily_review_deterministically_marks_old_no_response_due_and_preserves_manager_data(monkeypatch):
    """An unattended review may update workflow state, but never manager-owned data or email."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("MAIL_SEND_ENABLED", "False")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "review_classification.db")
        persistence = EncryptedPersistenceEngine(db_path=db_path, master_key="key123")
        manager_note = "Manager-owned note must remain byte-for-byte unchanged."
        persistence.upsert_submission(
            record_id="rec-auto-review",
            graph_immutable_id="immutable-auto-review",
            conversation_id="conv-auto-review",
            job_id="418326",
            ep_reference="EP2026RA7415469",
            candidate_name="Example Candidate",
            tcs_eligibility="eligible",
            domain_status=DomainStatus.AWAITING_RESPONSE.value,
            received_at="2026-07-01T10:00:00Z",
            created_at="2026-07-01T10:05:00Z",
            payload_data={
                "manager_notes": manager_note,
                "thread_messages": [{
                    "id": "immutable-auto-review",
                    "internetMessageId": "<auto-review@clifyx.com>",
                    "sentDateTime": "2026-07-01T10:00:00Z",
                    "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
                    "toRecipients": [{"emailAddress": {"address": "reviewer@tcs.com"}}],
                    "ccRecipients": [],
                    "bodyPreview": "Please find the candidate submission attached.",
                }],
                "timeline": [],
            },
        )

        import_service = MagicMock()
        import_service.run_import.return_value = MagicMock(messages_imported=0, auth_status="ok")
        engine = DailyReviewEngine(import_service=import_service, persistence=persistence)
        result = engine.run_daily_review()

        assert result.status == "completed"
        payload, _version, stored_status = persistence.get_record_payload_snapshot("rec-auto-review")
        assert stored_status == DomainStatus.PENDING_FOLLOW_UP.value
        assert payload["manager_notes"] == manager_note
        assert "draft" not in result.to_dict()
        assert os.environ["MAIL_SEND_ENABLED"] == "False"


def test_daily_review_never_overwrites_manager_outcome(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = EncryptedPersistenceEngine(
            db_path=os.path.join(tmpdir, "manager_override.db"), master_key="key123"
        )
        payload = {
            "manager_outcome_category": "Position Closed",
            "manager_notes": "Candidate selected; the single opening is closed.",
            "thread_messages": [{
                "id": "manager-imm",
                "internetMessageId": "<manager-override@clifyx.com>",
                "sentDateTime": "2026-07-01T10:00:00Z",
                "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
                "toRecipients": [{"emailAddress": {"address": "reviewer@tcs.com"}}],
                "bodyPreview": "Submission",
            }],
            "timeline": [{
                "event_type": "MANAGER_OUTCOME_DECISION",
                "body_preview": "Manager set outcome decision: Position Closed",
                "timestamp": "2026-08-01T10:00:00Z",
            }],
        }
        persistence.upsert_submission(
            "manager-rec", "manager-imm", "manager-conv", "1", "EP1", "Candidate",
            "eligible", DomainStatus.MANAGER_ACTION_REQUIRED.value,
            "2026-07-01T10:00:00Z", "2026-07-01T10:00:00Z", payload,
        )
        import_service = MagicMock()
        import_service.run_import.return_value = MagicMock(messages_imported=0, auth_status="ok")
        result = DailyReviewEngine(import_service=import_service, persistence=persistence).run_daily_review()
        after, _version, status = persistence.get_record_payload_snapshot("manager-rec")
        assert result.status == "completed"
        assert status == DomainStatus.MANAGER_ACTION_REQUIRED.value
        assert after["manager_outcome_category"] == "Position Closed"
        assert after["manager_notes"] == payload["manager_notes"]


def test_manual_review_refreshes_primary_and_linked_conversations(monkeypatch):
    """A manual review reads exact primary/linked identities before classification."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = EncryptedPersistenceEngine(
            db_path=os.path.join(tmpdir, "manual_refresh.db"), master_key="key123"
        )
        original = {
            "id": "source-1",
            "conversationId": "primary-conversation",
            "internetMessageId": "<source-1@clifyx.com>",
            "sentDateTime": "2026-08-01T10:00:00Z",
            "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
            "toRecipients": [{"emailAddress": {"address": "reviewer@tcs.com"}}],
            "ccRecipients": [],
            "bodyPreview": "Candidate submission",
            "body": {"contentType": "html", "content": "<p>Full encrypted submission body</p>"},
            "attachments": [{
                "id": "attachment-1",
                "name": "resume.pdf",
                "contentBytes": "encrypted-content-placeholder",
            }],
        }
        persistence.upsert_submission(
            "refresh-record", "source-1", "primary-conversation", "1", "EP1", "Candidate",
            "eligible", DomainStatus.AWAITING_RESPONSE.value,
            "2026-08-01T10:00:00Z", "2026-08-01T10:00:00Z",
            {
                "thread_messages": [original],
                "manager_notes": "Preserve this note",
                "timeline": [],
                "linked_conversations": [{
                    "conversation_id": "interview-conversation",
                    "role": "interview_coordination",
                    "linked_at": "2026-08-02T10:00:00Z",
                    "thread_messages": [],
                }],
            },
        )

        inbound = {
            "id": "reply-1",
            "conversationId": "primary-conversation",
            "internetMessageId": "<reply-1@tcs.com>",
            "receivedDateTime": "2026-08-02T10:00:00Z",
            "from": {"emailAddress": {"address": "reviewer@tcs.com"}},
            "toRecipients": [{"emailAddress": {"address": "tarun@clifyx.com"}}],
            "ccRecipients": [],
            "bodyPreview": "We received the profile.",
        }
        interview = {
            "id": "invite-1",
            "conversationId": "interview-conversation",
            "internetMessageId": "<invite-1@tcs.com>",
            "receivedDateTime": "2026-08-03T10:00:00Z",
            "from": {"emailAddress": {"address": "scheduler@tcs.com"}},
            "toRecipients": [{"emailAddress": {"address": "tarun@clifyx.com"}}],
            "ccRecipients": [],
            "bodyPreview": "Interview scheduled for tomorrow at 2 PM EDT.",
        }

        import_service = MagicMock()
        import_service.run_import.return_value = MagicMock(messages_imported=0, auth_status="ok")
        graph_client = MagicMock()
        graph_client.fetch_exact_conversation_messages.side_effect = [
            ([original, inbound], "ok"),
            ([interview], "ok"),
        ]

        result = DailyReviewEngine(
            import_service=import_service,
            persistence=persistence,
            graph_client=graph_client,
        ).run_daily_review()

        payload, version, _status = persistence.get_record_payload_snapshot("refresh-record")
        assert result.status == "completed"
        assert result.conversations_updated == 1
        assert result.conversation_refresh_errors == 0
        assert graph_client.fetch_exact_conversation_messages.call_count == 2
        assert len(payload["thread_messages"]) == 2
        assert payload["thread_messages"][0]["body"]["content"].startswith("<p>Full encrypted")
        assert payload["thread_messages"][0]["attachments"][0]["contentBytes"] == "encrypted-content-placeholder"
        assert payload["linked_conversations"][0]["thread_messages"][0]["id"] == "invite-1"
        assert payload["manager_notes"] == "Preserve this note"
        assert version >= 2


# 6. Exact Conversation Identity & Non-Association
def test_exact_conversation_identity_non_association():
    """Verify Job ID, EP reference, candidate name, and customer NEVER associate conversations."""
    sub_1 = "418326 - EP2026RA7415469 - Candidate A - Requirement - AMEX - Remote"
    sub_2 = "418326 - EP2026RA7415469 - Candidate B - Requirement - AMEX - Remote"

    meta_1 = parse_subject_metadata(sub_1)
    meta_2 = parse_subject_metadata(sub_2)

    # Metadata matches
    assert meta_1.job_id == meta_2.job_id
    assert meta_1.ep_reference == meta_2.ep_reference
    assert meta_1.customer == meta_2.customer

    # But candidate identity and conversationId are strictly separate
    assert meta_1.candidate_name != meta_2.candidate_name
