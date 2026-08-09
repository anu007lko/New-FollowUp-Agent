# Architecture Specification

## Context

The manager uses a browser-like local UI built with React, TypeScript, and Vite on the Mac. The app talks only to local encrypted storage (SQLCipher/encrypted SQLite), local Python 3.11+ FastAPI application service bound to `127.0.0.1`, local Ollama (`llama3.2:latest`), macOS Keychain key protection, and Microsoft Graph under the existing approved registration/consent. Outlook remains the only sending surface.

## Components

| Component | Technology / Responsibility | Must not do |
|---|---|---|
| UI | React + TypeScript + Vite: render projections, collect explicit intent | infer or mutate workflow state |
| Application service | Python 3.11+ FastAPI: authorize/orchestrate commands, bind to `127.0.0.1` | contain Graph-specific or prompt-specific business rules |
| Domain engine | Python 3.11 domain classes: eligibility, status, timing, transitions | call Graph, storage, UI, or LLM |
| Graph adapter | Graph SDK / HTTP client: folder/message/conversation/draft operations | decide eligibility or send mail |
| Ollama adapter | Ollama client: schema-constrained advisory inference | decide actions or transitions |
| Persistence | SQLite + SQLCipher (or reviewed encrypted SQLite): encrypted records, content, audit, migrations | encode display logic |
| Key adapter | macOS Keychain: master key generation, wrap/unwrap, protection | leak raw keys or bypass OS security |
| Policy engine | Recipient policy engine: BCC allowlist (`@clifyx.com`), empty default BCC, retention | accept unapproved runtime bypasses |

## Trust boundaries

Browser-to-loopback app (`127.0.0.1`); app-to-Graph; app-to-Ollama; app-to-Keychain; encrypted store/files; attachment parser/display. Each external response is untrusted input, including email bodies and LLM output.

## Key flows

Import is explicit command → locate configured folder → page messages → deterministic TCS evaluation → identity upsert → report. Review is explicit command → exact conversation query across mailbox → reconcile → encrypt content → deterministic analysis → advisory LLM → derived projection. Draft is request suggestion → manager edit/approve → recipient policy preview → explicit create confirmation → Graph draft only → record draft identity. Backup is explicit manager command → encrypt local decisions, notes, and audit history → produce backup artifact → restore immediately enforces retention sweep.

## Availability and failure

Graph/Ollama outages leave records intact and show retryable errors. Partial import uses checkpoints without silently declaring success. A failed draft call remains uncreated unless Graph reconciliation proves an operation-created draft exists. No fallback may send or broaden permissions.

## Deployment shape

Single-user local process (Python 3.11+ FastAPI backend), loopback listener (`127.0.0.1`), React+TS UI, encrypted local SQLite database, macOS Keychain secrets protection, and explicit startup/shutdown. Future manager support adds identities/roles without changing record ownership/audit semantics.

## Production flow — 2026-08-08

`Scheduler → import → Graph reads → immutable/exact-conversation reconciliation → deterministic classifier → optimistic encrypted persistence → UI`. Drafts use a separate manager path: `preview → approval hash → Reply All draft → read-back verification`. No scheduler-to-draft path and no send adapter exist.

## Presentation boundary — 2026-08-09

The approved visual system is a frontend-only layer over the same domain/API contracts. Its background assets, gradients, glass surfaces, typography scale, card treatments, and responsive layout do not cross the UI/API boundary. This separation prevents a visual adjustment from changing deterministic workflow, identity matching, persistence, or Outlook behavior.
