# Recruitment Follow-Up Agent

Status: Local production release candidate — approved 2026-08-08  
Product owner: Tarun / Clifyx  
Initial mailbox: `tarun@clifyx.com`  
Deployment: Local-only macOS, bound to `127.0.0.1`  
Time zone: `America/New_York`

## Purpose

This is the authoritative implementation and documentation for the local recruitment follow-up app. It performs an approved mailbox review daily at 8:00 AM America/New_York, updates deterministic local workflow states, and supports manager-approved Outlook drafts. It cannot send email.

## Document authority

When documents conflict, use this order: approved ADRs; approved SRS/PRD; approved API/data/security specifications; other plans. A change to a confirmed requirement requires explicit owner approval and corresponding updates to requirements, tests, risks, and milestones.

## Document map

1. [BRD](01-BRD.md)
2. [SOW](02-SOW.md)
3. [PRD](03-PRD.md)
4. [SRS](04-SRS.md)
5. [TRD](05-TRD.md)
6. [Architecture](06-ARCHITECTURE.md)
7. [Data model and dictionary](07-DATA-MODEL.md)
8. [API contract](08-API-CONTRACT.md)
9. [UI/UX specification](09-UI-UX.md)
10. [Security and threat model](10-SECURITY-THREAT-MODEL.md)
11. [Microsoft Graph integration](11-GRAPH-INTEGRATION.md)
12. [LLM and prompt specification](12-LLM-PROMPTS.md)
13. [Retention policy](13-RETENTION-POLICY.md)
14. [Migration/import plan](14-MIGRATION-IMPORT.md)
15. [Test strategy](15-TEST-STRATEGY.md)
16. [Acceptance criteria](16-ACCEPTANCE-CRITERIA.md)
17. [Operations runbook](17-OPERATIONS-RUNBOOK.md)
18. [Release plan](18-RELEASE-PLAN.md)
19. [Architecture decision records](19-ADRS.md)
20. [Risk register](20-RISK-REGISTER.md)
21. [RACI](21-RACI.md)
22. [Source-code standards](22-SOURCE-CODE-STANDARDS.md)
23. [Milestone tracker](23-MILESTONE-TRACKER.md)
24. [Open decisions](24-OPEN-DECISIONS.md)
25. [Production readiness and lessons learned](25-PRODUCTION-READINESS-AND-LESSONS.md)

## Core invariants

- The application never sends mail and never requests `Mail.Send`.
- The approved 8:00 AM America/New_York mailbox review may import and update deterministic local statuses. Follow-up decisions, drafts, closure, deletion, and sending remain manager-controlled; automatic drafts and email sending are prohibited.
- Reply association uses immutable source-message identity plus exact Outlook conversation identity, never Job ID.
- Deterministic rules decide eligibility and actions; the LLM only classifies, summarizes, and suggests text.
- Uncertainty remains in Needs Review and can never silently close a record.
- Full content and attachments are encrypted and retained for 3 months; afterward only the defined basic operational record remains.
- No production change occurs without explicit approval; the 8:00 AM unattended review was explicitly approved on 2026-08-08.

## Production baseline — 2026-08-08

- Loopback-only FastAPI and React app on `127.0.0.1` with encrypted SQLite and macOS Keychain.
- Existing Microsoft Graph consent only; `Mail.Send` is absent and prohibited.
- Daily review at 8:00 AM ET plus one missed-run catch-up; no automatic drafts, closure, deletion, or sending.
- **Review mailbox now** is the manual equivalent of the daily review: it imports new eligible Submissions messages, re-reads every stored primary and manager-linked interview conversation by exact Graph `conversationId`, recalculates deterministic statuses/timers, and reloads the dashboard/open record. It never creates a draft or sends email.
- Manager-approved Reply All drafts preserve Outlook history and are sent manually in Outlook.
- See `25-PRODUCTION-READINESS-AND-LESSONS.md`.

## Visual-system release and handoff — 2026-08-09

The released local UI now uses the approved calm, cinematic workspace visual system: Today, Work Queue, Interviews, and Retention & Operations; a focused dashboard decision card; conversation path; and clear manager actions. The update is presentation-only: it makes no Graph, database, draft, or send action by itself, retains local assets/font fallbacks, and honors reduced-motion preferences.

See `PROJECT-HANDOFF.md` for the current operating state and `09-UI-UX.md` for the visual specification. The connected Figma file is documented there; its final connector save is pending only because the Figma Starter-plan tool quota is currently exhausted.
