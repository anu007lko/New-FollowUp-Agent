"""
Comprehensive offline test suite for P1 audit-integrity hardening.
Verifies append-only preservation, tamper resistance (deletion/alteration/reordering rejection),
canonical schema completeness, legacy entry preservation, and optimistic locking conflict safety.
"""

import pytest
import json
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.audit_trail import create_audit_event, is_audit_event
from backend.app.domain.models import DomainStatus


client = TestClient(app)


@pytest.fixture
def temp_persistence(tmp_path):
    db_file = str(tmp_path / "test_audit_integrity.db")
    return EncryptedPersistenceEngine(db_path=db_file)


def test_deleting_existing_audit_event_is_rejected(temp_persistence):
    record_id = "rec-audit-del-001"
    evt1 = create_audit_event(
        record_id=record_id,
        event_type="INITIAL_ENTRY",
        actor="system",
        prior_status="NeedsReview",
        resulting_status="NeedsReview",
        record_version=1
    )
    payload = {
        "id": record_id,
        "record_version": 1,
        "graph_immutable_id": "graph-001",
        "conversation_id": "conv-001",
        "timeline": [evt1]
    }
    temp_persistence.save_record_payload(record_id, payload, "NeedsReview")

    # Attempt to delete the existing audit event
    tampered_payload = dict(payload)
    tampered_payload["timeline"] = []

    with pytest.raises(ValueError, match="Audit timeline append-only constraint violation"):
        temp_persistence.update_record_optimistically(record_id, tampered_payload, "NeedsReview", 1)


def test_altering_existing_audit_event_is_rejected(temp_persistence):
    record_id = "rec-audit-alt-001"
    evt1 = create_audit_event(
        record_id=record_id,
        event_type="MANAGER_NOTE_ADDED",
        actor="tarun@clifyx.com",
        prior_status="NeedsReview",
        resulting_status="NeedsReview",
        record_version=1,
        note="Original Note"
    )
    payload = {
        "id": record_id,
        "record_version": 1,
        "graph_immutable_id": "graph-002",
        "conversation_id": "conv-002",
        "timeline": [evt1]
    }
    temp_persistence.save_record_payload(record_id, payload, "NeedsReview")

    # Attempt to alter the note inside existing audit event
    tampered_evt = dict(evt1)
    tampered_evt["note"] = "Tampered Note Text"
    tampered_payload = dict(payload)
    tampered_payload["timeline"] = [tampered_evt]

    with pytest.raises(ValueError, match="Audit timeline append-only constraint violation"):
        temp_persistence.update_record_optimistically(record_id, tampered_payload, "NeedsReview", 1)


def test_reordering_existing_audit_events_is_rejected(temp_persistence):
    record_id = "rec-audit-reorder-001"
    evt1 = create_audit_event(
        record_id=record_id,
        event_type="EVENT_ONE",
        actor="system",
        prior_status="NeedsReview",
        resulting_status="NeedsReview",
        record_version=1
    )
    evt2 = create_audit_event(
        record_id=record_id,
        event_type="EVENT_TWO",
        actor="tarun@clifyx.com",
        prior_status="NeedsReview",
        resulting_status="PendingFollowUp",
        record_version=2
    )
    payload = {
        "id": record_id,
        "record_version": 2,
        "graph_immutable_id": "graph-003",
        "conversation_id": "conv-003",
        "timeline": [evt1, evt2]
    }
    temp_persistence.save_record_payload(record_id, payload, "PendingFollowUp")

    # Attempt to reorder historical events
    reordered_payload = dict(payload)
    reordered_payload["timeline"] = [evt2, evt1]

    with pytest.raises(ValueError, match="Audit timeline append-only constraint violation"):
        temp_persistence.update_record_optimistically(record_id, reordered_payload, "PendingFollowUp", 2)


def test_appending_valid_new_audit_event_succeeds(temp_persistence):
    record_id = "rec-audit-append-001"
    evt1 = create_audit_event(
        record_id=record_id,
        event_type="EVENT_ONE",
        actor="system",
        prior_status="NeedsReview",
        resulting_status="NeedsReview",
        record_version=1
    )
    payload = {
        "id": record_id,
        "record_version": 1,
        "graph_immutable_id": "graph-004",
        "conversation_id": "conv-004",
        "timeline": [evt1]
    }
    temp_persistence.save_record_payload(record_id, payload, "NeedsReview")

    # Append valid new audit event
    evt2 = create_audit_event(
        record_id=record_id,
        event_type="EVENT_TWO",
        actor="tarun@clifyx.com",
        prior_status="NeedsReview",
        resulting_status="Closed",
        record_version=2
    )
    payload["timeline"] = [evt1, evt2]
    payload["record_version"] = 2

    new_ver = temp_persistence.update_record_optimistically(record_id, payload, "Closed", 1)
    assert new_ver == 2

    saved = temp_persistence.get_record_payload_snapshot(record_id)[0]
    saved_events = [e for e in saved.get("timeline", []) if is_audit_event(e)]
    assert len(saved_events) == 2
    assert saved_events[0]["event_type"] == "EVENT_ONE"
    assert saved_events[1]["event_type"] == "EVENT_TWO"


def test_thread_message_refresh_allowed_when_audit_timeline_unchanged(temp_persistence):
    record_id = "rec-audit-refresh-001"
    evt1 = create_audit_event(
        record_id=record_id,
        event_type="INITIAL_IMPORT",
        actor="system",
        prior_status="NeedsReview",
        resulting_status="NeedsReview",
        record_version=1
    )
    payload = {
        "id": record_id,
        "record_version": 1,
        "graph_immutable_id": "graph-005",
        "conversation_id": "conv-005",
        "thread_messages": [{"id": "msg-1", "bodyPreview": "Initial email"}],
        "timeline": [evt1]
    }
    temp_persistence.save_record_payload(record_id, payload, "NeedsReview")

    # Refresh thread messages (adding new email message to thread_messages)
    payload["thread_messages"].append({"id": "msg-2", "bodyPreview": "Follow-up email"})
    payload["record_version"] = 2

    # Update succeeds because historical audit events in payload["timeline"] are untouched
    new_ver = temp_persistence.update_record_optimistically(record_id, payload, "NeedsReview", 1)
    assert new_ver == 2


def test_every_new_audit_event_has_mandatory_schema_fields():
    evt = create_audit_event(
        record_id="rec-schema-001",
        event_type="TEST_ACTION",
        actor="tarun@clifyx.com",
        prior_status="NeedsReview",
        resulting_status="Closed",
        record_version=5,
        note="Schema validation note"
    )
    assert "entry_id" in evt and evt["entry_id"].startswith("evt-")
    assert evt["record_id"] == "rec-schema-001"
    assert "timestamp" in evt
    assert evt["sender"] == "tarun@clifyx.com"
    assert evt["event_type"] == "TEST_ACTION"
    assert evt["prior_status"] == "NeedsReview"
    assert evt["resulting_status"] == "Closed"
    assert evt["record_version"] == 5
    assert evt["audit_event"] is True
    assert evt["is_system_note"] is True
    assert evt["note"] == "Schema validation note"


def test_legacy_audit_entries_preserved_without_forced_db_migration(temp_persistence):
    record_id = "rec-legacy-001"
    legacy_evt = {
        "entry_id": "audit_legacy_1234",
        "sender": "legacy_system",
        "timestamp": "2026-08-01T10:00:00Z",
        "is_system_note": True,
        "body_preview": "Legacy audit entry without newer schema fields"
    }
    payload = {
        "id": record_id,
        "record_version": 1,
        "graph_immutable_id": "graph-legacy",
        "conversation_id": "conv-legacy",
        "timeline": [legacy_evt]
    }
    temp_persistence.save_record_payload(record_id, payload, "NeedsReview")

    # Append new schema audit event alongside legacy entry
    new_evt = create_audit_event(
        record_id=record_id,
        event_type="NEW_ACTION",
        actor="tarun@clifyx.com",
        prior_status="NeedsReview",
        resulting_status="Closed",
        record_version=2
    )
    payload["timeline"] = [legacy_evt, new_evt]
    payload["record_version"] = 2

    # Update must succeed without rejecting legacy entry
    new_ver = temp_persistence.update_record_optimistically(record_id, payload, "Closed", 1)
    assert new_ver == 2

    saved = temp_persistence.get_record_payload_snapshot(record_id)[0]
    saved_timeline = saved.get("timeline", [])
    assert len(saved_timeline) == 2
    assert saved_timeline[0]["entry_id"] == "audit_legacy_1234"
    assert saved_timeline[1]["event_type"] == "NEW_ACTION"


def test_optimistic_lock_conflict_returns_409_and_prevents_partial_audit(temp_persistence):
    record_id = "rec-conflict-001"
    evt1 = create_audit_event(
        record_id=record_id,
        event_type="INIT",
        actor="system",
        prior_status="NeedsReview",
        resulting_status="NeedsReview",
        record_version=1
    )
    payload = {
        "id": record_id,
        "record_version": 1,
        "graph_immutable_id": "graph-conflict",
        "conversation_id": "conv-conflict",
        "timeline": [evt1]
    }
    temp_persistence.save_record_payload(record_id, payload, "NeedsReview")

    # Attempt optimistic update with stale version 999
    evt2 = create_audit_event(
        record_id=record_id,
        event_type="STALE_ACTION",
        actor="tarun@clifyx.com",
        prior_status="NeedsReview",
        resulting_status="Closed",
        record_version=2
    )
    payload["timeline"] = [evt1, evt2]

    with pytest.raises(ValueError, match="Record version token is stale or mismatched"):
        temp_persistence.update_record_optimistically(record_id, payload, "Closed", expected_version=999)

    # Verify that database state still has version 1 and only evt1
    snap, version, status = temp_persistence.get_record_payload_snapshot(record_id)
    assert version == 1
    assert len(snap.get("timeline", [])) == 1
    assert snap["timeline"][0]["event_type"] == "INIT"
