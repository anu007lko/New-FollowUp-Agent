# Security Policy

The **Recruitment Follow-Up Agent** is designed with security, privacy, and safety as first-order architectural invariants. This document outlines our security model, reporting guidelines, and defensive measures.

---

## 1. Supported Versions

Security updates and patches are applied to the latest release on the `main` branch.

| Version | Supported          | Notes                                     |
| ------- | ------------------ | ----------------------------------------- |
| v0.1.x  | :white_check_mark: | Active open-source development / release  |
| < v0.1  | :x:                | Pre-release / development milestones      |

---

## 2. Reporting a Vulnerability

If you discover a potential security vulnerability in this project, please follow responsible disclosure practices:

1. **Do NOT open a public GitHub issue** to report a security vulnerability.
2. **Report via GitHub Private Security Advisory**: Use the "Report a vulnerability" button under the **Security** tab of the GitHub repository.
3. If GitHub Private Advisories are unavailable, contact the project maintainer privately through their established GitHub profile channels.

### Information to Include in Your Report
- A clear description of the vulnerability and its potential impact.
- Step-by-step instructions or proof-of-concept to reproduce the issue safely.
- Affected components, files, or endpoints.
- Any suggested mitigations or patches.

### Maintainer Response Timeline
- **Initial Response & Acknowledgment**: Within 48 hours.
- **Triage & Status Assessment**: Within 5 business days.
- **Fix & Disclosure Coordination**: We will work with the reporter to validate the fix and coordinate a release before public disclosure.

---

## 3. Core Security & Safety Invariants

### A. Strict Prohibition of Automated Email Sending
- **Draft Only**: The application creates draft emails in Microsoft Outlook for human review. It is architecturally prohibited from sending emails automatically.
- **Scope Restriction**: The Microsoft Graph client only requests read and draft capabilities (`Mail.Read`, `Mail.ReadWrite`). The `Mail.Send` permission is **strictly forbidden** and enforced via code assertions (`MSALPermissionError` in `backend/app/infrastructure/msal_client.py`).

### B. Recipient Policy & BCC Allowlist
- **Empty Default BCC**: Every new draft begins with an empty BCC field.
- **Allowlist Restriction**: Manager-added BCC recipients are strictly restricted to internal corporate domains (e.g. `@clifyx.com`). External or historical BCC addresses from past threads are never copied.
- **Approval Invalidation**: Any modification to recipients (To, CC, BCC) or email body invalidates prior approval cryptographic hashes, requiring fresh manager re-approval before draft generation.

### C. Local-First & Network Isolation
- **Loopback Binding**: The FastAPI backend and web server are bound strictly to `127.0.0.1` (localhost). They are not exposed to external networks.
- **CSRF Defense**: All state-mutating endpoints require a valid `x-csrf-token` header, generated locally and validated on each request.
- **Zero Cloud Telemetry**: No telemetry, tracking, or candidate data is sent to external third-party servers.

### D. Credential & Secret Management
- **macOS Keychain Integration**: Master encryption keys are stored securely in the operating system's native credential store (macOS Keychain) via CLI/SecKeychain APIs.
- **Token Cache Protection**: Microsoft Authentication Library (MSAL) tokens are cached locally in protected binary caches without plaintext logging.
- **Diagnostic Logging**: System logs automatically redact sensitive fields (tokens, authorization headers, passwords, cookies, client secrets) using centralized regex filters in `backend/app/api/logging_config.py`.

### E. Data Privacy & Cryptographic Retention
- **Encrypted Persistence**: Candidate metadata, raw email bodies, and attachments are encrypted at rest using AES-GCM encryption in the local SQLite database.
- **3-Month Cryptographic Reduction**: Full email message bodies and attachments are retained for 3 months. After 3 months, raw content is cryptographically shredded, leaving only basic operational summary records.

### F. LLM / AI Security Boundaries
- **Advisory Only**: AI models (e.g. local Ollama / LLaMA) operate strictly in an advisory role. State transitions, timers, and eligibility decisions are enforced by deterministic code.
- **Prompt Isolation (Sandwiching)**: Inbound email text and attachments are treated as untrusted data. Prompt templates isolate untrusted inputs within boundary delimiters to protect against prompt injection attacks.
- **Local Model Execution**: AI inference runs locally without transmitting recruitment data to cloud-based LLM APIs.

---

## 4. Third-Party Dependencies & Audits

We periodically audit dependencies for known CVEs using automated security tools (`npm audit`, `pip-audit`, Dependabot). Contributors must ensure that any new or upgraded dependency is vetted and does not introduce security vulnerabilities or incompatible licenses.
