"""
Import application service orchestrating manual import preview and execution.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from backend.app.domain.models import (
    ImportReport, ImportItemSummary, SubjectMetadata, DomainStatus
)
from backend.app.domain.eligibility import evaluate_tcs_eligibility
from backend.app.domain.subject_parser import parse_subject_metadata
from backend.app.infrastructure.graph_client import MicrosoftGraphClient
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine


class ImportService:
    def __init__(
        self,
        graph_client: Optional[MicrosoftGraphClient] = None,
        persistence: Optional[EncryptedPersistenceEngine] = None
    ):
        self.graph_client = graph_client or MicrosoftGraphClient()
        self.persistence = persistence or EncryptedPersistenceEngine()

    def run_import(self, preview: bool = True) -> ImportReport:
        """
        Execute manager-triggered manual import from Submissions folder.
        If preview=True, performs a read-only dry run without persisting records.
        If preview=False, idempotently persists operational records.
        """
        import_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc).isoformat()

        report = ImportReport(
            import_id=import_id,
            started_at=started_at,
            is_preview=preview
        )

        messages, auth_status, diagnostics = self.graph_client.fetch_submissions_folder_messages()
        report.auth_status = auth_status
        report.messages_scanned = len(messages)

        # Production imports are fail-closed.  An unavailable or rejected token
        # is an operational error, never an empty/successful import.
        if auth_status not in ("ok", "synthetic_test_data"):
            report.error_count += 1
            report.completed_at = datetime.now(timezone.utc).isoformat()
            return report

        for msg in messages:
            graph_immutable_id = msg.get("id", "")
            conversation_id = msg.get("conversationId", "")
            subject = msg.get("subject", "")
            received_at = msg.get("receivedDateTime", started_at)

            # Extract recipients
            to_list = [r.get("emailAddress", {}).get("address", "") for r in msg.get("toRecipients", [])]
            cc_list = [r.get("emailAddress", {}).get("address", "") for r in msg.get("ccRecipients", [])]
            to_list = [e for e in to_list if e]
            cc_list = [e for e in cc_list if e]

            # Evaluate TCS eligibility
            is_eligible, exclusion_reason, tcs_recipients, co_recipients = evaluate_tcs_eligibility(
                to_recipients=to_list,
                cc_recipients=cc_list,
                subject=subject
            )

            # Parse subject metadata
            metadata = parse_subject_metadata(subject)

            item_summary = ImportItemSummary(
                graph_immutable_id=graph_immutable_id,
                conversation_id=conversation_id,
                subject=subject,
                received_at=received_at,
                is_eligible=is_eligible,
                exclusion_reason=exclusion_reason,
                tcs_recipients=tcs_recipients,
                co_recipients=co_recipients,
                metadata=metadata
            )

            report.items.append(item_summary)

            if not is_eligible:
                report.excluded_count += 1
                continue

            report.messages_eligible += 1

            exists = self.persistence.exists_by_immutable_id(graph_immutable_id)

            if not preview:
                if auth_status == "synthetic_test_data":
                    thread_messages, thread_status = [msg], "ok"
                else:
                    thread_messages, thread_status = self.graph_client.fetch_exact_conversation_messages(
                        conversation_id
                    )
                if thread_status != "ok" or not thread_messages:
                    report.error_count += 1
                    continue
                # Perform idempotent write to encrypted database
                record_id = str(uuid.uuid4())
                payload_data = {
                    "graph_immutable_id": graph_immutable_id,
                    "conversation_id": conversation_id,
                    "subject": subject,
                    "received_at": received_at,
                    "metadata": metadata.model_dump(),
                    "tcs_recipients": tcs_recipients,
                    "co_recipients": co_recipients,
                    "to_recipients": to_list,
                    "cc_recipients": cc_list,
                    "thread_messages": thread_messages,
                    "thread_message_count": len(thread_messages),
                }
                from backend.app.domain.consolidated_classifier import refresh_classification_snapshot
                refresh_classification_snapshot(payload_data, graph_immutable_id=graph_immutable_id)

                is_new, is_dup = self.persistence.upsert_submission(
                    record_id=record_id,
                    graph_immutable_id=graph_immutable_id,
                    conversation_id=conversation_id,
                    job_id=metadata.job_id,
                    ep_reference=metadata.ep_reference,
                    candidate_name=metadata.candidate_name,
                    tcs_eligibility="eligible",
                    domain_status=DomainStatus.NEW_SUBMISSION.value,
                    received_at=received_at,
                    created_at=started_at,
                    payload_data=payload_data
                )
                if is_new:
                    report.messages_imported += 1
                elif is_dup and exists:
                    report.duplicates_skipped += 1
            else:
                # In preview mode, count eligible non-duplicate messages as ready for import
                report.messages_imported += 1

        report.completed_at = datetime.now(timezone.utc).isoformat()
        if not preview:
            self.persistence.save_import_event(report)

        return report
