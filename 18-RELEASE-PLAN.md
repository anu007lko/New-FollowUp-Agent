# Release Plan

## Environments

Documentation baseline; developer environment with synthetic data; local acceptance environment; approved local production instance. Real mailbox access is introduced only at an approved gate. No cloud/public environment.

## Release gates

Requirements/ADRs approved; threat model and Graph scopes reviewed; tests and traceability pass; data migration/reconciliation rehearsed; backup/restore and retention verified; loopback/no-send assertions pass; rollback rehearsed; operator trained; unresolved decisions closed or explicitly deferred; product owner authorizes production change.

## Packaging and rollout

Produce a versioned, reproducible artifact (Python 3.11+ FastAPI application service + Vite-built React UI distribution) and checksums from the one authoritative repository. Back up current new-app data using the M6 encrypted backup utility, stop local service, apply artifact/config/migrations, run non-invasive readiness checks (loopback binding to `127.0.0.1`, Keychain access, Graph permissions check), then enable manager use. Do not touch the old app.


## Rollback

Trigger on identity mismatch, unexpected permission/login, send-capability finding, encryption/data integrity failure, duplicate drafts, critical workflow error, or acceptance regression. Stop new version, preserve redacted incident evidence, restore prior artifact/schema-compatible backup using tested procedure, verify retention and loopback controls, and require approval to resume.

## Versioning and communication

Use semantic application versions and explicit schema/prompt/rule versions. Release notes list user-visible changes, security/permission impact, migrations, known issues, validation, and rollback. No direct production hotfix; emergency change still requires owner approval, minimal reviewed change, tests, and retrospective.

## Release status — 2026-08-08

Approved local production release candidate. Sequence: verified encrypted backup, complete automated suite/build, restart with approved flags, monitor catch-up, API/UI/Graph/no-send checks, and handoff. Rollback restores the verified pre-release backup through quarantine only with explicit approval.

## Visual-system release — 2026-08-09

Released the approved frontend-only cinematic workspace treatment. Evidence: backend suite 352/352 passed, frontend suite 50/50 passed, TypeScript/build passed, static no-send scan passed, and desktop/responsive UI checks verified. The pass made no Graph call, database mutation, draft, or send action. Rollback is limited to restoring the prior verified frontend bundle. The corresponding Figma save is deferred until the connected Starter-plan quota permits a verified write.

