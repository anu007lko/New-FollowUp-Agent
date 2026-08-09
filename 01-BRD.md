# Business Requirements Document (BRD)

## Business problem

Recruitment submissions require consistent follow-up, but mailbox review is manual, fragmented across folders, and vulnerable to missed responses or incorrect matching. The product must give one manager a reliable, locally controlled review queue without sending mail or making autonomous decisions.

## Objectives and success measures

- Import only TCS-related submissions originating in Outlook folder `Submissions` for `tarun@clifyx.com`.
- Make every eligible record reviewable with complete conversation evidence.
- Surface records due after 48 calendar hours in `America/New_York`; the approved daily review may update deterministic local states but never creates drafts or sends mail.
- Preserve manager authority for Request Follow-up, Close, and draft approval.
- Achieve zero email sends by the app, zero Job-ID-based reply matching, and zero silent uncertain closures.
- Demonstrate 100% traceability from each displayed status to message evidence and deterministic rule outcome.

## Stakeholders

Product owner/manager; future managers; recruiting operations; Microsoft 365/identity administrator; security/privacy reviewer; developer/tester; support operator.

## Scope

In scope: manual import/review; TCS eligibility; exact conversation retrieval; encrypted local history and attachments; classification; timing/status evaluation; manager closure; suggested content; explicitly approved Outlook Reply All draft creation; audit trail; retention; future-manager-ready design.

Out of scope: non-TCS submissions; other source folders; public/cloud hosting; automatic/background activity; sending mail; CRM/ATS replacement; new Graph permissions or consent; branding finalization; automated candidate/client decisions.

## Business rules

BR-01 Source mailbox and folder are fixed initially. BR-02 TCS eligibility requires at least one original-submission To/CC recipient at `tcs.com`; end-client co-recipients are allowed but cannot substitute for a TCS recipient. BR-03 identity matching uses immutable Graph message identity and exact conversation identity, not Job ID or EP reference. BR-04 manager review retrieves the whole mailbox conversation across folders and shows the latest update/evidence, sender, timestamp, and timer effect. BR-05 category transitions: Acknowledgement sets In Evaluation and restarts the 48-calendar-hour timer from that message; Feedback or request for information sets Manager Action Required and pauses follow-up timing until marked handled; Rejection shows Client Rejected and prompts manager closure with reason Client rejected; Position closed shows Position Closed and prompts manager closure with reason Position closed; Duplicate/already submitted places in Needs Review and prompts closure or decision; Unrelated places in Needs Review and does not reset the follow-up timer; Uncertain or conflicting classifications remain in Needs Review. BR-06 48 calendar hours are evaluated in New York local time. BR-07 “we will update you” maps to In Evaluation and becomes Follow-up due after 48 hours without a newer meaningful response. BR-08 after a scheduled interview time passes, manager confirmation is required: Completed starts the 48-hour feedback timer; Rescheduled requires a new date and time; Cancelled and Not Confirmed move to Needs Review for immediate manager attention; no interview outcome auto-closes a record. BR-09 uncertainty maps to Needs Review and never auto-closes. BR-10 Close requires an allowed reason and Other requires a note. BR-11 drafting and draft creation are separately explicit manager choices. BR-12 drafts start with an empty BCC field; manager may add/remove `@clifyx.com` BCC recipients; external/historical BCC is never copied; recipient changes invalidate prior draft approval. BR-13 the manager sends only in Outlook. BR-14 M6 includes a manager-triggered encrypted local backup and tested restore protecting local decisions, notes, and audit history; restores immediately enforce retention before content access.

## Constraints and assumptions

Existing Graph registration/current consent remain authoritative. Local Ollama model is `llama3.2:latest`. Technology stack is Python 3.11+ with FastAPI backend, React with TypeScript and Vite frontend, SQLite with SQLCipher (or reviewed encrypted SQLite design), macOS Keychain secret protection, bound strictly to `127.0.0.1`. Three calendar months retention anchor is fixed to the newest message timestamp in the exact thread.

## Production decision — 2026-08-08

The Product Owner approved unattended mailbox review at 8:00 AM America/New_York and deterministic local status updates. Automatic drafts, automatic closure, retention deletion, and email sending remain prohibited. After the approved 2026-08-08 catch-up, the operational baseline contains 114 complete records and no placeholders.

## Documentation refresh — 2026-08-09

The approved visual-system release improves manager clarity without changing this business scope, ownership, decision rights, or the no-send policy. Current operating and handoff detail is maintained in `PROJECT-HANDOFF.md`.
