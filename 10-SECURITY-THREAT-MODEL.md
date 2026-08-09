# Security and Threat Model

## Assets and goals

Assets: OAuth tokens, encryption keys, mailbox content, attachments, recipient lists, identities, audit history, drafts, and manager decisions. Goals: confidentiality, exact identity integrity, manager-only action, no sends, least privilege, retention enforcement, and evidence-grade auditability.

## Threats and mitigations

| Threat | Mitigation/verification |
|---|---|
| LAN/public exposure | bind `127.0.0.1`; reject non-loopback host/origin; startup assertion and network test |
| Malicious webpage calls localhost | local auth, CSRF token, strict Origin/Host, SameSite cookies, CORS deny, CSP |
| Token/key theft | macOS Keychain, restrictive file permissions, memory/log redaction, no secrets in source/config |
| Data theft at rest | authenticated encryption, envelope keys, FileVault prerequisite, encrypted backups |
| Prompt injection in email | treat content as data, fixed prompt boundaries, no tool/action authority, schema validation |
| LLM hallucination | deterministic rules authoritative, evidence required, uncertainty to Needs Review |
| Wrong thread/record | immutable message ID + exact conversation ID assertions; Job ID prohibited |
| Recipient leakage | normalize/validate Reply All; empty default BCC; manager-editable BCC restricted strictly to `@clifyx.com`; external/historical BCC never copied; recipient changes invalidate prior draft approval; preview and reapproval |
| Unauthorized send | no `Mail.Send`, no send route/UI/code path; permission and negative tests |
| Duplicate drafts | idempotency key, operation reconciliation, audit |
| Attachment exploit | size limits, MIME/signature checks, safe names, no execution, sandboxed view |
| Retention failure | due index, preview/report, verified deletion, backup-expiry alignment, alerts |
| Backup data leak / resurrection | encrypted local backup in M6; restores immediately enforce 3-calendar-month retention sweep before content becomes accessible |
| Test bypass reaches release | no test-only security bypass; production-equivalent security tests |
| Local multi-user access | OS session assumptions documented; future app roles and per-user audit |

## Abuse cases

Forged local requests; externally originated BCC copied; poisoned email instructing model to close/send; Graph returns same subject/job under a different conversation; user double-clicks draft creation; clock/DST changes; attachment path traversal; restore resurrects expired content (mitigated by immediate mandatory post-restore retention sweep); developer edits production directly.


## Security gates

Threat-model review; existing-scope inventory; dependency/license review; secret scan; loopback/CSRF/origin tests; encryption/key-loss exercise; Graph-send negative test; recipient-policy tests; prompt-injection corpus; retention/backup deletion test; rollback rehearsal. No critical/high issue is accepted without owner and security sign-off plus expiry.

## Verified controls — 2026-08-08

Loopback/Host/Origin checks, CSRF on mutations, server-bound identity, encryption/Keychain, immutable identity, optimistic versions, internal-only BCC, draft read-back, and fail-closed scopes are active. `Mail.Send` is absent; no send route/method exists. Tests cannot use the production DB or live Ollama.

## Documentation refresh — 2026-08-09

The visual-system release uses local assets and font fallbacks so it does not introduce a remote rendering dependency. Its verification pass made no Graph call, database mutation, draft action, or send action.
