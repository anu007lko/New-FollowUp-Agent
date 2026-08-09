# Milestone Tracker

Global gate for every milestone: no production change without explicit Product Owner approval. Current status is local production release candidate.

| Milestone | Deliverable | Acceptance and tests | Rollback | Status |
|---|---|---|---|---|
| M0 Documentation baseline | all documents approved; open decisions resolved & assigned; tech stack selected | consistency/traceability review; confirmed requirements & PO decisions represented | revert documentation baseline only; no production exists | Accepted |
| M1 Security/local foundation | Python/FastAPI loopback, CSRF, Keychain, encrypted SQLite | bind/origin/CSRF/Keychain/redaction tests | restore approved backup | Accepted |
| M2 Graph read/import | manual and approved scheduled `Submissions` import, TCS filter, immutable/exact identity | scopes, pagination, eligibility, idempotency | restore encrypted checkpoint; never Outlook | Accepted |
| M3 Conversation/workflow | production UI, exact threads, 48h ET, categories/interviews | identity, transition, DST, Needs Review tests | restore prior schema/store | Accepted |
| M4 LLM advisory | guarded optional Ollama; deterministic workflow authoritative | schema, memory, injection/fallback tests | disabled by default | Accepted |
| M5 Draft-only integration | approved Reply All, internal BCC, two-step approval, reconciliation | recipient/thread/read-back/crash/no-send tests | disable drafts; reconcile test draft | Accepted |

| M6 Retention/backup and operations | expiry list, manager-approved local deletion, encrypted backup/restore, operations runbook | calendar/encryption/deletion/restore, post-restore retention enforcement | authenticated restore of a policy-compliant backup | Accepted |
| M7 Local production release | mature FastAPI/Vite UI, approved scheduler, security/browser/Graph evidence | 347 backend tests, 49 frontend tests, clean build, loopback and CSRF checks, encrypted recovery rehearsal | stop local service and restore verified pre-release backup | Accepted — production-ready 2026-08-08 |
| M8 Visual-system release | approved cinematic local workspace, responsive/a11y polish, UI verification | 352 backend tests, 50 frontend tests, TypeScript/build pass, static no-send scan pass | restore prior verified frontend bundle; no data recovery required | Accepted — 2026-08-09; Figma write-back pending connector quota |



## Milestone record template

Each milestone record must list owner, dates, exact scope, requirement IDs, acceptance evidence, test results, defects/risks, data/schema changes, permission impact, rollback rehearsal result, approvers, and explicit go/no-go decision. Passing tests alone does not authorize production change.
