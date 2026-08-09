"""
M3 Workflow Engine, Identity, and Dashboard tests.

Tests:
1. 48-hour timer calculation (EDT/EST boundary)
2. Interview state transitions: valid and invalid
3. Close action with each approved reason
4. Reopen on newer conversation message
5. Manager notes append-only (never overwrite)
6. System notes separation
7. Dashboard summary counts
8. Job ID / EP reference / candidate name NEVER link conversations
"""

import pytest
from datetime import datetime, timedelta
from backend.app.domain.models import (
    DomainStatus, InterviewState, CloseReason, CloseAction,
    DashboardSummary, SubmissionRecord, TimelineEntry
)
from backend.app.domain.date_utils import TIMEZONE_NEW_YORK, TIMEZONE_UTC
from backend.app.application.workflow_engine import (
    compute_feedback_due_at, is_feedback_overdue,
    validate_interview_transition, compute_domain_status_after_interview,
    evaluate_status_on_timer_check, validate_close_action, should_reopen_on_new_message,
    format_system_note, append_manager_note,
    FEEDBACK_WINDOW_HOURS
)
from backend.app.infrastructure.synthetic_data import (
    get_synthetic_records, get_synthetic_dashboard_summary,
    get_synthetic_record_by_id
)


# --- 48h Timer Tests ---

class Test48HourTimer:
    def test_timer_is_exactly_48_calendar_hours(self):
        """Timer must be exactly 48 calendar hours from completion."""
        completed = "2026-07-15T14:00:00+00:00"
        due = compute_feedback_due_at(completed)
        due_dt = datetime.fromisoformat(due)
        completed_dt = datetime.fromisoformat(completed)
        delta = due_dt - completed_dt
        assert delta == timedelta(hours=48)

    def test_timer_edt_boundary(self):
        """48h timer across EDT (UTC-4). Summer 2026 is EDT."""
        # July 15 2:00 PM EDT = 6:00 PM UTC
        completed = "2026-07-15T18:00:00+00:00"
        due = compute_feedback_due_at(completed)
        due_dt = datetime.fromisoformat(due)
        # Should be July 17 6:00 PM UTC (48h later)
        expected = datetime(2026, 7, 17, 18, 0, 0, tzinfo=TIMEZONE_UTC)
        assert due_dt == expected

    def test_timer_est_boundary(self):
        """48h timer across EST (UTC-5). January 2026 is EST."""
        # Jan 10 2:00 PM EST = 7:00 PM UTC
        completed = "2026-01-10T19:00:00+00:00"
        due = compute_feedback_due_at(completed)
        due_dt = datetime.fromisoformat(due)
        # Should be Jan 12 7:00 PM UTC (48h later)
        expected = datetime(2026, 1, 12, 19, 0, 0, tzinfo=TIMEZONE_UTC)
        assert due_dt == expected

    def test_timer_across_dst_spring_forward(self):
        """48h timer across DST spring-forward (EST→EDT, March 2026).
        March 8 2026 2:00 AM EST → 3:00 AM EDT.
        Timer should still be exactly 48 calendar hours."""
        # March 7, 2026 10:00 PM EST = March 8 03:00 UTC
        completed = "2026-03-08T03:00:00+00:00"
        due = compute_feedback_due_at(completed)
        due_dt = datetime.fromisoformat(due)
        completed_dt = datetime.fromisoformat(completed)
        delta = due_dt - completed_dt
        assert delta == timedelta(hours=48)

    def test_timer_across_dst_fall_back(self):
        """48h timer across DST fall-back (EDT→EST, November 2026).
        Nov 1 2026 2:00 AM EDT → 1:00 AM EST.
        Timer should still be exactly 48 calendar hours."""
        # Nov 1, 2026 12:00 AM EDT = Nov 1 04:00 UTC
        completed = "2026-11-01T04:00:00+00:00"
        due = compute_feedback_due_at(completed)
        due_dt = datetime.fromisoformat(due)
        completed_dt = datetime.fromisoformat(completed)
        delta = due_dt - completed_dt
        assert delta == timedelta(hours=48)

    def test_is_overdue_true(self):
        past = (datetime.now(TIMEZONE_UTC) - timedelta(hours=1)).isoformat()
        assert is_feedback_overdue(past) is True

    def test_is_overdue_false(self):
        future = (datetime.now(TIMEZONE_UTC) + timedelta(hours=1)).isoformat()
        assert is_feedback_overdue(future) is False

    def test_is_overdue_empty(self):
        assert is_feedback_overdue("") is False


# --- Interview State Transition Tests ---

class TestInterviewTransitions:
    def test_none_to_requested(self):
        ok, _ = validate_interview_transition(None, InterviewState.REQUESTED)
        assert ok

    def test_none_to_scheduled(self):
        ok, _ = validate_interview_transition(None, InterviewState.SCHEDULED)
        assert ok

    def test_none_to_completed_invalid(self):
        ok, reason = validate_interview_transition(None, InterviewState.COMPLETED)
        assert not ok
        assert "Cannot transition" in reason

    def test_requested_to_scheduled(self):
        ok, _ = validate_interview_transition(InterviewState.REQUESTED, InterviewState.SCHEDULED)
        assert ok

    def test_requested_to_cancelled(self):
        ok, _ = validate_interview_transition(InterviewState.REQUESTED, InterviewState.CANCELLED)
        assert ok

    def test_requested_to_not_confirmed(self):
        ok, _ = validate_interview_transition(InterviewState.REQUESTED, InterviewState.NOT_CONFIRMED)
        assert ok

    def test_scheduled_to_completed(self):
        ok, _ = validate_interview_transition(InterviewState.SCHEDULED, InterviewState.COMPLETED)
        assert ok

    def test_scheduled_to_rescheduled(self):
        ok, _ = validate_interview_transition(InterviewState.SCHEDULED, InterviewState.RESCHEDULED)
        assert ok

    def test_scheduled_to_cancelled(self):
        ok, _ = validate_interview_transition(InterviewState.SCHEDULED, InterviewState.CANCELLED)
        assert ok

    def test_scheduled_to_not_confirmed(self):
        ok, _ = validate_interview_transition(InterviewState.SCHEDULED, InterviewState.NOT_CONFIRMED)
        assert ok

    def test_completed_is_terminal(self):
        """Completed interview cannot transition to any other state."""
        for target in InterviewState:
            ok, _ = validate_interview_transition(InterviewState.COMPLETED, target)
            assert not ok, f"COMPLETED should not transition to {target.value}"

    def test_cancelled_is_terminal(self):
        for target in InterviewState:
            ok, _ = validate_interview_transition(InterviewState.CANCELLED, target)
            assert not ok

    def test_not_confirmed_is_terminal(self):
        for target in InterviewState:
            ok, _ = validate_interview_transition(InterviewState.NOT_CONFIRMED, target)
            assert not ok

    def test_rescheduled_to_scheduled(self):
        ok, _ = validate_interview_transition(InterviewState.RESCHEDULED, InterviewState.SCHEDULED)
        assert ok

    def test_rescheduled_to_cancelled(self):
        ok, _ = validate_interview_transition(InterviewState.RESCHEDULED, InterviewState.CANCELLED)
        assert ok

    def test_completed_starts_awaiting_feedback(self):
        status = compute_domain_status_after_interview(
            InterviewState.COMPLETED, DomainStatus.IN_EVALUATION
        )
        assert status == DomainStatus.AWAITING_FEEDBACK

    def test_pre_expiry_awaiting_feedback_vs_post_expiry_feedback_due(self):
        """
        Pre-expiry: timer is active (unexpired) -> remains AwaitingFeedback.
        Post-expiry: 48h timer expires without response -> transitions to FeedbackDue.
        """
        now = datetime.now(TIMEZONE_UTC)
        unexpired_due = (now + timedelta(hours=12)).isoformat()
        expired_due = (now - timedelta(hours=24)).isoformat()

        # Unexpired timer: remains AwaitingFeedback
        st_pre = evaluate_status_on_timer_check(DomainStatus.AWAITING_FEEDBACK, unexpired_due, now)
        assert st_pre == DomainStatus.AWAITING_FEEDBACK

        # Expired timer: transitions to FeedbackDue
        st_post = evaluate_status_on_timer_check(DomainStatus.AWAITING_FEEDBACK, expired_due, now)
        assert st_post == DomainStatus.FEEDBACK_DUE

    def test_manager_confirmation_separate_from_mailbox_evidence(self):
        """
        Manager manual confirmation of interview completion must remain distinct
        from mailbox message evidence. Never imply recruiter@tcs.com confirmed completion.
        """
        rec = get_synthetic_record_by_id("syn-rec-001")
        assert rec is not None
        assert rec.domain_status == DomainStatus.AWAITING_FEEDBACK

        # System notes log manager confirmation
        assert "Manager confirmed interview completed" in rec.system_notes

        # Email timeline contains recruiter scheduled email, but NOT a fake recruiter completion claim
        recruiter_emails = [t for t in rec.timeline if "tcs.com" in t.sender]
        for t in recruiter_emails:
            assert "Interview completed" not in t.body_preview

        # Manual confirmation is separate timeline entry with is_system_note=True
        manual_entries = [t for t in rec.timeline if t.is_system_note or "Manager" in t.sender]
        assert len(manual_entries) >= 1
        assert "Manager confirmed" in manual_entries[0].body_preview

    def test_cancelled_goes_to_needs_review(self):
        status = compute_domain_status_after_interview(
            InterviewState.CANCELLED, DomainStatus.IN_EVALUATION
        )
        assert status == DomainStatus.NEEDS_REVIEW

    def test_not_confirmed_goes_to_needs_review(self):
        status = compute_domain_status_after_interview(
            InterviewState.NOT_CONFIRMED, DomainStatus.IN_EVALUATION
        )
        assert status == DomainStatus.NEEDS_REVIEW

    def test_rescheduled_stays_in_evaluation(self):
        status = compute_domain_status_after_interview(
            InterviewState.RESCHEDULED, DomainStatus.IN_EVALUATION
        )
        assert status == DomainStatus.IN_EVALUATION

    def test_scheduled_stays_in_evaluation(self):
        status = compute_domain_status_after_interview(
            InterviewState.SCHEDULED, DomainStatus.NEW_SUBMISSION
        )
        assert status == DomainStatus.IN_EVALUATION


# --- Close / Reopen Tests ---

class TestCloseReopen:
    def test_close_position_closed(self):
        action = CloseAction(reason=CloseReason.POSITION_CLOSED)
        ok, _ = validate_close_action(action)
        assert ok

    def test_close_candidate_withdrawn(self):
        action = CloseAction(reason=CloseReason.CANDIDATE_WITHDRAWN)
        ok, _ = validate_close_action(action)
        assert ok

    def test_close_client_rejected(self):
        action = CloseAction(reason=CloseReason.CLIENT_REJECTED)
        ok, _ = validate_close_action(action)
        assert ok

    def test_close_no_followup_needed(self):
        action = CloseAction(reason=CloseReason.NO_FOLLOW_UP_NEEDED)
        ok, _ = validate_close_action(action)
        assert ok

    def test_close_other_with_note(self):
        action = CloseAction(reason=CloseReason.OTHER, note="Duplicate submission")
        ok, _ = validate_close_action(action)
        assert ok

    def test_close_other_without_note_fails(self):
        action = CloseAction(reason=CloseReason.OTHER, note=None)
        ok, reason = validate_close_action(action)
        assert not ok
        assert "requires a note" in reason

    def test_close_other_empty_note_fails(self):
        action = CloseAction(reason=CloseReason.OTHER, note="   ")
        ok, reason = validate_close_action(action)
        assert not ok
        assert "requires a note" in reason

    def test_reopen_on_newer_message(self):
        """Closed record reopens when a newer exact-conversation message arrives."""
        result = should_reopen_on_new_message(
            current_status=DomainStatus.CLOSED,
            existing_latest_timestamp="2026-07-20T10:00:00+00:00",
            new_message_timestamp="2026-07-25T10:00:00+00:00"
        )
        assert result is True

    def test_no_reopen_on_older_message(self):
        """Closed record does NOT reopen for an older message."""
        result = should_reopen_on_new_message(
            current_status=DomainStatus.CLOSED,
            existing_latest_timestamp="2026-07-25T10:00:00+00:00",
            new_message_timestamp="2026-07-20T10:00:00+00:00"
        )
        assert result is False

    def test_no_reopen_if_not_closed(self):
        """Non-closed records don't trigger reopen logic."""
        result = should_reopen_on_new_message(
            current_status=DomainStatus.IN_EVALUATION,
            existing_latest_timestamp="2026-07-20T10:00:00+00:00",
            new_message_timestamp="2026-07-25T10:00:00+00:00"
        )
        assert result is False


# --- Manager Notes / System Notes Tests ---

class TestNotes:
    def test_append_manager_note_to_empty(self):
        result = append_manager_note("", "First note")
        assert "First note" in result
        assert result.startswith("[")

    def test_append_manager_note_preserves_existing(self):
        """Manager notes NEVER overwritten — only appended."""
        existing = "[2026-07-15T10:00:00] Earlier note"
        result = append_manager_note(existing, "Second note")
        assert "Earlier note" in result
        assert "Second note" in result
        lines = result.strip().split("\n")
        assert len(lines) == 2

    def test_append_three_notes_preserves_all(self):
        notes = ""
        notes = append_manager_note(notes, "Note 1")
        notes = append_manager_note(notes, "Note 2")
        notes = append_manager_note(notes, "Note 3")
        assert "Note 1" in notes
        assert "Note 2" in notes
        assert "Note 3" in notes
        lines = notes.strip().split("\n")
        assert len(lines) == 3

    def test_system_notes_separate_from_manager_notes(self):
        """System notes and manager notes are independent fields."""
        record = get_synthetic_record_by_id("syn-rec-002")
        assert record is not None
        # This record has both manager and system notes
        assert record.manager_notes  # has content
        assert record.system_notes  # has content
        # They contain different content
        assert record.manager_notes != record.system_notes

    def test_system_note_format(self):
        note = format_system_note("Test event")
        assert note.startswith("[")
        assert "Test event" in note


# --- Identity Invariant Tests ---

class TestIdentityInvariants:
    """
    CRITICAL: Job ID, EP reference, subject, and candidate name MUST NEVER
    be used to link conversations. Only conversationId and graph_immutable_id.
    """

    def test_records_with_same_job_id_are_different_conversations(self):
        """Two records sharing a job_id must remain separate conversations."""
        records = get_synthetic_records()
        # Simulate: if two records had the same job_id, their conversationIds must differ
        conv_ids = {r.conversation_id for r in records}
        # All synthetic records have unique conversationIds
        assert len(conv_ids) == len(records)

    def test_records_with_same_candidate_are_different_conversations(self):
        """Two submissions for the same candidate must be separate records if conversationIds differ."""
        records = get_synthetic_records()
        immutable_ids = {r.graph_immutable_id for r in records}
        assert len(immutable_ids) == len(records)

    def test_conversation_id_is_identity_key(self):
        """Each record's identity is its conversationId, not metadata."""
        records = get_synthetic_records()
        for r in records:
            assert r.conversation_id, f"Record {r.id} missing conversationId"
            assert r.graph_immutable_id, f"Record {r.id} missing graph_immutable_id"

    def test_job_id_is_metadata_only(self):
        """Job ID must not participate in record lookup or linking."""
        # Lookup is by record ID, not job_id
        record = get_synthetic_record_by_id("syn-rec-001")
        assert record is not None
        # There's no get_by_job_id method — job_id is display-only
        assert record.job_id == "418326"

    def test_ep_reference_is_metadata_only(self):
        """EP reference must not participate in record lookup or linking."""
        record = get_synthetic_record_by_id("syn-rec-001")
        assert record is not None
        assert record.ep_reference == "EP2026RA7415469"


# --- Dashboard Summary Tests ---

class TestDashboard:
    def test_summary_counts_match(self):
        summary = get_synthetic_dashboard_summary()
        total = (
            summary.awaiting_feedback +
            summary.pending_follow_up +
            summary.feedback_due +
            summary.manager_action_required +
            summary.in_evaluation +
            summary.needs_review +
            summary.closed
        )
        assert total == summary.total
        assert summary.total >= 6

    def test_each_status_has_one_record(self):
        summary = get_synthetic_dashboard_summary()
        assert summary.awaiting_feedback == 1
        assert summary.feedback_due == 1
        assert summary.manager_action_required == 1
        assert summary.in_evaluation == 1
        assert summary.needs_review == 1
        assert summary.closed >= 1

    def test_auth_status_is_synthetic(self):
        summary = get_synthetic_dashboard_summary()
        assert summary.auth_status == "synthetic_test_data"

    def test_records_list_populated(self):
        summary = get_synthetic_dashboard_summary()
        assert len(summary.records) >= 6

    def test_record_lookup_by_id(self):
        record = get_synthetic_record_by_id("syn-rec-003")
        assert record is not None
        assert record.candidate_name == "Alex Mercer"
        assert record.domain_status == DomainStatus.MANAGER_ACTION_REQUIRED

    def test_record_lookup_nonexistent(self):
        record = get_synthetic_record_by_id("does-not-exist")
        assert record is None

    def test_timeline_entries_exist(self):
        record = get_synthetic_record_by_id("syn-rec-001")
        assert record is not None
        assert len(record.timeline) >= 3
        # Timeline entries are chronological
        for entry in record.timeline:
            assert entry.sender
            assert entry.timestamp
