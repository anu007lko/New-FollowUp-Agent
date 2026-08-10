# Production Readiness and Lessons Learned

Status: approved local production release  
Date: 2026-08-08  
Owner: Tarun / Clifyx

## Final operating contract

The app is local-only on `127.0.0.1`. It reviews the mailbox daily at 8:00 AM America/New_York and performs one catch-up after a missed run. It may import eligible submissions, reconcile immutable/exact conversations, and update deterministic local status. It never creates an automatic draft, closes automatically, deletes automatically, or sends email. Managers approve Reply All Outlook drafts and send manually in Outlook.

## What went well

- Immutable Graph identity and exact Outlook conversations became authoritative.
- Deterministic evidence, 48-hour ET timers, and Needs Review made decisions explainable.
- Encrypted storage, Keychain, durable draft idempotency/read-back, and quarantine restore protected local data.
- Dry runs, aggregate reports, checkpoints, and manager gates protected live migration.
- The UI converged on four plain-language work areas and one primary action per state.
- Automated tests cover timing, manager overrides, recipient policy, CSRF, recovery, no-send, and production-data isolation.

## What did not go well

- A fake draft adapter once reported success without creating an Outlook draft.
- Import initially skipped placeholders instead of refreshing them.
- Physical Outlook copies were counted as logical messages before RFC-ID reconciliation.
- Display and workflow state were temporarily mixed, especially interview states.
- Inconsistent record versions caused stale-token errors.
- An unbounded Ollama context consumed excessive memory.
- Some UI labels were technical or misleading, including “sync paused.”
- Generic draft creation did not preserve Outlook history until Reply All/read-back was implemented.

## Permanent lessons

1. External success requires read-back verification.
2. Fake adapters are test-only and fail closed in production.
3. Import refreshes by immutable identity and preserves manager state.
4. Job ID, EP, name, or subject alone cannot match replies; EP may span requirements.
5. Separate interview chains require strong evidence and manager confirmation; first follow-up stays on the submission chain.
6. Every mutation uses CSRF, server-bound identity, and optimistic versioning.
7. `Mail.Send`, send routes, and scheduler draft paths are prohibited.
8. Ollama is optional, disabled by default, bounded, and advisory.
9. Live changes require verified encrypted backup, isolated tests, exact scope, reconciliation, and rollback.
10. Production UI text must describe actual capability in plain language.

## Remaining non-blocking enhancements

Branding, multiple managers, packaged macOS launch UX, and optional local-model evaluation may come later. Automatic email sending is not pending work; it is an explicit non-goal.

## Release evidence after every change

Full backend tests; frontend tests/build; browser manager journeys; API/CSRF matrix; encrypted DB audit; quarantine restore; Graph identity/scope assertion; draft Reply All/read-back/idempotency checks when changed; scheduler timing/overlap/catch-up checks; static no-send scan; loopback and port-8765 verification; redacted report.

## Final verified release evidence — 2026-08-08

- Authoritative database: 114 complete records, zero incomplete records, `PRAGMA quick_check: ok`.
- Daily scheduler: active; next run 2026-08-09 at 8:00 AM America/New_York; overlap protection and missed-run catch-up verified.
- Manager decisions: seven historical decisions preserved. The sole state difference is the approved deterministic `Awaiting Feedback` to `Feedback Due` timer transition.
- Draft safety: no draft was created by unattended reviews; durable draft-operation count remained unchanged.
- Security: manual review without a valid CSRF token returns HTTP 403; loopback binding remains active.
- Microsoft Graph: silent authentication and mailbox identity verified; `Mail.Read` and `Mail.ReadWrite` present; `Mail.Send` absent; no new consent or login triggered.
- Automated verification: 347 backend tests passed, 49 frontend tests passed, and the production frontend build completed successfully.
- Final encrypted recovery checkpoint: `backup-65d36a18_2026-08-08_15-18-43.enc`, authenticated and restored to quarantine with all 114 records.
- Runtime: version 1.0.0; Graph review and manager-approved drafts enabled; Ollama and email sending disabled. The obsolete legacy service on port 8765 was retired on 2026-08-09.

## Visual-system release lessons — 2026-08-09

- What went well: treating the visual refresh as a frontend-only release preserved the deterministic workflow, immutable identity, persistence, Graph, draft, and no-send boundaries. Browser checks caught layout/runtime problems before handoff.
- What we learned: a reference design needs explicit responsive, reduced-motion, local-font, and no-overflow acceptance checks—not a subjective “looks right” sign-off alone. Remote font dependencies are unnecessary risk for a local-only app.
- What did not go well: the Figma Starter-plan connector reached its quota before an auditable final write-back. The design must not be represented as saved in Figma until that integration succeeds.
- Current evidence: backend suite 352/352 passed, frontend suite 50/50 passed, TypeScript/build passed, static no-send scan passed; the visual session performed zero Graph calls, database mutations, draft actions, or sends.

## Legacy retirement — 2026-08-09

The obsolete `outlook-followup-agent` local runtime, launch item, listener on port 8765, application-support data, logs, and verified old project/snapshot folders were permanently removed to reclaim space. The current Follow Up Agent and its `~/.recruitment_agent` encrypted operational store were explicitly preserved. The old private GitHub repository remains pending deletion only because the current GitHub authentication lacks the `delete_repo` permission.
