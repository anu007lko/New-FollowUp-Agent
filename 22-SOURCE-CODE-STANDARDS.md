# Source-Code and Engineering Standards

These standards apply to the implemented product and every future change.

## Repository and changes

Use one authoritative repository. Keep changes small, cohesive, and reviewable; one responsibility per commit/change set. Do not mix refactors, migrations, security changes, and features without necessity. Never edit production directly. Every change links requirements/tests and includes rollback/migration impact.

## Architecture

Strictly separate domain (Python 3.11 domain models), application (FastAPI handlers bound to `127.0.0.1`), UI (React + TypeScript + Vite), Graph adapter, LLM adapter (Ollama client), persistence (SQLCipher/encrypted SQLite), security (macOS Keychain), and operations responsibilities. Dependency direction points strictly inward toward the domain. Domain state is authoritative; display state is derived. Do not place business decisions in controllers, UI components, Graph queries, prompts, or database triggers.

## Correctness and safety

Use strict typing (Python type annotations, TypeScript strict mode) and validated Pydantic/Zod schemas; explicit enums/value objects for identities/statuses/reasons; immutable identifiers; UTC instants plus named time zone (`America/New_York`) at boundaries; idempotent commands; append-only audit. Job ID must not appear in association logic. No test-only authentication, encryption, authorization, recipient, consent, or send bypasses.


## Security/privacy

No secrets or personal message content in source, fixtures, logs, snapshots, or error telemetry. Parameterize queries, encode output, validate paths/MIME/size, pin/review dependencies, use safe cryptographic libraries, redact by default. Prohibit Graph send clients/methods and fail on disallowed scopes.

## Testing/review

Required: formatter/linter, type/static analysis, unit/contract/integration tests, security scans, coverage of changed risks, migration up/down or forward-recovery test, documentation updates. Reviews use checklists for identity, permissions, retention, state ownership, time, idempotency, logs, and rollback.

## Documentation

Public interfaces and non-obvious invariants need concise documentation. ADR required for material architecture/security/permission/retention change. Prompt/rule/schema versions are release artifacts.

## Permanent release rules — 2026-08-08

Fake Graph is test-only; tests cannot resolve the production DB or live Ollama; all mutations use CSRF/server-bound identity; import cannot reset workflow state; Graph writes require durable idempotency/read-back; every production change requires backup, tests, rollback, and approval.

## Frontend visual-system standards — 2026-08-09

Keep visual tokens, backgrounds, gradients, typography, responsive rules, and reduced-motion behavior in the frontend presentation layer. Use semantic component names and preserve the established shell/card hierarchy. Do not introduce a remote font/CDN dependency for a decorative effect. A visual-only change must not call an API merely to render and must retain the no-send boundary in all labels and flows.
