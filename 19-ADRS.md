# Architecture Decision Records (ADRs)

Status terms: Proposed, Accepted, Superseded. Confirmed requirements below are recorded as Accepted; unresolved implementation choices remain Proposed.

## ADR-001 — Local-only loopback deployment (Accepted)

Use a macOS-local app bound to `127.0.0.1`. Consequence: reduced remote attack surface; device security and local request protection remain essential.

## ADR-002 — Manager-triggered operations only (Superseded)

Superseded by ADR-010. Drafts, closure, deletion, and sends remain manager-controlled.

## ADR-003 — Immutable message plus exact conversation identity (Accepted)

Associate through Graph immutable source message identity and exact conversation identity. Job ID is display-only. Consequence: imports without required identity are quarantined.

## ADR-004 — Deterministic authority, advisory local LLM (Accepted)

Rules govern eligibility/actions; Ollama classifies/summarizes/suggests. Consequence: model failures degrade safely to Needs Review.

## ADR-005 — Draft-only Graph write (Accepted)

Create an approved Reply All draft; app cannot send and excludes `Mail.Send`. Consequence: manager completes send in Outlook.

## ADR-006 — Encrypted full content with three-month reduction (Accepted)

Content/attachments are encrypted then reduced to operational metadata after 3 calendar months from the newest message in the exact Outlook conversation thread. Consequence: automated retention worker reduces expired items without altering Outlook.

## ADR-007 — Layered responsibilities and authoritative domain state (Accepted)

Separate UI, application, domain, adapters, and persistence; projections cannot overwrite state. Consequence: more explicit mappings, safer change isolation.

## ADR-008 — One authoritative repository and controlled releases (Accepted)

Clean commit/change boundaries, no direct production edits, no test-only security bypass. Repository initialization waits for explicit implementation approval.

## ADR-009 — Local technology stack selection (Accepted)

Use Python 3.11+ with FastAPI for local application/domain API; React with TypeScript and Vite for local UI; SQLite with SQLCipher (or reviewed encrypted SQLite design) for encrypted persistence; macOS Keychain for protecting encryption master keys; bound strictly to `127.0.0.1`. Consequence: unified, maintainable, cross-layer typed contracts running entirely locally on macOS.

## ADR-010 — Daily deterministic mailbox review (Accepted 2026-08-08)

Run at 08:00 America/New_York and once after a missed run. It may import, reconcile exact conversations, and update deterministic status. It cannot draft, close, delete, or send.

## ADR-011 — No email-send capability (Accepted)

`Mail.Send`, send routes, and send adapter methods are prohibited. Graph may create manager-approved Reply All drafts; only Outlook sends.

## ADR-012 — Local cinematic visual system (Accepted 2026-08-09)

Adopt the approved spacious dark aurora-room visual system for the local React UI. The decision applies only to presentation: local assets/fallback fonts, responsive layout, reduced-motion behavior, clear focus states, and a focused decision-first dashboard. It shall not add a remote rendering dependency or alter API, Graph, deterministic workflow, persistence, draft, or send boundaries.
