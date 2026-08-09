# Data Model and Data Dictionary

## Entity relationships

## Entity relationships

`Manager` performs `AuditEvent`; `SubmissionRecord` originates from one `SourceMessageIdentity`, belongs to one `OutlookConversation`, has many `MessageSnapshot`, `Attachment`, `Classification`, `StatusEvent`, `ManagerDecision`, and optional `DraftOperation` records. `RetentionEvent` records content reduction; `BackupEvent` records encrypted local backup and restore events.

## Core entities

| Entity/field | Type/constraint | Meaning |
|---|---|---|
| SubmissionRecord.id | local immutable UUID | internal identity |
| sourceMessage.graphImmutableId | required unique string | immutable source message key |
| sourceMessage.internetMessageId | optional indexed string | corroborating RFC identity; not sole key |
| conversation.graphConversationId | required indexed string | exact Outlook thread identity |
| jobId | optional string | subject-derived display/search only; prohibited for association |
| epReference | optional string | candidate ownership reference, normally valid three months; prohibited for message association |
| tcsEligibility | eligible/ineligible/review | deterministic outcome and evidence |
| domainStatus | enum | authoritative workflow status (`NewSubmission`, `InEvaluation`, `ManagerActionRequired`, `PendingFollowUp`, `ClientRejected`, `PositionClosed`, `NeedsReview`, `Closed`) |
| displayProjection | derived, not persisted as authority | UI label/badges |
| latestMeaningfulAt | zoned instant nullable | rule-selected response anchor |
| followUpDueAt | instant nullable | calculated DST-safe threshold (paused during `ManagerActionRequired`) |
| interviewScheduledAt | instant nullable | parsed/confirmed scheduled time |
| interviewOutcome | pending/completed/rescheduled/cancelled/not-confirmed | manager confirmation after scheduled time (Completed starts feedback timer; Rescheduled requires new time; Cancelled/Not-Confirmed move to NeedsReview) |
| interviewOutcomeConfirmedAt | instant nullable | timer starts here only when outcome is completed |
| managerId | foreign key | action attribution |
| createdAt/updatedAt | instant | system timestamps |

## MessageSnapshot

Graph immutable ID (unique), conversation ID, internetMessageId, parent folder ID observed, sent/received instant, sender, To/CC, BCC metadata only where legally/technically available and never auto-reused, subject, direction, body format/content ciphertext, header evidence ciphertext, content hash, Graph change token if available, imported/reviewed timestamps.

## Classification

Category enum (`InterviewRequestScheduled`, `PositionClosed`, `Rejection`, `InEvaluation`, `Acknowledgement`, `FeedbackRequestForInfo`, `DuplicateAlreadySubmitted`, `NoResponse`, `Unrelated`, `NeedsReview`); confidence; uncertainty flags; evidence message IDs; short rationale; source (`rule`, `llm`, `manager`); model and prompt versions; raw structured output ciphertext with retention; created time. Manager correction is additive and never overwrites provenance.

## Decisions and drafts

Close reason enum: Position closed, Candidate withdrawn, Client rejected, No follow-up needed, Other; Other note required. DraftOperation stores operation key, approved content hash, approved To/CC recipients, BCC list (starts empty; manager editable for `@clifyx.com` addresses only; external BCC prohibited; recipient modifications invalidate approval), confirmation time, Graph draft ID, result, and error metadata. It cannot represent “sent.”

## Basic operational record after reduction

Keep local record ID, immutable source ID, conversation ID, non-content mailbox/folder provenance, Job ID, EP reference and ownership-expiry metadata, TCS eligibility outcome, category/status history, manager decisions/reasons including Other notes, timing/interview fields, content/attachment counts and hashes, draft ID/result/recipient metadata as approved, audit/retention/backup events, and schema versions. Delete bodies, full headers, attachment bytes, LLM raw content, and content-bearing caches.

## Integrity rules

Unique source immutable ID; all reconciled messages must match conversation ID; status events append-only; domain status changes only through transition service; ciphertext fields cannot accept plaintext; attachment paths cannot escape managed storage; deletion is auditable; foreign keys enforced; restores must immediately enforce 3-calendar-month retention before content is accessible.

## Production baseline — 2026-08-08

The database contains 114 complete records and zero placeholders after the approved 2026-08-08 catch-up. `record_version` supplies optimistic concurrency. `draft_operations` persists approval, idempotency, Graph draft identity, and read-back verification. Physical copies reconcile by RFC `internetMessageId` inside an exact conversation. EP is metadata, never an association key.

## Documentation refresh — 2026-08-09

The visual-system release does not introduce, remove, query, or mutate any data-model field. It remains a presentation-layer change only.
