from backend.app.application.workflow_engine import build_professional_followup_draft
from backend.app.domain.models import DomainStatus


def test_submission_followup_is_professional_and_complete():
    text = build_professional_followup_draft(
        DomainStatus.PENDING_FOLLOW_UP,
        "Jane Doe",
        "Data Engineer",
        "123456",
        "EP2026RA000001",
    )
    assert text.startswith("Hi Team,\n\nHope you are doing well.\n\n")
    assert "chance to review the profile of Jane Doe" in text
    assert "Job ID 123456" in text
    assert "EP2026RA000001" not in text
    assert "interview availability" in text
    assert text.endswith("Thank you,\nTarun Srivastava\nClifyX")


def test_feedback_followup_requests_feedback_and_next_steps():
    text = build_professional_followup_draft(
        DomainStatus.FEEDBACK_DUE, "Jane Doe", "Data Engineer"
    )
    assert "interview feedback for Jane Doe" in text
    assert "advise us on the next steps" in text
    assert "submission of" not in text


def test_feedback_followup_uses_interview_date_and_missing_invite_evidence():
    text = build_professional_followup_draft(
        DomainStatus.FEEDBACK_DUE,
        "Jane Doe",
        "Data Engineer",
        interview_datetime="August 10, 2026 at 2:00 PM EDT",
        interview_invite_found=False,
    )
    assert "August 10, 2026 at 2:00 PM EDT" in text
    assert "completed the interview on August 10, 2026 at 2:00 PM EDT" in text


def test_interview_request_without_invite_is_stated_clearly():
    text = build_professional_followup_draft(
        DomainStatus.FEEDBACK_DUE,
        "Jane Doe",
        "Data Engineer",
        interview_invite_found=False,
    )
    assert "interview was requested" in text
    assert "not received the calendar invite" in text


def test_template_never_contains_send_instruction():
    text = build_professional_followup_draft(
        DomainStatus.PENDING_FOLLOW_UP, None, None
    )
    assert "send automatically" not in text.lower()
    assert "click send" not in text.lower()
