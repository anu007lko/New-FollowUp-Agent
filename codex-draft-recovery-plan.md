# Codex Draft Recovery Completion Plan

## Objective

Make the manager-approved Outlook Reply All draft workflow real, fail-closed, crash-recoverable, and verifiably unable to send mail or create duplicate drafts.

## Work

1. [Complete] Harden persistent draft-operation states and authenticated encrypted payload storage.
2. [Complete] Replace the live adapter with verified create, recovery, and exact read-back operations.
3. [Complete] Add status, read-only reconciliation, explicit resume-finalization, and safe reset routes.
4. [Complete] Complete the Draft Wizard recovery UI without automatic retries or Send controls.
5. [Complete] Add crash-injection, security, persistence, API, and frontend regression tests.
6. [Complete] Run full automated suites and a read-only local service smoke test.
7. [Pending manager approval] Enable exactly one live-draft test after a named record is selected.

## Verification result

- Backend: 319 passed.
- Frontend: 49 passed.
- Production frontend build: passed.
- Authoritative database: quick_check ok; 111 records; zero existing draft operations.
- Local server: 127.0.0.1:8000, live integrations disabled; draft mutation gate returns 403.
- Legacy service: 127.0.0.1:8765 untouched.

## Safety gates

- No Mail.Send scope, route, control, or Graph send operation.
- No live Graph writes during implementation or automated testing.
- Temporary databases for tests; authoritative DB backed up before migration.
- Immutable message/conversation identities only.
- Old app and port 8765 untouched.
