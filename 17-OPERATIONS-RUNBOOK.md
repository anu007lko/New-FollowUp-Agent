# Operations Runbook

## Start-of-session checks

Confirm expected Mac user, FileVault/keychain availability, loopback bind, sufficient disk, encrypted store health, configured mailbox/folder/model/time zone, Graph permission allowlist, and Ollama model availability. Readiness checks must not trigger login, consent, mailbox scan, draft, or send.

## Normal operation & Daily Review Schedule

Manager starts import, reviews import report, opens a record, explicitly reviews its conversation, resolves Needs Review, and chooses Follow-up or Close. Draft creation follows suggestion → edit → approve → recipient preview → explicit creation. Manager verifies and sends only in Outlook.

### Approved Daily Review Engine

1. **Schedule:** Runs daily at **8:00 AM America/New_York** time.
2. **Missed-Run Catch-Up:** If the Mac or application was offline or unavailable at 8:00 AM, the engine detects the missed schedule upon next startup/resume and executes **ONCE** as a catch-up review.
3. **Manual Trigger (Run Now):** Provides an explicit "Run Daily Review Now" option in the UI and API endpoint (`POST /api/v1/daily-review/run`).
4. **Overlap Prevention:** Enforces thread/process locking; overlapping runs return `already_running` status without interfering.
5. **Scope:** Imports new eligible submissions from the `Submissions` folder starting July 10, 2026 midnight EDT (`2026-07-10T04:00:00Z`), and reviews every active exact conversation across all mailbox folders (including `Sent Items`).
6. **State Updates:** Automatically updates system notes, classifications, latest evidence timestamps/senders, domain statuses (`Acknowledgement` -> `InEvaluation` + 48h timer restart; `Feedback/Request for Info` -> `ManagerActionRequired`), and 48-hour timer.
7. **Preservation:** **NEVER overwrites manager notes.** Manager notes are stored separately in `manager_notes` and preserved untouched.
8. **Prohibitions:** **NO automatic closures, NO Graph draft creation, and NO email sending.**

## Failure playbooks

- Graph unavailable/throttled: stop operation safely, retain checkpoint, honor retry guidance, retry manually; never broaden permission.
- Token/consent error: display exact redacted condition and stop; do not launch login/consent without instruction.
- Ollama unavailable/invalid: retain deterministic result, mark advisory unavailable/Needs Review, permit no inferred closure.
- Partial conversation: label incomplete, block high-confidence automation-like conclusions, retry review.
- Draft timeout: reconcile operation/draft ID before retry; never blind-create.
- Key/store failure: stop content access/writes, preserve evidence, restore from approved encrypted backup; never reset key/store casually.
- Disk pressure: stop attachment import before corruption, report required capacity, do not delete outside retention plan.
- Retention failure: quarantine failed items, show report, repair and rerun; verify backups.

## Backup and recovery

M6 delivers a manager-triggered encrypted local backup and tested restore process. The backup protects local decisions, notes, operational records, and audit history. Outlook remains untouched and serves as the primary source for rebuilding mailbox content. 

### Approved Rollback & Quarantine Recovery Procedure

> [!CAUTION]
> **NEVER** copy a database file directly over the active database (`~/.recruitment_agent/records.db`) while the server process is running. Doing so risks database corruption, race conditions, and key mismatch.

When performing a rollback or restoring from an encrypted backup:
1. **Stop Application Server:** Stop the running uvicorn/backend server process before touching any storage files.
2. **Restore to Quarantine:** Execute the approved restore workflow (`restore_backup_to_quarantine` or `POST /api/v1/backup/restore`) to decrypt the `.enc` backup into an isolated quarantine workspace.
3. **Validate Database & Payload Integrity:**
   - Execute SQLite `PRAGMA quick_check;` on the restored quarantine database.
   - Decrypt and verify all 91 records via `EncryptedPersistenceEngine` with the Keychain-backed master key.
   - Confirm expected record counts (89 complete, 2 incomplete) and manager decisions.
4. **Retention Sweep:** Quarantine automatically evaluates calendar-month retention expiry. Review and prune any expired records prior to promotion.
5. **Promote Quarantine to Active:** Atomically swap the verified quarantined database to the active path (`~/.recruitment_agent/records.db`).
6. **Restart in Safe Mode:** Relaunch the application server in `APP_MODE=manager_local` with `READ_ONLY=True`.

## Diagnostics and incident handling

Collect redacted correlation IDs, versions, timestamps, operation states, and permission/config status. Never collect tokens or content by default. For suspected exposure, stop app, isolate device, preserve minimal audit evidence, notify owner/security, assess mailbox/token/key actions, and document resolution.

## Change rule

No direct production edits. All changes come from the authoritative repository, with reviewed clean boundaries, test evidence, rollback, and explicit approval.

## Approved production start — 2026-08-08

Run one server on `127.0.0.1:8000` with `APP_MODE=manager_local`, `READ_ONLY=False`, `GRAPH_ENABLED=True`, `DRAFTS_ENABLED=True`, `MAIL_SEND_ENABLED=False`, `OLLAMA_ENABLED=False`, `SCHEDULER_ENABLED=True`, `ENVIRONMENT=production`. Verify an encrypted backup first. After start, confirm scheduler active/next 08:00 ET, `Mail.Send` absent, DB quick-check `ok`, and port `8765` unchanged.

If the Mac missed 08:00, one catch-up runs after startup. It may import and update deterministic status, but cannot create drafts. Managers approve drafts and send manually in Outlook.

## Manual real-time review

Select **Review mailbox now** in the top bar. Keep the app open until the result message appears. The action imports new eligible Submissions messages, refreshes all tracked primary and confirmed linked interview conversations across Outlook folders, applies deterministic rules, and reloads the screen. If warnings are reported, existing data remains available and the next manual/daily run retries failed conversations. Do not interpret the browser reload control as mailbox review. No draft is created and no email is sent.

## Visual verification after a frontend update — 2026-08-09

Open Dashboard, Work Queue, Interviews, Retention & Operations, one record workspace, and one manager-action dialog at both normal desktop width and a narrower browser width. Confirm that no content is clipped, focus is visible, the local-only/no-send boundary is readable, and motion remains restrained. A broken visual build is rolled back by restoring the previously verified frontend bundle; no database or mailbox recovery is involved.
