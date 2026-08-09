from types import SimpleNamespace

from backend.app.application.interview_reconciliation_service import (
    InterviewReconciliationService,
)


SUBJECT = "418326 - EP2026RA7415469 - Jane Doe - Data Engineer - Client - Remote"


class FakeGraph:
    def fetch_mailbox_messages_since(self, date_str):
        return ([{
            "id": "header-1", "conversationId": "interview-conv",
            "subject": f"RE: {SUBJECT}", "bodyPreview": "Interview invite sent for Monday",
            "receivedDateTime": "2026-08-08T14:00:00Z",
        }], "ok", {})

    def fetch_exact_conversation_messages(self, conversation_id):
        return ([{
            "id": "immutable-1", "conversationId": conversation_id,
            "subject": SUBJECT, "bodyPreview": "Interview invite sent for Monday",
            "receivedDateTime": "2026-08-08T14:00:00Z",
        }], "ok")


class FakePersistence:
    def __init__(self):
        self.updated = None

    def list_records(self):
        return [SimpleNamespace(id="rec-1", conversation_id="original-conv")]

    def get_record_payload_snapshot(self, record_id):
        return ({
            "subject": SUBJECT,
            "graph_immutable_id": "source-1",
            "conversation_id": "original-conv",
            "linked_conversations": [],
        }, 3, "PendingFollowUp")

    def update_record_optimistically(self, record_id, payload, status, version):
        self.updated = (record_id, payload, status, version)
        return version + 1


def test_reconciliation_persists_exact_subject_interview_conversation():
    persistence = FakePersistence()
    result = InterviewReconciliationService(FakeGraph(), persistence).reconcile()
    assert result.conversations_linked == 1
    assert persistence.updated is not None
    link = persistence.updated[1]["linked_conversations"][0]
    assert link["conversation_id"] == "interview-conv"
    assert link["linked_by"] == "automatic_exact_subject_rule"


def test_duplicate_complete_subjects_fail_closed():
    persistence = FakePersistence()
    persistence.list_records = lambda: [
        SimpleNamespace(id="rec-1", conversation_id="c1"),
        SimpleNamespace(id="rec-2", conversation_id="c2"),
    ]
    persistence.get_record_payload_snapshot = lambda record_id: (
        {"subject": SUBJECT, "linked_conversations": []}, 1, "NeedsReview"
    )
    result = InterviewReconciliationService(FakeGraph(), persistence).reconcile()
    assert result.conversations_linked == 0
    assert result.conflicts_skipped == 2
    assert persistence.updated is None
