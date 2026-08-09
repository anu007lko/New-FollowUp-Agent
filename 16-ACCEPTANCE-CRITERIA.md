# Product Acceptance Criteria

## Scope and control

AC-01 App is reachable only through `127.0.0.1` and rejects LAN/cross-origin access. AC-02 Only the approved 8:00 AM ET review and deterministic local status updates occur unattended; drafts, closure, deletion, and sending do not. AC-03 Existing Graph registration/current consent are reused without new login/consent unless separately instructed. AC-04 Effective permissions exclude `Mail.Send`; no app/API send capability exists.

## Import and identity

AC-05 Manual import reads only `tarun@clifyx.com` / `Submissions`, initially from July 10, 2026. AC-06 Only original messages having a `tcs.com` To/CC recipient enter scope; end-client co-recipients are allowed and lookalike subjects without TCS recipients are excluded. AC-07 Every record has immutable source message ID and exact Outlook conversation ID. AC-08 Tests prove Job ID and EP reference cannot associate replies. AC-09 Manager review retrieves and displays all accessible exact-conversation messages across folders, including the latest update/evidence, or clearly reports incompleteness.

## Workflow

AC-10 Approved categories, newer meaningful message evidence (sender, timestamp, evidence, timer effect) are displayed. AC-11 Category transition rules: Acknowledgement sets In Evaluation and restarts 48h timer; Feedback/Request for info sets Manager Action Required and pauses timing; Rejection shows Client Rejected prompting closure; Position closed shows Position Closed prompting closure; Duplicate/already submitted places in Needs Review prompting closure/decision; Unrelated places in Needs Review without timer reset; uncertain/conflict stays Needs Review; zero auto-closures. AC-12 48-hour New York calculations pass boundary and DST tests. AC-13 Eligible no-response records become Pending Follow-up only as derived by rules after 48 hours. AC-14 update-promising reply becomes In Evaluation and displays Follow-up due after 48 hours without newer meaningful response. AC-15 after a scheduled interview passes, manager confirms Completed/Rescheduled/Cancelled/Not confirmed: Completed starts 48h feedback timer; Rescheduled requires new date/time; Cancelled and Not Confirmed move to Needs Review for immediate manager attention; none auto-closes the record. AC-16 manager must choose Request Follow-up or Close; closure requires approved reason and Other note.

## Draft safety

AC-16A Suggestion requires manager request; Graph draft requires explicit content approval and separate confirmation. AC-17 Created item is a Reply All draft in the original conversation with valid To/CC. AC-18 drafts start with an empty BCC field; manager may add/remove `@clifyx.com` BCC recipients; external/historical BCC is never copied; recipient changes invalidate prior draft approval. AC-19 timeout/retry cannot create duplicate drafts. AC-20 UI clearly directs manual sending in Outlook and never reports a send.

## Data/security/quality

AC-21 full history and attachments are encrypted using SQLCipher/encrypted SQLite store and macOS Keychain secrets protection. AC-22 expiry reduction deletes content after 3 months and leaves only approved operational fields; manager-triggered encrypted local backup and tested restore in M6 protects local decisions, notes, operational records, and audit history; restores immediately enforce retention sweep before content access. AC-23 audit attributes actions and schema supports future managers. AC-24 accessibility, performance, recovery, logging/redaction, and threat-model gates pass. AC-25 approved tech stack (Python 3.11+ FastAPI, React TS Vite, SQLCipher/encrypted SQLite, Keychain, loopback `127.0.0.1`) strictly separates UI, application, domain, persistence, Graph, and Ollama; domain state is authoritative; clean changes; no direct production edits.


## Acceptance authority

Product owner signs business/workflow acceptance; security/identity reviewers sign their areas; test lead signs evidence. Production use requires explicit final approval even after all criteria pass.

## Final acceptance — 2026-08-08

The Product Owner approved daily review at 08:00 America/New_York with deterministic local updates and retained the prohibition on automatic drafts and sending. Final restart evidence must remain green.

AC-31 **Review mailbox now** performs an immediate full mailbox review, not merely a local page reload. AC-32 It refreshes all tracked exact primary and confirmed linked conversations across folders, updates changed records, and reports partial failures. AC-33 It requires CSRF, prevents overlap, refreshes visible data when finished, and makes zero draft/send calls.

## Visual-release acceptance — 2026-08-09

AC-34 The dashboard, navigation shell, focus card, conversation path, later-today queue, work queue, interviews, retention, record workspace, and action dialogs implement the approved visual system without obscuring workflow data or manager actions.

AC-35 The UI uses local assets/fallbacks, works at desktop and responsive widths without horizontal overflow, respects reduced-motion preferences, and exposes visible keyboard focus.

AC-36 The visual release passes frontend tests, TypeScript/build checks, browser runtime checks, and a zero-side-effect proof: no Graph, database, draft, or send action occurs solely from rendering or visual navigation.
