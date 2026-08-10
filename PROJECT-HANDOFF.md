# Project Handoff — Recruitment Follow-Up Agent

**Last updated:** 2026-08-09  
**Operating state:** Local production-ready application on the manager's Mac  
**Scope boundary:** Outlook drafts may be created only after explicit manager approval; the application never sends email.

## Purpose

This is the authoritative handoff for the current local Recruitment Follow-Up Agent. It records the released operating model, the visual-system release, its evidence, and the remaining external dependency.

## Product and safety boundary

- Runs locally and binds only to `127.0.0.1`.
- The authoritative store is encrypted local SQLite; keys and the MSAL cache are protected by macOS Keychain.
- Imports are restricted to eligible TCS submissions and preserve immutable source-message identity plus exact Outlook conversation identity.
- Daily mailbox review runs at 08:00 `America/New_York`; **Review mailbox now** is the equivalent manager-initiated action.
- The review may read/import/reconcile eligible messages and update deterministic local status. It cannot create a draft, close a record, delete retained content, or send email.
- Outlook draft creation is a separately approved manager action. It uses Reply All against the validated reply anchor, preserves valid To/CC, restricts BCC to `@clifyx.com`, performs read-back verification, and remains idempotent.
- `Mail.Send` is absent, disabled, and prohibited. Sending occurs manually in Outlook only.
- Ollama is optional, advisory only, disabled by default, bounded when explicitly enabled, and never controls eligibility or actions.

## Current user experience

The completed visual system is a calm, cinematic local-workspace design with the existing functionality preserved:

- Persistent navigation: Today, Work Queue, Interviews, Retention & Operations.
- A date/local-only/refresh top bar.
- A focused dashboard decision card, conversation path, and later-today queue.
- A responsive work queue, record workspace, status evidence, and manager-action wizard.
- Local background and local font fallbacks only; no external font/runtime dependency is required.
- Motion is decorative, subtle, and disabled for `prefers-reduced-motion`.

The implementation is in `frontend/src/`; the visual work is presentation-only and does not alter mailbox, Graph, database, classification, draft, or send behavior.

## Verification completed for the visual release

- Backend unit & integration suite: **352/352 passed**.
- Frontend unit suite: **50/50 passed**.
- TypeScript validation and production Vite build: **passed**.
- Static no-send scan: **passed** (`Mail.Send` strictly absent; no send route/button/adapter exists).
- Visual-release session: **zero Graph calls, database mutations, draft actions, or email sends**.


## Figma status

The target design is the connected file **Delegatlabs** (`Yb1ECfpSNIMLk53ASiKcKE`). The Figma Starter-plan connector reached its tool-call limit while attempting the final save, so no unverified Figma write is claimed here. When the connector quota resets or the plan is upgraded, save the released dashboard frame and its design tokens to that file, then mark this item complete.

## Release and recovery

- Keep production flags aligned with the Operations Runbook: Graph and drafts only when intentionally enabled; `MAIL_SEND_ENABLED=False` always.
- Before any production configuration or data change, create and authenticate an encrypted backup and use the prescribed test/release gate.
- Restore only through quarantine and with explicit approval.
- The obsolete legacy service on port 8765 was retired on 2026-08-09; the current app does not use that port.

## Remaining item

Two external-account actions remain pending:

- The final Figma write-back is pending because of the free-plan connector quota.
- The old private GitHub repository `anu007lko/outlook-followup-agent` could not be deleted because the active GitHub authentication lacks the `delete_repo` permission. Its verified local runtime, launch item, local databases, logs, old project/snapshot folders, three exclusively old Antigravity task histories, deployment templates, and listener on port 8765 were removed on 2026-08-09. The current Follow Up Agent and `~/.recruitment_agent` were preserved.

There is no unresolved functional product decision in this handoff.

## Primary references

- `README.md` — product entry point and operating boundary.
- `09-UI-UX.md` — visual and interaction specification.
- `15-TEST-STRATEGY.md` — automated and manual quality gates.
- `17-OPERATIONS-RUNBOOK.md` — launch, review, and recovery procedures.
- `18-RELEASE-PLAN.md` — release/rollback governance.
- `25-PRODUCTION-READINESS-AND-LESSONS.md` — production-readiness evidence and lessons.
