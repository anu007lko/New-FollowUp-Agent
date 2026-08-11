# Mutation route ownership

This inventory is the ownership contract for the local manager UI. “Legacy” means
supported for compatibility, but not selected by the current canonical workflow UI.
No route is removed by this document.

| Route | Classification | Replacement / frontend owner |
|---|---|---|
| `POST /api/v1/records/{id}/action` | canonical UI workflow route | Current action bars and manager modals; authority for supported record mutations |
| `POST /api/v1/records/{id}/follow-up-decision` | specialized supported route | Follow-up modal; remains separate because it records the draft workflow decision |
| `POST /api/v1/records/{id}/draft-approve` | specialized supported route | Follow-up modal draft wizard |
| `POST /api/v1/records/{id}/draft-create` | specialized supported route | Follow-up modal draft wizard |
| `POST /api/v1/records/{id}/draft-reconcile` | specialized supported route | Follow-up recovery controls |
| `POST /api/v1/records/{id}/draft-resume` | specialized supported route | Follow-up recovery controls |
| `POST /api/v1/records/{id}/draft-reset` | specialized supported route | Follow-up recovery controls |
| `POST /api/v1/records/{id}/interview-confirmation` | specialized supported route | Interview modal |
| `POST /api/v1/records/{id}/link-interview` | specialized supported route | Record workspace interview-link controls |
| `POST /api/v1/records/{id}/unlink-interview` | specialized supported route | Record workspace interview-link controls |
| `POST /api/v1/records/{id}/refresh` | specialized supported route | Record workspace Refresh Thread control |
| `POST /api/v1/imports/submissions` | specialized supported route | Top-bar mailbox review |
| `POST /api/v1/imports/submissions/preview` | specialized supported route | Import preparation tooling; no current mutation owner |
| `POST /api/v1/records/{id}/analyze` | specialized supported route | Advisory tooling; no canonical workflow owner |
| `POST /api/v1/records/{id}/advisory-decision` | specialized supported route | Advisory tooling; no canonical workflow owner |
| `POST /api/v1/records/{id}/suggest-reply` | specialized supported route | Advisory tooling; no canonical workflow owner |
| `POST /api/v1/records/{id}/notes` | legacy/deprecated route | Use `action` with `ADD_NOTE`; no current frontend owner |
| `POST /api/v1/records/{id}/outcome-decision` | legacy/deprecated route | Use `action` with `REVIEW_OUTCOME`; no current frontend owner |
| `POST /api/v1/records/{id}/close` | legacy/deprecated route | Use `action` with `CLOSE_RECORD`; no current frontend owner |
| `POST /api/v1/records/{id}/reopen` | legacy/deprecated route | Use `action` with `REOPEN_RECORD`; no current frontend owner |
| `POST /api/v1/records/{id}/interview-schedule` | legacy/deprecated route | Use the supported interview modal/confirmation flow; no current frontend owner |
| `POST /api/v1/retention/delete-approved` | internal/admin-only route | Retention review tooling; no current frontend owner |
| `POST /api/v1/backup/create` | internal/admin-only route | Local operations tooling; no current frontend owner |
| `POST /api/v1/backup/restore` | internal/admin-only route | Local operations tooling; no current frontend owner |
| `POST /api/v1/synthetic/reset` | internal/admin-only route | Test-only synthetic tooling; disabled in release mode |
| `POST /api/v1/daily-review/run` | internal/admin-only route | Top-bar mailbox review uses the route only as an explicit local manager operation |

The direct legacy record routes remain available for compatibility and must retain
their existing validation and optimistic concurrency behavior until a later removal
phase explicitly authorizes their deletion.
