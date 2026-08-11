#!/usr/bin/env python3
"""
Idempotent Migration Script: migrate_legacy_reasons.py
Normalizes legacy workflow_status and close_reason values to canonical enums.

Features:
- Timestamped SQLite database backup before writing
- --dry-run option
- Post-migration validation
- Written report output (migration_report_YYYYMMDD_HHMMSS.txt)
"""

import os
import sys
import json
import uuid
import shutil
import argparse
from datetime import datetime, timezone

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.domain.models import (
    WorkflowStatus, CloseReason, AuditEventType, normalize_close_reason
)
from backend.app.domain.workflow_view_composer import LEGACY_STATUS_MAP
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine, SimplePayloadEncryptor


def run_migration(dry_run: bool = False):
    engine = EncryptedPersistenceEngine()
    db_path = engine.db_path
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    report_lines = []
    report_lines.append(f"=== Workflow System Legacy Migration Report ({timestamp_str}) ===")
    report_lines.append(f"Target Database: {db_path}")
    report_lines.append(f"Mode: {'DRY RUN (No changes written)' if dry_run else 'LIVE MIGRATION'}")
    report_lines.append("")

    # 1. Timestamped SQLite Backup
    if not dry_run and os.path.exists(db_path):
        backup_dir = os.path.expanduser("~/.recruitment_agent/backups")
        os.makedirs(backup_dir, exist_ok=True)
        backup_path = os.path.join(backup_dir, f"followup_backup_{timestamp_str}.db")
        shutil.copy2(db_path, backup_path)
        report_lines.append(f"✓ Created timestamped backup: {backup_path}")
    else:
        report_lines.append("• Backup skipped (dry run or file not found)")

    # 2. Scan & Normalize Records
    total_scanned = 0
    total_updated = 0
    status_updated_count = 0
    reason_updated_count = 0
    classification_updated_count = 0
    audit_events_written = 0

    valid_statuses = {s.value for s in WorkflowStatus}
    valid_reasons = {r.value for r in CloseReason}

    with engine._get_connection() as conn:
        cursor = conn.execute(
            "SELECT id, domain_status, payload_ciphertext, record_version, "
            "classification_category, classification_updated_at, classifier_version "
            "FROM submission_records"
        )
        rows = cursor.fetchall()
        total_scanned = len(rows)

        for row in rows:
            rec_id = row["id"]
            orig_status = row["domain_status"]
            orig_version = row["record_version"]
            payload_json = engine.encryptor.decrypt(row["payload_ciphertext"])
            payload = json.loads(payload_json)

            changes = {}

            # Status normalization
            # Ensure canonical status for both DB column and payload
            canonical_status = LEGACY_STATUS_MAP.get(orig_status, WorkflowStatus.NEEDS_REVIEW).value
            payload_status = payload.get("domain_status")
            canonical_payload_status = LEGACY_STATUS_MAP.get(payload_status, canonical_status).value if payload_status else canonical_status

            final_status = canonical_status
            if orig_status != final_status or payload_status != final_status:
                changes["domain_status"] = {"old": f"db:{orig_status},payload:{payload_status}", "new": final_status}

            # Close reason normalization
            orig_reason = payload.get("close_reason")
            canonical_reason = None
            if orig_reason:
                try:
                    canonical_reason = normalize_close_reason(str(orig_reason)).value
                    if orig_reason != canonical_reason:
                        changes["close_reason"] = {"old": orig_reason, "new": canonical_reason}
                except ValueError:
                    pass

            # Classification fields backfill / normalization
            persisted_cat = payload.get("classification_category")
            cat_changed = False
            if not persisted_cat:
                # Try classifier
                try:
                    from backend.app.domain.consolidated_classifier import refresh_classification_snapshot
                    res = refresh_classification_snapshot(
                        payload,
                        graph_immutable_id=payload.get("graph_immutable_id", f"graph-{rec_id}"),
                        evaluation_time=datetime.now(timezone.utc)
                    )
                    if res and res.category:
                        persisted_cat = res.category
                except Exception:
                    pass

                if not persisted_cat and payload.get("manager_outcome_category"):
                    persisted_cat = payload.get("manager_outcome_category")

                if not persisted_cat:
                    persisted_cat = "Needs Review"

                changes["classification_category"] = {"old": None, "new": persisted_cat}
                cat_changed = True

            updated_at = payload.get("classification_updated_at")
            if not updated_at:
                updated_at = datetime.now(timezone.utc).isoformat()
                changes["classification_updated_at"] = {"old": None, "new": updated_at}

            classifier_ver = payload.get("classifier_version")
            if not classifier_ver:
                classifier_ver = "v1.0"
                changes["classifier_version"] = {"old": None, "new": classifier_ver}

            if changes:
                total_updated += 1
                new_version = orig_version + 1
                now_iso = datetime.now(timezone.utc).isoformat()

                if "domain_status" in changes:
                    status_updated_count += 1
                if "close_reason" in changes:
                    reason_updated_count += 1
                if "classification_category" in changes or "classification_updated_at" in changes or "classifier_version" in changes:
                    classification_updated_count += 1

                payload["domain_status"] = final_status
                if canonical_reason:
                    payload["close_reason"] = canonical_reason
                payload["classification_category"] = persisted_cat
                payload["classification_updated_at"] = updated_at
                payload["classifier_version"] = classifier_ver
                payload["record_version"] = new_version

                # Append SYSTEM_MIGRATION audit event
                from backend.app.domain.audit_trail import create_audit_event
                timeline = payload.get("timeline", [])
                evt = create_audit_event(
                    record_id=rec_id,
                    event_type=AuditEventType.SYSTEM_MIGRATION.value,
                    actor="system/migration",
                    prior_status=orig_status or final_status,
                    resulting_status=final_status,
                    record_version=new_version,
                    body_preview=f"[Audit: SYSTEM_MIGRATION] Normalized legacy fields: {json.dumps(changes)}",
                    extra_fields={"field_changes": changes}
                )
                timeline.append(evt)
                payload["timeline"] = timeline
                audit_events_written += 1

                if not dry_run:
                    new_ciphertext = engine.encryptor.encrypt(json.dumps(payload))
                    conn.execute("""
                        UPDATE submission_records
                        SET domain_status = ?,
                            payload_ciphertext = ?,
                            record_version = ?,
                            classification_category = ?,
                            classification_updated_at = ?,
                            classifier_version = ?
                        WHERE id = ?
                    """, (
                        final_status,
                        new_ciphertext,
                        new_version,
                        persisted_cat,
                        updated_at,
                        classifier_ver,
                        rec_id
                    ))

        if not dry_run:
            conn.commit()

    # 3. Post-Migration Validation
    report_lines.append("")
    report_lines.append("=== Summary Statistics ===")
    report_lines.append(f"Total Records Scanned: {total_scanned}")
    report_lines.append(f"Total Records Updated: {total_updated}")
    report_lines.append(f"Status Fields Normalized: {status_updated_count}")
    report_lines.append(f"Close Reason Fields Normalized: {reason_updated_count}")
    report_lines.append(f"Classification Fields Backfilled/Updated: {classification_updated_count}")
    report_lines.append(f"Audit Events Recorded: {audit_events_written}")

    if not dry_run:
        report_lines.append("")
        report_lines.append("=== Post-Migration Validation ===")
        invalid_status_count = 0
        invalid_reason_count = 0
        missing_classification_count = 0

        with engine._get_connection() as conn:
            cursor = conn.execute(
                "SELECT domain_status, payload_ciphertext, "
                "classification_category, classification_updated_at, classifier_version "
                "FROM submission_records"
            )
            for row in cursor.fetchall():
                st = row["domain_status"]
                if st not in valid_statuses:
                    invalid_status_count += 1
                pl = json.loads(engine.encryptor.decrypt(row["payload_ciphertext"]))
                cr = pl.get("close_reason")
                if cr and cr not in valid_reasons:
                    invalid_reason_count += 1

                cat = row["classification_category"] or pl.get("classification_category")
                up_at = row["classification_updated_at"] or pl.get("classification_updated_at")
                cver = row["classifier_version"] or pl.get("classifier_version")
                if not cat or not up_at or not cver:
                    missing_classification_count += 1

        if invalid_status_count == 0 and invalid_reason_count == 0 and missing_classification_count == 0:
            report_lines.append("✓ Validation Passed: 0 invalid statuses, 0 invalid close reasons, 0 missing classification fields.")
        else:
            report_lines.append(
                f"⚠ Validation Warning: {invalid_status_count} invalid statuses, "
                f"{invalid_reason_count} invalid close reasons, "
                f"{missing_classification_count} missing classification fields."
            )

    report_text = "\n".join(report_lines)
    print(report_text)

    # Save report
    report_filename = f"migration_report_{timestamp_str}.txt"
    with open(report_filename, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\nMigration report saved to: {report_filename}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate legacy workflow statuses and close reasons.")
    parser.add_argument("--dry-run", action="store_true", help="Scan and report without modifying database.")
    args = parser.parse_args()
    run_migration(dry_run=args.dry_run)
