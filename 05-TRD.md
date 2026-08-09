# Technical Requirements Document (TRD)

## Technical boundaries

The implementation will comprise a local presentation layer (React with TypeScript and Vite), local application API (Python 3.11+ with FastAPI bound to `127.0.0.1`), domain/workflow engine, Graph adapter, Ollama adapter, encrypted persistence (SQLite with SQLCipher, or reviewed encrypted SQLite design), key/secrets adapter (macOS Keychain), and audit/retention/backup workers invoked only by explicit user or approved maintenance action. Dependencies point strictly inward toward the domain.

## Design requirements

- Domain state is authoritative; view/display projections are derived and cannot overwrite it.
- Graph DTOs, persistence models, and UI view models are separate.
- Conversation identity is a first-class value object; Job ID has no association methods.
- Commands are explicit, authenticated, CSRF-protected, auditable, and idempotent.
- Query paths are side-effect free except explicit cache refresh documented as such.
- Draft creation uses a unique operation key and persists Graph draft identity/result.
- Time is injected through a clock abstraction and evaluated with an IANA time zone (`America/New_York`).
- LLM output must validate against a strict schema; invalid output becomes Needs Review.
- Content encryption uses per-record or envelope keys; master key is protected by macOS Keychain.
- Draft creation starts with an empty BCC field; manager additions/removals are restricted strictly to `@clifyx.com`; recipient modifications invalidate prior draft approvals.
- Attachments are streamed with size/type limits and never executed or rendered unsafely.
- Manager-triggered encrypted local backup and tested restore in M6 protects local decisions, notes, operational records, and audit history. Restores immediately enforce 3-month retention before content access.


## Configuration classes

Non-secret: mailbox, source folder, time zone, threshold, model name, internal recipient domains/allowlist, size limits, retention schedule. Secret: OAuth token material and encryption keys. Runtime configuration is validated and shown read-only in diagnostics, with secrets redacted.

## Quality gates

Formatting, static analysis, unit/integration/security tests, dependency review, migration rehearsal, permission assertion, send-surface negative tests, loopback test, and documentation traceability must pass before release approval.

## Implemented runtime — 2026-08-08

FastAPI serves the built React UI on `127.0.0.1:8000`. Encrypted SQLite is authoritative and Keychain protects keys/MSAL cache. One in-process scheduler calculates 08:00 with IANA `America/New_York`, prevents overlap, and fails closed. Ollama is optional and disabled in production.

## Visual architecture — 2026-08-09

The React presentation layer owns the approved cinematic workspace treatment: a reusable rail/top-bar shell, dashboard focus card, conversation/later-today panels, work queue, record workspace, and status/action controls. It uses local CSS gradients, local imagery, local font fallbacks, responsive sizing, and reduced-motion rules. The visual layer consumes existing API data and remains isolated from Graph, persistence, scheduler, mail, and draft adapters.
