# Statement of Work (SOW)

## Deliverable

A local-only macOS recruitment follow-up application delivered through gated milestones and operated under the approved production controls.

## Work packages

1. Governance and requirements baseline (Documentation Baseline & Requirements Approval).
2. Local application shell and security foundation (Python 3.11+ FastAPI backend bound to `127.0.0.1`, macOS Keychain integration, local auth, CSRF defense).
3. Read-only Graph discovery/import and identity handling (folder-only import, TCS recipient filter, immutable Graph message IDs & `conversationId`).
4. Conversation review, deterministic workflow, and encrypted persistence (React+TS+Vite UI, SQLCipher/encrypted SQLite store, 48h NY timer, interview state transitions, category rules).
5. Local LLM advisory features (Ollama `llama3.2:latest`, schema-constrained JSON classification, summary/suggestion generator, Needs Review fallback).
6. Explicitly approved Reply All draft creation (empty default BCC, `@clifyx.com` BCC restriction, two-step manager approval, Graph draft creation).
7. Retention, encrypted local backup/restore, audit, operations, and release readiness.


## Required deliverables

Approved specifications; traceability matrix; threat model; tested local application; test evidence; operator runbook; rollback package; release approval record. Source code, configuration, and test assets must ultimately live in one authoritative repository, created only after explicit implementation authorization.

## Exclusions

No app-based sending, `Mail.Send`, fresh consent/login without instruction, cloud hosting, scheduled work, production edits, direct migration from the old app, or reuse of old app code/data absent an independently approved sanitized import.

## Change control

Any scope, permission, retention, identity, matching, automation, or sending change requires written owner approval, impact analysis, updated ADR/risk/tests, and a new baseline version.

## Completion

Completion requires all acceptance criteria to pass, no open critical/high security defects, rollback rehearsal, retention verification, Graph scope verification, and product-owner release approval. Each milestone independently requires acceptance criteria, tests, rollback instructions, and the no-production-change-without-approval gate.

## Delivered scope — 2026-08-08

The implementation, encrypted migration, exact-conversation import, deterministic workflow, manager actions, Reply All draft workflow, retention/backup controls, production UI, and 8:00 AM daily review are delivered. Email sending and automatic draft creation are excluded by design.

## Documentation refresh — 2026-08-09

The approved frontend visual-system release is delivered as presentation-only scope. It preserves every SOW boundary, including explicit manager approval for drafts and the permanent exclusion of email sending. See `PROJECT-HANDOFF.md` for current evidence and remaining external follow-up.
