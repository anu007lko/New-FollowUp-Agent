# Risk Register

Scale: probability (P) and impact (I), Low/Medium/High. Owner roles are provisional.

| ID | Risk | P/I | Mitigation and trigger | Owner |
|---|---|---|---|---|
| R-01 | Wrong conversation linked | M/H | immutable IDs, exact conversation assertions, adversarial tests; stop on mismatch | Engineering |
| R-02 | App accidentally sends mail | L/H | no scope/route/method, runtime permission fail-closed, negative tests | Security |
| R-03 | New consent/login unexpectedly requested | M/H | readiness-only scope inventory; stop and ask owner | Identity admin |
| R-04 | External BCC/privacy leak | L/H | empty default BCC; manager additions restricted to `@clifyx.com`; external BCC prohibited; recipient modifications invalidate approval | Product/Security |
| R-05 | LLM misclassifies or follows prompt injection | M/H | advisory only, schema/evidence, uncertainty gate, attack corpus | Engineering |
| R-06 | 48-hour/DST calculation wrong | M/M | injected clock, IANA zone, boundary suite | QA |
| R-07 | Retention leaves derived/backed-up content | L/H | data inventory, verified reduction, post-restore retention sweep, backup test | Security/Ops |
| R-08 | Encryption key loss | L/H | Keychain design, recovery decision, backup rehearsal | Ops |
| R-09 | Duplicate Outlook drafts | M/M | idempotency and reconciliation | Engineering |
| R-10 | Incomplete Graph conversation | M/H | pagination, partial flag, block confident conclusion | Engineering |
| R-11 | Localhost attacked by malicious site/user | M/H | auth, CSRF/origin/host checks, OS controls | Security |
| R-12 | Attachment exploit/disk exhaustion | M/H | type/size limits, sandbox, quotas | Security/Ops |
| R-13 | Old app contaminates rebuild | L/H | no reuse/access; mailbox-only initial source | Product |
| R-14 | Mixed responsibilities/display overwrite regress | M/M | architecture boundaries, tests, review checklist | Engineering |
| R-15 | Single-user assumptions block future managers | M/M | manager entity, attribution, authorization seams | Architecture |
| R-16 | Undefined TCS/meaningful-response rules cause inconsistency | L/H | Resolved by PO decision: category transition rules and interview state machine fully specified | Product |
| R-17 | Local model quality insufficient | M/M | benchmark, Needs Review, approved model-change ADR | Product/QA |
| R-18 | Direct production edit/untracked change | M/H | repository-only release, checksums, approvals | Release owner |


Risks are reviewed at every milestone. High residual risks require explicit owner/security acceptance with expiry; critical risks block release.

## Production review — 2026-08-08

R-01/R-02 are controlled through immutable/exact identity, manager confirmation for separate interview chains, Reply All read-back, and no send capability. Added R-19 missed/duplicate scheduler run (L/H): persisted last run, lock, single catch-up, idempotent import. Added R-20 manager choice overwritten (L/H): manager-override precedence and regression tests.

## Visual-release review — 2026-08-09

Added R-21 visual regression/accessibility degradation (M/M): local asset/font fallbacks, responsive and reduced-motion requirements, screenshot/browser checks, and frontend rollback. Added R-22 Figma connector quota preventing verified write-back (L/L): record the design reference and defer the save; do not claim an unsaved Figma update as completed.
