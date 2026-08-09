"""
Approved Daily Review Engine.

INVARIANTS:
1. Schedule: Runs daily at 8:00 AM America/New_York.
2. Catch-up: Runs ONCE at startup/resume if missed while offline.
3. Manual trigger: Provides 'Run Daily Review Now'.
4. Overlap prevention: Enforces thread/process locking; returns 'already_running' if locked.
5. Scope: Imports new eligible submissions and reviews every active exact conversation across all mailbox folders.
6. State updates: Updates system notes, classifications, latest evidence, domain status, and 48-hour timer.
7. Preservation: NEVER overwrites manager notes.
8. Safety: NO automatic closures, Graph draft creation, or sending.
"""

import os
import logging
import threading
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List
from backend.app.domain.models import DomainStatus, CategoryEnum
from backend.app.domain.date_utils import TIMEZONE_NEW_YORK
from backend.app.application.import_service import ImportService
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.infrastructure.graph_client import MicrosoftGraphClient
from backend.app.domain.consolidated_classifier import (
    PROPOSED_TO_DOMAIN_STATUS,
    classify_record,
)

logger = logging.getLogger("daily_review_engine")


class DailyReviewResult:
    def __init__(
        self,
        run_id: str,
        started_at: str,
        completed_at: str,
        status: str,
        submissions_imported: int,
        conversations_reviewed: int,
        timers_restarted: int,
        manager_actions_flagged: int,
        conversations_updated: int = 0,
        conversation_refresh_errors: int = 0,
        is_catchup: bool = False
    ):
        self.run_id = run_id
        self.started_at = started_at
        self.completed_at = completed_at
        self.status = status  # "completed", "already_running", "error"
        self.submissions_imported = submissions_imported
        self.conversations_reviewed = conversations_reviewed
        self.timers_restarted = timers_restarted
        self.manager_actions_flagged = manager_actions_flagged
        self.conversations_updated = conversations_updated
        self.conversation_refresh_errors = conversation_refresh_errors
        self.is_catchup = is_catchup

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "submissions_imported": self.submissions_imported,
            "conversations_reviewed": self.conversations_reviewed,
            "timers_restarted": self.timers_restarted,
            "manager_actions_flagged": self.manager_actions_flagged,
            "conversations_updated": self.conversations_updated,
            "conversation_refresh_errors": self.conversation_refresh_errors,
            "is_catchup": self.is_catchup
        }


class DailyReviewEngine:
    def __init__(
        self,
        import_service: Optional[ImportService] = None,
        persistence: Optional[EncryptedPersistenceEngine] = None,
        graph_client: Optional[MicrosoftGraphClient] = None
    ):
        self.import_service = import_service or ImportService()
        self.persistence = persistence or EncryptedPersistenceEngine()
        self.graph_client = graph_client or (
            self.import_service.graph_client
            if isinstance(self.import_service, ImportService)
            else MicrosoftGraphClient()
        )
        # Unit tests commonly inject a minimal import-service double. They must
        # opt in with an explicit Graph double before conversation refresh is
        # attempted; production ImportService always enables this path.
        self._mailbox_refresh_enabled = graph_client is not None or isinstance(
            self.import_service, ImportService
        )
        self._review_lock = threading.Lock()
        self._scheduler_stop = threading.Event()
        self._scheduler_thread: Optional[threading.Thread] = None

    def is_running(self) -> bool:
        """Check if daily review is currently running."""
        return self._review_lock.locked()

    def is_scheduler_active(self) -> bool:
        return bool(self._scheduler_thread and self._scheduler_thread.is_alive())

    def start_scheduler(self) -> bool:
        """Start the single local 8:00 AM America/New_York review daemon."""
        if os.environ.get("SCHEDULER_ENABLED", "False").lower() not in ("true", "1", "yes"):
            return False
        if self.is_scheduler_active():
            return True
        self._scheduler_stop.clear()
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="follow-up-daily-review",
            daemon=True,
        )
        self._scheduler_thread.start()
        return True

    def stop_scheduler(self) -> None:
        self._scheduler_stop.set()
        if self.is_scheduler_active():
            self._scheduler_thread.join(timeout=2.0)

    def next_scheduled_run(self, now_ny: Optional[datetime] = None) -> datetime:
        now_ny = now_ny or datetime.now(TIMEZONE_NEW_YORK)
        next_run = now_ny.replace(hour=8, minute=0, second=0, microsecond=0)
        if now_ny >= next_run:
            next_run += timedelta(days=1)
        return next_run

    def _scheduler_loop(self) -> None:
        while not self._scheduler_stop.is_set():
            now_ny = datetime.now(TIMEZONE_NEW_YORK)
            wait_seconds = max(0.0, (self.next_scheduled_run(now_ny) - now_ny).total_seconds())
            if self._scheduler_stop.wait(wait_seconds):
                return
            try:
                self.run_daily_review(is_catchup=False)
            except Exception as exc:
                logger.error("Scheduled daily review failed: %s", exc)

    def check_and_run_startup_catchup(self) -> Optional[DailyReviewResult]:
        """
        Check if 8:00 AM America/New_York daily review was missed while offline.
        If missed, executes catch-up review ONCE.
        """
        if os.environ.get("SCHEDULER_ENABLED", "False").lower() not in ("true", "1", "yes"):
            return None
        if os.environ.get("READ_ONLY", "False").lower() in ("true", "1", "yes"):
            logger.info("READ_ONLY mode active: Skipping startup daily review catchup")
            return None

        now_ny = datetime.now(TIMEZONE_NEW_YORK)
        target_today = now_ny.replace(hour=8, minute=0, second=0, microsecond=0)

        # If current time is past 8:00 AM today
        if now_ny >= target_today:
            last_run_iso = self._get_last_review_timestamp()
            if not last_run_iso:
                return self.run_daily_review(is_catchup=True)

            try:
                last_run_dt = datetime.fromisoformat(last_run_iso).astimezone(TIMEZONE_NEW_YORK)
                if last_run_dt < target_today:
                    return self.run_daily_review(is_catchup=True)
            except Exception:
                return self.run_daily_review(is_catchup=True)

        return None

    def run_daily_review(self, is_catchup: bool = False) -> DailyReviewResult:
        """
        Execute daily review workflow with overlap protection.
        """
        if not self._review_lock.acquire(blocking=False):
            return DailyReviewResult(
                run_id="none",
                started_at=datetime.now(timezone.utc).isoformat(),
                completed_at=datetime.now(timezone.utc).isoformat(),
                status="already_running",
                submissions_imported=0,
                conversations_reviewed=0,
                timers_restarted=0,
                manager_actions_flagged=0,
                is_catchup=is_catchup
            )

        run_id = f"rev-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        started_at = datetime.now(timezone.utc).isoformat()
        timers_restarted = 0
        manager_actions_flagged = 0
        conversations_updated = 0
        conversation_refresh_errors = 0

        try:
            # 1. Import new eligible submissions from Submissions folder
            import_report = self.import_service.run_import(preview=False)
            submissions_imported = import_report.messages_imported

            auth_allowed = import_report.auth_status == "ok" or (
                import_report.auth_status == "synthetic_test_data"
                and os.environ.get("ENVIRONMENT", "production").lower() == "test"
            )
            if not auth_allowed:
                return DailyReviewResult(
                    run_id=run_id,
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    status="error",
                    submissions_imported=0,
                    conversations_reviewed=0,
                    timers_restarted=0,
                    manager_actions_flagged=0,
                    is_catchup=is_catchup,
                )

            # 2. Review every active exact conversation
            records = self.persistence.list_records()
            conversations_reviewed = len(records)

            for rec in records:
                snapshot = self.persistence.get_record_payload_snapshot(rec.id)
                if not snapshot:
                    continue
                payload, version, stored_status = snapshot

                # Refresh the authoritative primary conversation even when the
                # original submission is no longer visible in the Submissions
                # folder. Also refresh every manager-confirmed linked interview
                # conversation. Identity is always the exact Graph
                # conversationId; job/EP/candidate metadata is never used here.
                mailbox_changed = False
                if self._mailbox_refresh_enabled and import_report.auth_status == "ok":
                    primary_messages, primary_status = self.graph_client.fetch_exact_conversation_messages(
                        rec.conversation_id
                    )
                    if primary_status == "ok" and primary_messages:
                        merged_messages, primary_changed = self._merge_refreshed_messages(
                            payload.get("thread_messages", []), primary_messages
                        )
                        if primary_changed:
                            payload["thread_messages"] = merged_messages
                            payload["thread_message_count"] = len(merged_messages)
                            mailbox_changed = True
                    else:
                        conversation_refresh_errors += 1

                linked_conversations = payload.get("linked_conversations", [])
                if self._mailbox_refresh_enabled and import_report.auth_status == "ok":
                    for linked in linked_conversations:
                        if not isinstance(linked, dict) or not linked.get("conversation_id"):
                            continue
                        linked_messages, linked_status = self.graph_client.fetch_exact_conversation_messages(
                            linked["conversation_id"]
                        )
                        if linked_status == "ok" and linked_messages:
                            merged_linked, linked_changed = self._merge_refreshed_messages(
                                linked.get("thread_messages", []), linked_messages
                            )
                            if linked_changed:
                                linked["thread_messages"] = merged_linked
                                mailbox_changed = True
                        else:
                            conversation_refresh_errors += 1

                if mailbox_changed:
                    payload["linked_conversations"] = linked_conversations
                    try:
                        version = self.persistence.update_record_optimistically(
                            rec.id, payload, stored_status, version
                        )
                        conversations_updated += 1
                    except ValueError:
                        logger.warning("Record changed during mailbox refresh; deferred to next run")
                        continue

                thread_messages = payload.get("thread_messages", [])
                if not thread_messages or stored_status == DomainStatus.CLOSED.value:
                    continue

                # Manager decisions are authoritative. A mailbox refresh may add
                # evidence, but the unattended review must not reinterpret or
                # overwrite an outcome/interview decision. The one permitted
                # derived transition is the completed-interview feedback timer.
                timeline = payload.get("timeline", [])
                has_manager_decision = any(
                    isinstance(entry, dict) and entry.get("event_type") in {
                        "MANAGER_OUTCOME_DECISION",
                        "INTERVIEW_CONFIRMATION_DECISION",
                    }
                    for entry in timeline
                )
                if has_manager_decision:
                    if (
                        stored_status == DomainStatus.AWAITING_FEEDBACK.value
                        and payload.get("interview_state") == "completed"
                        and payload.get("feedback_due_at")
                    ):
                        try:
                            due_at = datetime.fromisoformat(payload["feedback_due_at"])
                            if due_at.tzinfo is None:
                                due_at = due_at.replace(tzinfo=timezone.utc)
                            if datetime.now(timezone.utc) >= due_at:
                                payload["domain_status"] = DomainStatus.FEEDBACK_DUE.value
                                self.persistence.update_record_optimistically(
                                    rec.id, payload, DomainStatus.FEEDBACK_DUE.value, version
                                )
                                manager_actions_flagged += 1
                        except (TypeError, ValueError):
                            logger.warning("Invalid manager feedback timer; preserved for review")
                    continue

                authoritative_followup_ids = []
                for entry in payload.get("timeline", []):
                    if isinstance(entry, dict) and entry.get("event_type") == "MANAGER_FOLLOWUP":
                        message_id = entry.get("message_id") or entry.get("graph_immutable_id")
                        if message_id:
                            authoritative_followup_ids.append(message_id)

                result = classify_record(
                    rec.graph_immutable_id,
                    thread_messages,
                    datetime.now(TIMEZONE_NEW_YORK),
                    authoritative_followup_ids=authoritative_followup_ids,
                    timeline=timeline,
                    linked_conversations=payload.get("linked_conversations", []),
                )
                target_status = PROPOSED_TO_DOMAIN_STATUS.get(result.proposed_status)
                if target_status is None and result.proposed_status in {s.value for s in DomainStatus}:
                    target_status = DomainStatus(result.proposed_status)
                if target_status is None:
                    target_status = DomainStatus.NEEDS_REVIEW

                prior_derived = (
                    payload.get("classification_category"),
                    payload.get("classification_status"),
                    payload.get("reason_code"),
                    payload.get("timer_anchor_type"),
                )
                new_derived = (
                    result.category,
                    result.proposed_status,
                    result.reason_code,
                    result.timer_anchor_type,
                )
                if stored_status != target_status.value or prior_derived != new_derived:
                    payload["classification_category"] = result.category
                    payload["classification_status"] = result.proposed_status
                    payload["reason_code"] = result.reason_code
                    payload["timer_anchor_type"] = result.timer_anchor_type
                    payload["classification_timestamp"] = datetime.now(timezone.utc).isoformat()
                    payload["domain_status"] = target_status.value
                    try:
                        self.persistence.update_record_optimistically(
                            rec.id, payload, target_status.value, version
                        )
                    except ValueError:
                        logger.warning("Record changed during daily review; deferred to next run")
                        continue

                if target_status == DomainStatus.PENDING_FOLLOW_UP:
                    timers_restarted += 1
                elif target_status == DomainStatus.MANAGER_ACTION_REQUIRED:
                    manager_actions_flagged += 1

            completed_at = datetime.now(timezone.utc).isoformat()
            self._save_last_review_timestamp(completed_at)

            return DailyReviewResult(
                run_id=run_id,
                started_at=started_at,
                completed_at=completed_at,
                status="completed",
                submissions_imported=submissions_imported,
                conversations_reviewed=conversations_reviewed,
                timers_restarted=timers_restarted,
                manager_actions_flagged=manager_actions_flagged,
                conversations_updated=conversations_updated,
                conversation_refresh_errors=conversation_refresh_errors,
                is_catchup=is_catchup
            )
        finally:
            self._review_lock.release()

    @staticmethod
    def _merge_refreshed_messages(
        existing: List[Dict[str, Any]], refreshed: List[Dict[str, Any]]
    ) -> tuple[List[Dict[str, Any]], bool]:
        """Merge mailbox facts without discarding richer encrypted local content.

        Graph refresh queries intentionally fetch lightweight message facts for
        classification. Existing full bodies and attachment content therefore
        remain authoritative whenever the refreshed representation omits them.
        """
        merged = [dict(message) for message in existing if isinstance(message, dict)]
        positions = {
            str(message.get("id")): index
            for index, message in enumerate(merged)
            if message.get("id")
        }

        def merge_attachments(old_items: Any, new_items: Any) -> Any:
            if not isinstance(new_items, list):
                return old_items if old_items is not None else new_items
            if not isinstance(old_items, list):
                return new_items
            old_by_id = {
                str(item.get("id")): item
                for item in old_items
                if isinstance(item, dict) and item.get("id")
            }
            result = []
            for item in new_items:
                if not isinstance(item, dict) or not item.get("id"):
                    result.append(item)
                    continue
                prior = old_by_id.pop(str(item["id"]), None)
                combined = dict(prior or {})
                combined.update(item)
                result.append(combined)
            result.extend(old_by_id.values())
            return result

        for message in refreshed:
            if not isinstance(message, dict):
                continue
            message_id = str(message.get("id") or "")
            if message_id and message_id in positions:
                index = positions[message_id]
                combined = dict(merged[index])
                for key, value in message.items():
                    if key == "attachments":
                        combined[key] = merge_attachments(combined.get(key), value)
                    elif value is not None:
                        combined[key] = value
                merged[index] = combined
            else:
                positions[message_id] = len(merged)
                merged.append(dict(message))

        def canonical(messages: List[Dict[str, Any]]) -> List[str]:
            return sorted(
                json.dumps(message, sort_keys=True, separators=(",", ":"), default=str)
                for message in messages
            )

        return merged, canonical(merged) != canonical(existing)

    def _get_last_review_timestamp(self) -> Optional[str]:
        """Retrieve last review timestamp from state store."""
        try:
            with self.persistence._get_connection() as conn:
                cursor = conn.execute("SELECT value FROM system_state WHERE key = 'last_daily_review_at'")
                row = cursor.fetchone()
                return row["value"] if row else None
        except Exception:
            return None

    def _save_last_review_timestamp(self, timestamp_iso: str) -> None:
        """Save last review timestamp to state store."""
        try:
            with self.persistence._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS system_state (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                """)
                conn.execute("""
                    INSERT OR REPLACE INTO system_state (key, value) VALUES ('last_daily_review_at', ?)
                """, (timestamp_iso,))
                conn.commit()
        except Exception:
            pass
