"""Comprehensive tests for interview date, time, and timezone detection rules."""

from datetime import datetime, timezone
import pytest
from backend.app.domain.interview_parser import (
    evaluate_thread_interview_details,
    parse_slot_from_text,
    InterviewDetectionResult,
)
from backend.app.domain.consolidated_classifier import classify_record


def test_rule1_direct_scheduling_command():
    msg = {
        "graph_immutable_id": "msg-101",
        "sender": "client@tcs.com",
        "body_preview": "Please schedule the interview for Tuesday, 4 PM EST.",
        "timestamp": "2026-08-10T10:00:00Z",
    }
    cur = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    res = evaluate_thread_interview_details([msg], cur)
    assert res.interview_status == "Interview Scheduled"
    assert res.confidence_label == "Confirmed from thread"
    assert res.interview_date == "2026-08-11"
    assert res.interview_time == "16:00"
    assert res.timezone == "EST"


def test_rule2_availability_requires_later_confirmation():
    msg1 = {
        "graph_immutable_id": "msg-201",
        "sender": "candidate@example.com",
        "body_preview": "Candidate is available Tuesday at 4 PM EST. Please confirm this slot.",
        "timestamp": "2026-08-10T09:00:00Z",
    }
    cur = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)

    # 1. Unconfirmed availability
    res1 = evaluate_thread_interview_details([msg1], cur)
    assert res1.interview_status == "Interview Awaiting Confirmation"
    assert res1.confidence_label == "Awaiting confirmation"

    # 2. Later confirmation reply added
    msg2 = {
        "graph_immutable_id": "msg-202",
        "sender": "recruiter@tcs.com",
        "body_preview": "Interview is confirmed. That time works.",
        "timestamp": "2026-08-10T10:00:00Z",
    }
    res2 = evaluate_thread_interview_details([msg1, msg2], cur)
    assert res2.interview_status == "Interview Scheduled"
    assert res2.confidence_label == "Confirmed from thread"
    assert res2.interview_time == "16:00"


def test_rule3_changed_slot_unconfirmed():
    msg1 = {
        "graph_immutable_id": "msg-301",
        "sender": "client@tcs.com",
        "body_preview": "Please schedule for Tuesday at 4 PM EST.",
        "timestamp": "2026-08-10T09:00:00Z",
    }
    msg2 = {
        "graph_immutable_id": "msg-302",
        "sender": "candidate@example.com",
        "body_preview": "Move it to Thursday at 2 PM EST instead. Is that available?",
        "timestamp": "2026-08-10T10:00:00Z",
    }
    cur = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    res = evaluate_thread_interview_details([msg1, msg2], cur)
    assert res.interview_status == "Interview Awaiting Confirmation"
    assert res.confidence_label == "Awaiting confirmation"
    assert res.interview_time == "14:00"


def test_rule4_calendar_invite_confirms_availability():
    msg1 = {
        "graph_immutable_id": "msg-401",
        "sender": "candidate@example.com",
        "body_preview": "Candidate is available Wednesday at 10 AM EST.",
        "timestamp": "2026-08-10T09:00:00Z",
    }
    msg2 = {
        "graph_immutable_id": "msg-402",
        "sender": "recruiter@clifyx.com",
        "body_preview": "Calendar invite sent for Wednesday at 10 AM EST.",
        "timestamp": "2026-08-10T10:00:00Z",
    }
    cur = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    res = evaluate_thread_interview_details([msg1, msg2], cur)
    assert res.interview_status == "Interview Scheduled"
    assert res.confidence_label == "Confirmed from thread"


def test_rule5_missing_timezone_resolution_and_fallback():
    # 1. Missing timezone text, but sender is @tcs.com (known timezone)
    msg1 = {
        "graph_immutable_id": "msg-501",
        "sender": "recruiter@tcs.com",
        "body_preview": "Please schedule for tomorrow at 3 PM.",
        "timestamp": "2026-08-10T09:00:00Z",
    }
    cur = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    res1 = evaluate_thread_interview_details([msg1], cur)
    assert res1.timezone == "EST"
    assert res1.timezone_source == "sender_metadata"

    # 2. Missing timezone text and completely unknown sender domain -> flags review
    msg2 = {
        "graph_immutable_id": "msg-502",
        "sender": "random@unknown-external-domain.xyz",
        "body_preview": "Scheduled for tomorrow at 3 PM.",
        "timestamp": "2026-08-10T09:00:00Z",
    }
    res2 = evaluate_thread_interview_details([msg2], cur)
    assert res2.interview_status == "Needs Review"
    assert res2.timezone is None


def test_rule6_schedule_conflict():
    msg1 = {
        "graph_immutable_id": "msg-601",
        "sender": "client@tcs.com",
        "body_preview": "Please schedule the interview for Tuesday at 4 PM EST.",
        "timestamp": "2026-08-10T09:00:00Z",
    }
    msg2 = {
        "graph_immutable_id": "msg-602",
        "sender": "client2@tcs.com",
        "body_preview": "Please schedule the interview for Wednesday at 2 PM EST.",
        "timestamp": "2026-08-10T10:00:00Z",
    }
    cur = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    res = evaluate_thread_interview_details([msg1, msg2], cur)
    assert res.interview_status == "Needs Review"
    assert res.confidence_label == "Schedule conflict"
    assert len(res.supporting_message_ids) == 2


def test_rule7_cancellation_supersedes_older_scheduled_time():
    msg1 = {
        "graph_immutable_id": "msg-701",
        "sender": "client@tcs.com",
        "body_preview": "Please schedule the interview for Tuesday at 4 PM EST.",
        "timestamp": "2026-08-10T09:00:00Z",
    }
    msg2 = {
        "graph_immutable_id": "msg-702",
        "sender": "client@tcs.com",
        "body_preview": "Interview cancelled. Panel is unavailable.",
        "timestamp": "2026-08-10T11:00:00Z",
    }
    cur = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    res = evaluate_thread_interview_details([msg1, msg2], cur)
    assert res.interview_status == "Needs Review"
    assert res.confidence_label is None
