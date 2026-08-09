import pytest
from datetime import datetime, timezone
from backend.app.domain.consolidated_classifier import classify_record

def test_consolidated_no_response_awaiting():
    source_id = "msg_1"
    thread = [
        {
            "id": "msg_1",
            "internetMessageId": "<sub_1@clifyx.com>",
            "sentDateTime": "2026-08-03T10:00:00Z",
            "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
            "bodyPreview": "Submitting candidate"
        }
    ]
    ref_time = datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc) # 24h later
    res = classify_record(source_id, thread, ref_time)
    assert res.category == "No Response"
    assert res.proposed_status == "Awaiting Response"
    assert res.reason_code == "NO_INBOUND_AWAITING_RESPONSE_WITHIN_48H"
    assert res.timer_anchor_type == "ORIGINAL_SUBMISSION"

def test_consolidated_no_response_due():
    source_id = "msg_1"
    thread = [
        {
            "id": "msg_1",
            "internetMessageId": "<sub_1@clifyx.com>",
            "sentDateTime": "2026-08-01T10:00:00Z",
            "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
            "bodyPreview": "Submitting candidate"
        }
    ]
    ref_time = datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc) # 72h later
    res = classify_record(source_id, thread, ref_time)
    assert res.category == "No Response"
    assert res.proposed_status == "Follow-up Due"
    assert res.reason_code == "NO_INBOUND_FOLLOWUP_DUE_48H"

def test_consolidated_rejection_manager_action():
    source_id = "msg_1"
    thread = [
        {
            "id": "msg_1",
            "internetMessageId": "<sub_1@clifyx.com>",
            "sentDateTime": "2026-08-01T10:00:00Z",
            "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
            "bodyPreview": "Submitting candidate"
        },
        {
            "id": "msg_2",
            "internetMessageId": "<reply_1@client.com>",
            "sentDateTime": "2026-08-02T10:00:00Z",
            "from": {"emailAddress": {"address": "client@company.com"}},
            "bodyPreview": "We will pass on this candidate."
        }
    ]
    ref_time = datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc)
    res = classify_record(source_id, thread, ref_time)
    assert res.category == "Rejection"
    assert res.proposed_status == "Manager Action Required"
    assert res.reason_code == "DETERMINISTIC_REJECTION"

def test_consolidated_uncertain_followup_anchor():
    source_id = "msg_1"
    thread = [
        {
            "id": "msg_1",
            "internetMessageId": "<sub_1@clifyx.com>",
            "sentDateTime": "2026-08-01T10:00:00Z",
            "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
            "bodyPreview": "Submitting candidate"
        },
        {
            "id": "msg_2",
            "internetMessageId": "<sent_2@clifyx.com>", # Unconfirmed follow-up
            "sentDateTime": "2026-08-02T10:00:00Z",
            "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
            "bodyPreview": "Following up"
        }
    ]
    ref_time = datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc)
    res = classify_record(source_id, thread, ref_time)
    assert res.proposed_status == "Needs Review"
    assert res.reason_code == "UNCERTAIN_FOLLOWUP_ANCHOR"

def test_interview_awaiting_confirmation_category_separation():
    """Regression test: Interview Awaiting Confirmation MUST be proposed status, NOT category."""
    source_id = "msg_1"
    thread = [
        {
            "id": "msg_1",
            "internetMessageId": "<sub_1@clifyx.com>",
            "sentDateTime": "2026-08-01T10:00:00Z",
            "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
            "bodyPreview": "Submitting candidate"
        },
        {
            "id": "msg_2",
            "internetMessageId": "<reply_2@client.com>",
            "sentDateTime": "2026-08-01T11:00:00Z",
            "from": {"emailAddress": {"address": "client@company.com"}},
            "bodyPreview": "Invite sent for today 3pm EST"
        }
    ]
    # Ref time after the scheduled interview time
    ref_time = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)
    res = classify_record(source_id, thread, ref_time)
    assert res.category == "Interview Scheduled"
    assert res.proposed_status == "Interview Awaiting Confirmation"
    assert res.category != "Interview Awaiting Confirmation"
