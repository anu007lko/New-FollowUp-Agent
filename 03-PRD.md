# Product Requirements Document (PRD)

## Users and jobs

The initial manager needs to import relevant submissions, understand the latest complete thread, decide whether follow-up is appropriate, optionally create a safe draft, or close with a reason. Future managers need separate identity, authorization, preferences, and audit attribution without redesigning core records.

## Primary journey

1. Manager starts a manual import or system runs approved daily review (8:00 AM America/New_York or catch-up).
2. System shows import results and exceptions; only deterministic TCS matches enter the working set.
3. Manager opens a record and triggers Review Conversation.
4. System retrieves the exact full conversation across the mailbox, stores permitted content securely, applies rules, and obtains advisory LLM output.
5. UI shows evidence, classification, summary, timer, and Needs Review when uncertain.
6. Manager chooses Request Follow-up or Close.
7. If follow-up is requested, system suggests a draft; manager edits/approves it and separately confirms Create Outlook Draft.
8. App creates a Reply All draft only; manager sends it manually in Outlook.

## Functional requirements

PR-01 Manual import and approved daily review engine (scheduled at 8:00 AM America/New_York, missed-run catch-up at startup/resume, Run Now option, overlap prevention lock, no automatic closure, draft creation, or sending). PR-02 Manual review & daily review conversation processing. PR-03 Complete cross-folder exact-conversation review. PR-04 Approved categories and deterministic handlers: Interview request/scheduled (Completed starts 48h feedback timer, Rescheduled requires new date/time, Cancelled/Not Confirmed move to Needs Review); In Evaluation (includes Acknowledgement which resets the 48h timer from that message); Manager Action Required (set by Feedback or request for info, pausing follow-up timing until marked handled); Client Rejected (set by Rejection, prompting manager closure); Position Closed (set by Position closed, prompting manager closure); Needs Review (receives Duplicate/already submitted, Unrelated without timer reset, and uncertain/conflicting classifications); No response; Unrelated. PR-05 Due logic uses meaningful newer response, sender, timestamp, evidence, and 48 calendar hours in NY time. PR-06 Manager-controlled closure with enumerated reason (Position closed, Candidate withdrawn, Client rejected, No follow-up needed, Other with note); zero auto-closures. PR-07 Explicit draft approval and creation. PR-08 Recipient and BCC policy enforcement: empty default BCC, manager may add/remove `@clifyx.com` BCC recipients, external/historical BCC never copied, recipient changes invalidate prior draft approval. PR-09 Explainable status history and append-only audit. PR-10 Encrypted content/attachment retention, reduction after 3 months, and manager-triggered encrypted local backup/restore.

PR-11 The manager-visible **Review mailbox now** action runs the same governed workflow immediately. It must use a server-issued CSRF token, prevent overlap, show progress/outcome, import new eligible submissions, refresh every stored primary and confirmed linked interview conversation by exact Graph identity across mailbox folders, then reload the dashboard and any open record. Metadata such as Job ID or EP reference must never be used to match replies.

## Experience requirements

Simple, immersive, professional, low-clutter; one clear primary action per state; evidence visible beside decisions; destructive/irreversible-looking actions require confirmation; no visual implication that a draft was sent.

## Non-goals

No autonomous agent behavior, generic inbox client, ATS, bulk campaign tool, or sending client.

## Production behavior — 2026-08-08

The 8:00 AM ET review may import eligible submissions, read exact conversations, and update deterministic local statuses. The manager still approves every closure and Outlook draft. Separate interview chains require candidate identity, Job ID/full unique submission subject, interview evidence, and manager confirmation; EP alone never links.

## Product metrics

Import precision; identity-link accuracy; false closure count; Needs Review resolution time; due-state accuracy; draft recipient-policy violations; retention execution success; manager task time. Metrics remain local and contain no message content unless explicitly designed and approved.

## Experience release — 2026-08-09

The product experience uses a calm, visually expressive local workspace that helps a non-technical manager concentrate on one decision at a time. The approved visual system preserves the existing operational hierarchy—Today, Work Queue, Interviews, and Retention & Operations—and never changes deterministic outcomes, reply-anchor rules, approval requirements, or the no-send boundary. Decorative animation is subtle and optional; usable clarity, accessibility, and speed take priority over visual novelty.
