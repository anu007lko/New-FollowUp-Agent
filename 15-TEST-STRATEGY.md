# Test Strategy

## Test levels

Unit tests cover domain rules, time/DST, transitions, policy, parsers, and projections. Contract tests cover local API, Graph adapter, Ollama schema, encryption, and persistence. Integration tests use controlled fixtures/mocks and a separately approved non-production mailbox only if authorized. End-to-end tests exercise manager journeys without sending. Security, accessibility, performance, migration, retention, backup/restore, and rollback tests complete the release suite.

## Critical scenario matrix

- Source folder isolation and deterministic TCS inclusion/exclusion (lookalike subject without `tcs.com` To/CC excluded).
- Immutable source identity survives folder movement; exact conversation retrieval spans folders.
- Same Job ID/different conversation never links; changed subject/same conversation does link.
- Category transition tests:
  - Acknowledgement sets `In Evaluation` and restarts 48h timer from message timestamp.
  - Feedback / request for info sets `Manager Action Required` and pauses timing until marked handled.
  - Rejection shows `Client Rejected` and prompts manager closure with reason `Client rejected`.
  - Position closed shows `Position Closed` and prompts manager closure with reason `Position closed`.
  - Duplicate/already submitted moves to `Needs Review` prompting manager decision; zero auto-closures.
  - Unrelated moves to `Needs Review` without resetting follow-up timer.
  - Uncertain or conflicting classifications remain in `Needs Review`.
- 48 calendar hours across EST/EDT transitions, leap day, boundary instant, and system clock change.
- Interview scheduled time passes → confirmation requested; Completed starts 48h feedback timer; Rescheduled requires new date/time entry; Cancelled and Not Confirmed move to `Needs Review`; zero interview outcomes auto-close.
- Close reason validation and mandatory Other note.
- No action occurs without manager command; page refresh/restart does not trigger activity.
- Draft safety tests: empty default BCC field; manager additions/removals restricted to `@clifyx.com`; external/historical BCC excluded; recipient modifications invalidate prior draft approvals.
- Double-click/timeout/retry creates at most one draft.
- Static/runtime proof of no send route/method, loopback binding to `127.0.0.1`, and no `Mail.Send`.
- Encryption at rest (SQLCipher/encrypted SQLite + Keychain), key loss behavior, log redaction, malicious attachment, localhost CSRF/origin attack.
- Three-month reduction removes all content/derived copies and leaves operational record; manager-triggered encrypted local backup export and restore test; restore immediately executes retention sweep before content access.
- Domain status cannot be overwritten by a display projection.


## Evidence and environments

Tests produce requirement-linked results, redacted logs, screenshots where useful, and build/config hashes. Synthetic data is default. Real mailbox testing requires explicit approval and never sends. No test-only security bypass is permitted; test seams use dependency substitution with production controls intact.

## Exit criteria

100% critical requirements covered and passing; no critical/high security defects; no unresolved data-loss/identity/send defect; agreed performance/accessibility targets met; rollback and retention rehearsed; owner approves evidence.

## Final release suite — 2026-08-08

Run the full isolated backend suite, frontend tests/build, browser journeys, API/CSRF matrix, encrypted DB audit, Graph identity/scope audit, Reply All/read-back reconciliation, scheduler 08:00/DST/overlap/catch-up tests, backup quarantine restore, static no-send scan, and loopback/legacy-port checks. Real checks may create one approved draft but never send.

Manual-review regression coverage must prove: the UI obtains CSRF and calls the daily-review endpoint; exact primary and linked conversation IDs are refreshed; changed messages reach encrypted persistence before classification; manager notes/decisions survive; the dashboard/open record reload; and no draft or send endpoint is called.

## Visual-release quality gate — 2026-08-09

For every approved visual-system release: run the full backend test suite (352/352 passing), frontend unit suite (50/50 passing), TypeScript validation, production Vite build, desktop and responsive browser journeys, runtime-console check, and horizontal-overflow check. Verify reduced-motion behavior and keyboard focus. Screenshot comparison must cover the shell, dashboard focus card, conversation path, work queue, record workspace, interviews, retention, and manager-action dialog. A presentation-only pass must prove zero Graph calls, database mutations, draft creation, and sends.

