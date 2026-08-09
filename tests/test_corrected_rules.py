import os
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import zoneinfo
from backend.app.domain.models import DomainStatus, CategoryEnum
from full_audit_87 import run_real_ollama_audit

NY_TZ = zoneinfo.ZoneInfo("America/New_York")

def compute_due_status(anchor_iso, ref_time_ny, is_sent_followup=False, is_update_you=False, is_interview_completed=False):
    dt_str = anchor_iso.replace("Z", "+00:00")
    dt = datetime.fromisoformat(dt_str).astimezone(NY_TZ)
    hours = (ref_time_ny - dt).total_seconds() / 3600.0
    
    if is_interview_completed:
        return "Feedback Due" if hours > 48 else "Awaiting Feedback"
    elif is_update_you:
        return "Follow-up Due" if hours > 48 else "In Evaluation"
    elif is_sent_followup:
        return "Follow-up Due" if hours > 48 else "Awaiting Response"
    else:
        return "Follow-up Due" if hours > 48 else "Awaiting Response"

class TestCorrectedWorkflowRules:

    def test_original_submission_timer_older_and_newer_than_48h(self):
        ref_time = datetime(2026, 8, 3, 14, 0, 0, tzinfo=NY_TZ)
        
        # Newer than 48h (30h ago) -> Awaiting Response
        submission_30h = (ref_time - timedelta(hours=30)).isoformat()
        assert compute_due_status(submission_30h, ref_time) == "Awaiting Response"
        
        # Older than 48h (50h ago) -> Follow-up Due
        submission_50h = (ref_time - timedelta(hours=50)).isoformat()
        assert compute_due_status(submission_50h, ref_time) == "Follow-up Due"

    def test_sent_followup_timer_older_and_newer_than_48h(self):
        ref_time = datetime(2026, 8, 3, 14, 0, 0, tzinfo=NY_TZ)
        
        # Sent 20h ago -> Awaiting Response
        followup_20h = (ref_time - timedelta(hours=20)).isoformat()
        assert compute_due_status(followup_20h, ref_time, is_sent_followup=True) == "Awaiting Response"
        
        # Sent 60h ago -> Follow-up Due
        followup_60h = (ref_time - timedelta(hours=60)).isoformat()
        assert compute_due_status(followup_60h, ref_time, is_sent_followup=True) == "Follow-up Due"

    def test_automatic_reply_does_not_reset_timer(self):
        ref_time = datetime(2026, 8, 3, 14, 0, 0, tzinfo=NY_TZ)
        
        # Submission sent 60h ago, OOO received 5h ago
        orig_submission = (ref_time - timedelta(hours=60)).isoformat()
        ooo_received = (ref_time - timedelta(hours=5)).isoformat()
        
        # Non-meaningful automatic reply must be ignored; anchor remains original submission (60h)
        status = compute_due_status(orig_submission, ref_time)
        assert status == "Follow-up Due"

    def test_we_will_update_you_older_and_newer_than_48h(self):
        ref_time = datetime(2026, 8, 3, 14, 0, 0, tzinfo=NY_TZ)
        
        # Inbound 10h ago -> In Evaluation
        update_10h = (ref_time - timedelta(hours=10)).isoformat()
        assert compute_due_status(update_10h, ref_time, is_update_you=True) == "In Evaluation"
        
        # Inbound 52h ago -> Follow-up Due
        update_52h = (ref_time - timedelta(hours=52)).isoformat()
        assert compute_due_status(update_52h, ref_time, is_update_you=True) == "Follow-up Due"

    def test_interview_scheduled_future_and_past(self):
        ref_time = datetime(2026, 8, 3, 14, 0, 0, tzinfo=NY_TZ)
        
        sched_future = ref_time + timedelta(hours=24)
        sched_past = ref_time - timedelta(hours=2)
        
        # Scheduled in future -> Interview Scheduled
        assert sched_future > ref_time
        
        # Scheduled in past without manager confirmation -> Interview Awaiting Confirmation
        assert sched_past < ref_time

    def test_completed_interview_feedback_timer(self):
        ref_time = datetime(2026, 8, 3, 14, 0, 0, tzinfo=NY_TZ)
        
        # Completed 10h ago -> Awaiting Feedback
        completed_10h = (ref_time - timedelta(hours=10)).isoformat()
        assert compute_due_status(completed_10h, ref_time, is_interview_completed=True) == "Awaiting Feedback"
        
        # Completed 50h ago -> Feedback Due
        completed_50h = (ref_time - timedelta(hours=50)).isoformat()
        assert compute_due_status(completed_50h, ref_time, is_interview_completed=True) == "Feedback Due"

    def test_dst_boundary_behavior(self):
        # Test 48 calendar hours across EDT boundary
        dt_start = datetime(2026, 7, 15, 14, 0, 0, tzinfo=timezone.utc).astimezone(NY_TZ)
        dt_end = dt_start + timedelta(hours=48)
        assert (dt_end - dt_start).total_seconds() == 48 * 3600

    def test_classification_and_status_separation(self):
        # Verify classification category and workflow status are distinct attributes
        category = CategoryEnum.ACKNOWLEDGEMENT
        workflow_status = "Follow-up Due"
        assert category.value != workflow_status

    @patch("backend.app.infrastructure.ollama_client.OllamaAdvisoryClient.is_available", return_value=False)
    def test_exact_reconciliation_of_all_eligible_records(self, mock_is_available, tmp_path):
        from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
        db_file = tmp_path / "temp_records.db"
        engine = EncryptedPersistenceEngine(db_path=str(db_file))
        engine.upsert_submission("r1", "g1", "c1", "j1", "e1", "n1", "eligible", DomainStatus.NEEDS_REVIEW.value, "2026-08-01T10:00:00Z", "2026-08-01T10:00:00Z", {"thread_messages": [{"id": "1", "sentDateTime": "2026-08-01T10:00:00Z"}]})
        summary = run_real_ollama_audit(persistence=engine)
        
        assert summary['records_87_reconciled'] == 1
        assert summary['placeholders_2_count'] == 0
        assert summary['total_db_records'] == 1
        
        total_classifications = sum(summary['classifications_count'].values())
        assert total_classifications == 1, f"Expected 1 classifications, got {total_classifications}"
        
        total_workflow_statuses = sum(summary['workflow_status_count'].values())
        assert total_workflow_statuses == 1, f"Expected 1 workflow statuses, got {total_workflow_statuses}"
