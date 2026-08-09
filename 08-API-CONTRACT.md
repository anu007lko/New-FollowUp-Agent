# Local API Contract

## General contract

Base URL is loopback-only; versioned prefix `/api/v1`. JSON only except controlled attachment download. Every mutating request requires local authentication, same-origin/CSRF protection, an idempotency key, and audit correlation ID. Errors use `{code, message, correlationId, fieldErrors}` and never expose tokens, bodies, paths, or stack traces.

## Resource endpoints

| Method/path | Purpose | Side effects |
|---|---|---|
| `GET /health` | minimal liveness | none; no sensitive detail |
| `GET /config/status` | redacted readiness/permission status | none |
| `POST /imports/submissions` | manager-triggered import | Graph read and local upsert |
| `GET /imports/{id}` | progress/result/exclusions | none |
| `GET /records` | filtered dashboard | none |
| `GET /records/{id}` | record, projection, evidence | none |
| `POST /records/{id}/review` | retrieve/reconcile exact conversation | Graph read, local analysis |
| `POST /records/{id}/decisions/follow-up` | record manager request | workflow event only |
| `POST /records/{id}/decisions/close` | close with reason/note | workflow event only |
| `POST /records/{id}/draft-suggestions` | local suggested text | Ollama inference only |
| `POST /records/{id}/draft-approvals` | approve content/recipients hash | local audit only |
| `POST /records/{id}/outlook-drafts` | explicit confirmed draft creation | Graph creates draft, never sends |
| `GET /records/{id}/audit` | record history | none |
| `POST /maintenance/retention/preview` | preview eligible reductions | none |
| `POST /maintenance/retention/apply` | explicitly run approved reduction | deletes expired full content |
| `POST /maintenance/backup/export` | manager-triggered encrypted export | produces encrypted backup file |
| `POST /maintenance/backup/restore` | restore encrypted backup | restores DB and runs immediate retention sweep |

## Prohibited routes

There is no send, auto-scan, scheduler, bulk follow-up, permission-consent, or login-trigger route. No endpoint accepts Job ID as a message/conversation association key.

## Command preconditions

Review requires eligible/reviewable record and exact stored identities. Close requires allowed reason; Other requires nonblank note. Draft suggestion requires Request Follow-up. Approval requires content and recipient preview (BCC starts empty, editable for `@clifyx.com` addresses only). Draft creation requires unexpired matching approval hash plus a new explicit confirmation. Recipient changes invalidate prior approval. Restore execution immediately triggers retention sweep before content becomes accessible.


## Concurrency and responses

Records expose a version/ETag; stale mutations return conflict. Accepted long operations return an operation resource. Repeated idempotency keys return the original outcome. Draft timeout triggers reconciliation, not blind retry.

## Production notes — 2026-08-08

Every POST requires a server-issued CSRF token. Manager identity is injected server-side. Daily-review status exposes running state, last result, and next 08:00 ET run. Draft APIs support preview, approve, create, and reconcile only. No send endpoint exists.

`POST /api/v1/daily-review/run` is the manual real-time mailbox review endpoint. It imports eligible messages and refreshes primary plus confirmed linked conversations using exact `conversationId` values before deterministic classification. Its response includes `status`, `submissions_imported`, `conversations_reviewed`, `conversations_updated`, and `conversation_refresh_errors`. `already_running` is non-destructive. This endpoint has no draft or send behavior.

## Documentation refresh — 2026-08-09

The visual-system release adds no endpoint, changes no request/response contract, and performs no API call merely to render a screen.
