# RACI Matrix

Roles: PO = Product Owner/Manager; ENG = Engineering; QA = Test; SEC = Security/Privacy; ID = Microsoft 365 Identity Admin; OPS = Local Operations/Release. Named assignments remain to be confirmed.

| Activity | PO | ENG | QA | SEC | ID | OPS |
|---|---|---|---|---|---|---|
| Requirements/workflow approval | A/R | C | C | C | I | I |
| Architecture/data/API | A | R | C | C | C | C |
| TCS and meaningful-response rules | A/R | C | C | I | I | I |
| Graph registration/scope validation | A | C | C | C | R | I |
| Security/threat/retention approval | A | C | C | R | C | C |
| Implementation | A | R | C | C | C | C |
| Test strategy/evidence | A | C | R | C | C | C |
| Acceptance testing | A/R | C | R | C | I | C |
| Release/rollback | A | C | C | C | I | R |
| Production change approval | A/R | I | I | C | I | C |
| Incident response | A | C | C | R | C | R |

Accountable means final decision; Responsible performs work; Consulted provides input; Informed receives outcome. No person may silently combine approval and implementation where independent security/release review is required.

## Initial assignment — 2026-08-08

Tarun is Product Owner, manager, and local operator. Engineering owns implementation/evidence; Microsoft 365 administration owns registration/consent. Daily review is approved automation; every draft, closure, retention deletion, and exceptional link remains manager-accountable.

## Documentation refresh — 2026-08-09

The visual-system release does not change accountability. The manager remains accountable for mailbox review, draft approval, Outlook sending, closures, retention deletion, and exceptional conversation links.
