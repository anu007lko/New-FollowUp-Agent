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
        {"id": "m1", "conversationId": "round-1", "subject": SUBJECT, "bodyPreview": "Interview schedule", "receivedDateTime": "2026-08-08T10:00:00Z", "from": {"emailAddress": {"address": "recruiter@tcs.com"}}},
        {"id": "m2", "conversationId": "round-2", "subject": f"FWD: {SUBJECT}", "bodyPreview": "Second interview invite", "receivedDateTime": "2026-08-09T10:00:00Z", "from": {"emailAddress": {"address": "hr@tcs.com"}}},
    ]
    assert len(link_exact_subject_interview_conversations(SUBJECT, "original-conv", messages)) == 2


def test_normalization_does_not_reduce_subject_to_job_or_ep():
    assert normalize_full_subject(f" RE:   {SUBJECT} ") == normalize_full_subject(SUBJECT)
    assert normalize_full_subject(SUBJECT) != normalize_full_subject("418326 - EP2026RA7415469")


def test_valid_external_client_response():
    messages = [{
        "id": "m1", "conversationId": "client-conv-1",
        "subject": f"RE: {SUBJECT}", "bodyPreview": "Candidate profile looks good.",
        "receivedDateTime": "2026-08-08T14:00:00Z",
        "from": {"emailAddress": {"address": "recruiter@tcs.com"}},
    }]
    links = link_exact_subject_interview_conversations(SUBJECT, "original-conv", messages)
    assert len(links) == 1
    assert links[0]["role"] == "client_response"

def test_internal_only_thread_is_not_linked():
    messages = [{
        "id": "m1", "conversationId": "internal-conv",
        "subject": f"FW: {SUBJECT}", "bodyPreview": "FYI profile sent to client.",
        "receivedDateTime": "2026-08-08T14:00:00Z",
        "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
    }]
    links = link_exact_subject_interview_conversations(SUBJECT, "original-conv", messages)
    assert links == []

def test_auto_reply_is_not_linked():
    messages = [{
        "id": "m1", "conversationId": "auto-reply-conv",
        "subject": f"Automatic reply: {SUBJECT}", "bodyPreview": "I am currently out of office.",
        "receivedDateTime": "2026-08-08T14:00:00Z",
        "from": {"emailAddress": {"address": "recruiter@tcs.com"}},
    }]
    links = link_exact_subject_interview_conversations(SUBJECT, "original-conv", messages)
    assert links == []

def test_rani_requirement_closed_response():
    subject = "418542 - EP2026RA7308068 - Rani Ciriguri - SAP S/4HANA OTC / SD Consultant - Advantage Sales & Marketing LLC - Remote"
    messages = [{
        "id": "m1", "conversationId": "rani-client-conv",
        "subject": f"RE: {subject}", "bodyPreview": "TCS Confidential\n\nHi Tarun,\n\nThis requirement is closed, please do not submit profiles.\n\nRegards,\nKavi Rajendiran",
        "receivedDateTime": "2026-07-14T15:26:04Z",
        "from": {"emailAddress": {"address": "kavi.rajendiran@tcs.com"}},
    }]
    links = link_exact_subject_interview_conversations(subject, "original-conv", messages)
    assert len(links) == 1
    assert links[0]["conversation_id"] == "rani-client-conv"
