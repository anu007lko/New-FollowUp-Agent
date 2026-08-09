import os
import pytest
from backend.app.domain.models import DomainStatus, DashboardSummary
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine

def test_no_surrogate_status_mapping():
    """Prove that DomainStatus has explicit distinct values for AwaitingResponse and InterviewAwaitingConfirmation."""
    assert DomainStatus.AWAITING_RESPONSE == "AwaitingResponse"
    assert DomainStatus.INTERVIEW_AWAITING_CONFIRMATION == "InterviewAwaitingConfirmation"
    assert DomainStatus.AWAITING_RESPONSE != DomainStatus.NEW_SUBMISSION
    assert DomainStatus.INTERVIEW_AWAITING_CONFIRMATION != DomainStatus.AWAITING_FEEDBACK

def test_incomplete_records_excluded_from_needs_review(tmp_path):
    """Prove that database dashboard summary separates incomplete legacy placeholders from Needs Review."""
    db_file = tmp_path / "temp_records.db"
    persistence = EncryptedPersistenceEngine(db_path=str(db_file))
    
    # Seed 1 complete NeedsReview, 2 incomplete
    persistence.upsert_submission("r1", "g1", "c1", "j1", "e1", "n1", "eligible", DomainStatus.NEEDS_REVIEW.value, "2026-08-01T10:00:00Z", "2026-08-01T10:00:00Z", {"thread_messages": [{"id": "1", "sentDateTime": "2026-08-01T10:00:00Z"}]})
    persistence.upsert_submission("r2", "g2", "c2", "j2", "e2", "n2", "eligible", DomainStatus.NEW_SUBMISSION.value, "2026-08-01T10:00:00Z", "2026-08-01T10:00:00Z", {"thread_messages": []})
    persistence.upsert_submission("r3", "g3", "c3", "j3", "e3", "n3", "eligible", DomainStatus.NEW_SUBMISSION.value, "2026-08-01T10:00:00Z", "2026-08-01T10:00:00Z", {"thread_messages": []})
    
    summary = persistence.get_dashboard_summary()
    assert summary.total == 3
    assert summary.complete_records == 1
    assert summary.incomplete == 2
    assert summary.needs_review == 1

def test_dashboard_totals_reconcile(tmp_path):
    """Prove that operational status counts total exactly the complete records."""
    db_file = tmp_path / "temp_records.db"
    persistence = EncryptedPersistenceEngine(db_path=str(db_file))
    
    persistence.upsert_submission("r1", "g1", "c1", "j1", "e1", "n1", "eligible", DomainStatus.NEEDS_REVIEW.value, "2026-08-01T10:00:00Z", "2026-08-01T10:00:00Z", {"thread_messages": [{"id": "1", "sentDateTime": "2026-08-01T10:00:00Z"}]})
    persistence.upsert_submission("r2", "g2", "c2", "j2", "e2", "n2", "eligible", DomainStatus.PENDING_FOLLOW_UP.value, "2026-08-01T10:00:00Z", "2026-08-01T10:00:00Z", {"thread_messages": [{"id": "2", "sentDateTime": "2026-08-01T10:00:00Z"}]})
    
    summary = persistence.get_dashboard_summary()
    operational_total = (
        summary.pending_follow_up +
        summary.awaiting_response +
        summary.interview_awaiting_confirmation +
        summary.manager_action_required +
        summary.needs_review +
        summary.in_evaluation +
        summary.closed +
        summary.awaiting_feedback +
        summary.feedback_due
    )
    
    assert operational_total == summary.complete_records
    assert operational_total == 2
    assert summary.total == summary.complete_records + summary.incomplete
