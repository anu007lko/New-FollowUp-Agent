# Software Requirements Specification (SRS)

## Functional requirements

- FR-001 Bind HTTP listener exclusively to `127.0.0.1`; reject non-loopback Host/origin requests.
- FR-002 Require an active local user session and defend against cross-site requests.
- FR-003 Import only by manager command, from mailbox `tarun@clifyx.com`, folder `Submissions`.
- FR-004 Include a submission only when its original message has at least one `tcs.com` To/CC recipient; allow additional end-client recipients and retain exclusion reason in the import report.
- FR-005 Store immutable source identity and exact Outlook `conversationId`; Job ID and EP reference are informational metadata only.
- FR-006 On manager review, query the whole mailbox for the exact conversation and reconcile all messages.
- FR-007 Preserve message direction, timestamps, recipients, headers needed for identity, body, and attachments during full-retention period.
- FR-008 Classify into the ten approved categories with confidence, evidence, model version, and prompt version.
- FR-009 Route ambiguous/conflicting/low-confidence output to Needs Review; rules may override LLM but must record why.
- FR-010 Evaluate 48 calendar hours in `America/New_York`, DST-aware, from the latest event defined by the workflow rules.
- FR-011 Set Pending Follow-up when an eligible record has no meaningful newer response after the threshold.
- FR-012 Implement category workflow rules:
  - Acknowledgement: set status to `In Evaluation` and restart the 48-calendar-hour timer from that message's timestamp.
  - Feedback or request for information: set status to `Manager Action Required` and pause follow-up timing until manager records action handled; never send automatically.
  - Rejection: display `Client Rejected` and prompt manager closure with reason `Client rejected`.
  - Position closed: display `Position Closed` and prompt manager closure with reason `Position closed`.
  - Duplicate/already submitted: place in `Needs Review` and prompt manager closure or decision; never auto-close.
  - Unrelated: place in `Needs Review` without resetting the follow-up timer.
  - Uncertain or conflicting classifications: remain in `Needs Review`.
  - A newer meaningful message must always be visible with sender, timestamp, evidence, and timer effect.
- FR-012A When a scheduled interview time passes, require manager confirmation of Completed, Rescheduled, Cancelled, or Not confirmed:
  - Completed: starts the 48-hour feedback timer.
  - Rescheduled: requires entry of a new date and time.
  - Cancelled and Not Confirmed: move record to `Needs Review` for immediate manager attention.
  - No interview outcome closes a record automatically.
- FR-013 Never scan, classify, draft, follow up, close, or send on a schedule/background trigger.
- FR-014 Require manager choice of Request Follow-up or Close; close reason is mandatory and Other requires note.
- FR-015 Generate a suggestion locally only after manager request.
- FR-016 Require explicit approval of final draft content and a distinct confirmation to create the Outlook draft.
- FR-017 Create Reply All draft in original conversation; validate To/CC; start every draft with an empty BCC field; permit manager additions/removals for BCC addresses strictly ending in `@clifyx.com`; never copy or accept external/historical BCC; invalidating prior draft approval upon any recipient modification.
- FR-018 Provide no send operation, send route, send UI, or `Mail.Send` permission.
- FR-019 Encrypt full history and attachments at rest using SQLCipher/encrypted SQLite store and macOS Keychain; reduce content after three months to the approved operational record; provide a manager-triggered encrypted local backup and tested restore in M6 protecting local decisions, notes, operational records, and audit history; restores immediately enforce retention before content access.
- FR-020 Attribute actions to a user identity; schema supports multiple managers and authorization boundaries.
- FR-021 Display the latest conversation update, sender, timestamp, meaningful status, timer anchor, due explanation, and any conversation-completeness warning.

## Non-functional requirements

NFR-01 Security: least privilege, secrets outside source, OS-backed key protection via macOS Keychain, audit integrity. Approved tech stack: Python 3.11+ with FastAPI backend, React with TypeScript and Vite frontend, SQLite with SQLCipher (or reviewed encrypted SQLite design), bound exclusively to `127.0.0.1`. NFR-02 Reliability: operations are idempotent; retries cannot duplicate records/drafts. NFR-03 Performance targets: dashboard under 2s for 1,000 local records; record view under 2s excluding Graph/LLM; visible progress/cancel for external calls. NFR-04 Accessibility: WCAG 2.2 AA-oriented keyboard, focus, contrast, labels. NFR-05 Maintainability: strict layered separation between UI, application services, domain rules, persistence, Graph, and Ollama. NFR-06 Observability: structured local logs without bodies, tokens, or attachments. NFR-07 Recoverability: manager-triggered encrypted backup/restore procedure and rollback per milestone. NFR-08 Compatibility: supported current macOS and documented Ollama/Graph dependencies.

## Prohibited behavior

Job-ID-only or EP-only matching, test-only authentication/security bypasses, display-state writes over domain state, direct production edits, multiple authoritative repositories, mixed integration/domain/UI responsibilities, external bind, automatic drafts/closures/deletions, and mail sending.

## Scheduled-review requirements — 2026-08-08

- FR-023 Run at 08:00 America/New_York and once after a missed run.
- FR-024 Prevent overlap and persist a redacted result.
- FR-025 Use immutable source and exact or manager-confirmed linked conversation identity.
- FR-026 Preserve manager notes, decisions, closures, and overrides.
- FR-027 Never call draft creation or sending from the scheduler.

## UI non-functional requirements — 2026-08-09

- NFR-UI-01 The local UI shall use bundled/local assets and resilient local font fallbacks; a network font/CDN shall not be required to render it.
- NFR-UI-02 Dashboard, work queue, interviews, retention, record workspace, and action dialogs shall remain usable at desktop and responsive widths without horizontal overflow.
- NFR-UI-03 Non-essential motion shall honor `prefers-reduced-motion`.
- NFR-UI-04 Visual status, evidence, and actions shall remain intelligible without relying on color alone.
- NFR-UI-05 A visual-only release shall not invoke Graph, mutate the database, create a draft, or send email.
