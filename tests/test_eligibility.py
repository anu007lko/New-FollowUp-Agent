"""
Automated unit tests for deterministic TCS eligibility evaluation.
"""

import pytest
from backend.app.domain.eligibility import evaluate_tcs_eligibility


def test_tcs_recipient_inclusion():
    """Verify message with @tcs.com in To list is eligible."""
    is_eligible, reason, tcs_recipients, co_recipients = evaluate_tcs_eligibility(
        to_recipients=["recruiter@tcs.com"],
        cc_recipients=[],
        subject="Submission for Candidate"
    )
    assert is_eligible is True
    assert reason is None
    assert tcs_recipients == ["recruiter@tcs.com"]
    assert co_recipients == []


def test_end_client_co_recipient_allowed():
    """Verify message with @tcs.com and end-client co-recipient (e.g. Bank of America) is eligible."""
    is_eligible, reason, tcs_recipients, co_recipients = evaluate_tcs_eligibility(
        to_recipients=["hr@tcs.com"],
        cc_recipients=["manager@bankofamerica.com", "lead@apple.com"],
        subject="TCS Candidate Submission"
    )
    assert is_eligible is True
    assert tcs_recipients == ["hr@tcs.com"]
    assert "manager@bankofamerica.com" in co_recipients
    assert "lead@apple.com" in co_recipients


def test_lookalike_subject_without_tcs_recipient_excluded():
    """Verify message with TCS keywords in subject but NO @tcs.com recipient in To/CC is strictly excluded."""
    is_eligible, reason, tcs_recipients, co_recipients = evaluate_tcs_eligibility(
        to_recipients=["alex@directclient.com"],
        cc_recipients=["manager@anothercompany.com"],
        subject="TCS Submission: EP-9999 / JOB-1111 - Lookalike Candidate"
    )
    assert is_eligible is False
    assert reason is not None
    assert "No @tcs.com recipient" in reason
    assert len(tcs_recipients) == 0
