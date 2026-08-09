import os
import sqlite3
import json
import pytest
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict, Any
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, "/Users/tarunsrivastava/Desktop/Follow Up Agent")
from backend.app.domain.consolidated_classifier import classify_record, PROPOSED_TO_DOMAIN_STATUS
from backend.app.domain.models import DomainStatus, InterviewState

def get_base_thread(body: str, timestamp: datetime) -> List[Dict[str, Any]]:
    return [{
        "id": "msg1",
        "conversationId": "conv1",
        "isDraft": False,
        "isRead": True,
        "from": {"emailAddress": {"address": "test@test.com", "name": "Test"}},
        "sentDateTime": timestamp.isoformat(),
        "bodyPreview": body
    }]

def test_future_scheduled_interview():
    now = datetime(2026, 8, 6, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    # Interview is parsed for Aug 10
    body = "Please schedule the interview for next week Monday 2 pm EST."
    thread = get_base_thread(body, now - timedelta(hours=1))
    
    res = classify_record(
        source_immutable_id="id1",
        thread_messages=thread,
        current_time=now
    )
    
    assert res.category == "Interview Scheduled"
    assert res.proposed_status == "Interview Scheduled"
    
    domain_status = PROPOSED_TO_DOMAIN_STATUS[res.proposed_status]
    assert domain_status == DomainStatus.INTERVIEW_REQUEST_SCHEDULED

def test_passed_interview_boundary():
    now = datetime(2026, 8, 11, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    # Interview is parsed for Aug 10, so it's in the past relative to now
    body = "Please schedule the interview for next week Monday 2 pm EST."
    # The email was sent on Aug 5
    sent_dt = datetime(2026, 8, 5, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    thread = get_base_thread(body, sent_dt)
    
    res = classify_record(
        source_immutable_id="id1",
        thread_messages=thread,
        current_time=now
    )
    
    assert res.category == "Interview Scheduled"
    assert res.proposed_status == "Interview Awaiting Confirmation"
    
    domain_status = PROPOSED_TO_DOMAIN_STATUS[res.proposed_status]
    assert domain_status == DomainStatus.INTERVIEW_AWAITING_CONFIRMATION

def test_manager_confirmed_completed_protects_status():
    # If a manager has set interview_state to COMPLETED, the application handles it in workflow_engine.
    # The requirement is that reclassification shouldn't regress a future interview, and
    # "Manager-confirmed Completed remains protected and starts the existing feedback workflow."
    # To test this, we should test the workflow engine directly.
    from backend.app.application.workflow_engine import compute_domain_status_after_interview, evaluate_status_on_timer_check
    
    # Manager marks completed
    st = compute_domain_status_after_interview(InterviewState.COMPLETED, DomainStatus.INTERVIEW_REQUEST_SCHEDULED)
    assert st == DomainStatus.AWAITING_FEEDBACK

    # Time passes, feedback due triggers
    now = datetime.now(timezone.utc)
    due = (now - timedelta(hours=1)).isoformat()
    st2 = evaluate_status_on_timer_check(DomainStatus.AWAITING_FEEDBACK, due, now)
    assert st2 == DomainStatus.FEEDBACK_DUE

