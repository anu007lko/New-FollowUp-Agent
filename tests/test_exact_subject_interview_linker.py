from backend.app.domain.interview_linker import (
    link_exact_subject_interview_conversations,
    normalize_full_subject,
)


SUBJECT = "418326 - EP2026RA7415469 - Candidate Name - Data Engineer - Client - Remote"


def test_exact_full_subject_links_separate_interview_chain_despite_participant_change():
    messages = [{
        "id": "immutable-interview-1", "conversationId": "interview-conv-1",
        "subject": f"RE: {SUBJECT}", "bodyPreview": "Interview invite sent for Monday 2 PM EST",
        "receivedDateTime": "2026-08-08T14:00:00Z",
        "from": {"emailAddress": {"address": "different.person@tcs.com"}},
    }]
    links = link_exact_subject_interview_conversations(SUBJECT, "original-conv", messages)
    assert len(links) == 1
    assert links[0]["conversation_id"] == "interview-conv-1"


def test_ep_number_alone_never_links_different_requirement():
    other = SUBJECT.replace("Data Engineer", "Program Manager")
    messages = [{"conversationId": "other-conv", "subject": other, "bodyPreview": "Interview invite sent"}]
    assert link_exact_subject_interview_conversations(SUBJECT, "original-conv", messages) == []


def test_multiple_interview_conversations_can_link_to_one_submission():
    messages = [
        {"id": "m1", "conversationId": "round-1", "subject": SUBJECT, "bodyPreview": "Interview schedule", "receivedDateTime": "2026-08-08T10:00:00Z"},
        {"id": "m2", "conversationId": "round-2", "subject": f"FWD: {SUBJECT}", "bodyPreview": "Second interview invite", "receivedDateTime": "2026-08-09T10:00:00Z"},
    ]
    assert len(link_exact_subject_interview_conversations(SUBJECT, "original-conv", messages)) == 2


def test_normalization_does_not_reduce_subject_to_job_or_ep():
    assert normalize_full_subject(f" RE:   {SUBJECT} ") == normalize_full_subject(SUBJECT)
    assert normalize_full_subject(SUBJECT) != normalize_full_subject("418326 - EP2026RA7415469")


def test_same_full_subject_without_interview_evidence_is_not_linked():
    messages = [{
        "id": "m1", "conversationId": "unrelated-copy", "subject": SUBJECT,
        "bodyPreview": "Thank you for the update.",
    }]
    assert link_exact_subject_interview_conversations(SUBJECT, "original-conv", messages) == []
