# Contributing to Recruitment Follow-Up Agent

Thank you for your interest in contributing to the **Recruitment Follow-Up Agent**! This project is an open-source, local-first recruitment workflow automation tool designed with rigorous safety boundaries, cryptographic data protection, and explicit human-in-the-loop controls.

We welcome contributions from developers, designers, technical writers, and recruiters. To preserve the reliability, security, and integrity of the application, please review these contribution guidelines before submitting changes.

---

## 1. Project Overview & Core Philosophy

The Recruitment Follow-Up Agent helps recruitment managers track candidate submissions, schedule interviews, and draft follow-up communications in Microsoft Outlook via Microsoft Graph API.

Our core engineering and product invariants must be preserved by all contributions:
1. **Never Automatically Send Email**: The application must never automatically send email and must never request or use the Microsoft Graph `Mail.Send` permission. All follow-ups remain draft-only and require explicit manager review and approval.
2. **Deterministic State Machine Precedence**: Core workflow states, timers (e.g. 48-hour feedback deadlines), and eligibility transitions are governed by deterministic business logic. AI and LLMs operate strictly in an advisory capacity (summaries, message analysis, suggested draft text).
3. **Exact Identity Association**: Email threads and replies are linked exclusively via immutable Microsoft Graph message and conversation IDs (`conversationId`, `graph_immutable_id`), never inferred from Job IDs, candidate names, or subject strings.
4. **Local-First & Cryptographic Privacy**: Candidate PII, email bodies, and attachments are encrypted locally (using AES-GCM and macOS Keychain) and bound to `127.0.0.1`.

---

## 2. Development Environment & Setup

### Prerequisites
- **Python 3.9+** (FastAPI, MSAL, SQLite, Pytest)
- **Node.js 18+** & **npm** (React 19, TypeScript, Vite, Vitest)
- **Git**

### Local Setup

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/anu007lko/New-FollowUp-Agent.git
   cd New-FollowUp-Agent
   ```

2. **Backend Setup**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Frontend Setup**:
   ```bash
   cd frontend
   npm install
   cd ..
   ```

4. **Running in Offline/Synthetic Mode (Default)**:
   The application runs out-of-the-box without live Microsoft Graph or Ollama credentials by utilizing synthetic test fixtures:
   ```bash
   # Terminal 1: Backend
   python3 backend/app/main.py

   # Terminal 2: Frontend
   cd frontend
   npm run dev
   ```
   Open your browser to `http://localhost:5173`.

---

## 3. Repository Structure

```
.
├── backend/
│   └── app/
│       ├── api/              # FastAPI routes, middleware, and CSRF protection
│       ├── application/      # Orchestration (DailyReviewEngine, ImportService, Retention)
│       ├── domain/           # Pure business logic (models, classifiers, parsers, timers)
│       └── infrastructure/   # Storage, MSAL auth, Graph client, Ollama client, Keychain
├── frontend/
│   ├── src/
│   │   ├── components/       # UI components (AppShell, ManagerActionBar, modals)
│   │   ├── views/            # Dashboard, Interviews, Records, Retention views
│   │   ├── hooks/            # Custom React hooks (useRecords)
│   │   └── utils/            # Client-side status and timeline utilities
├── tests/                    # Pytest backend test suite (unit, integration, safety)
├── 01-BRD.md ... 25-*.md     # Authoritative engineering specification documents
├── README.md                 # Public project overview and documentation map
├── SECURITY.md               # Vulnerability reporting and security architecture
├── CONTRIBUTING.md           # This document
└── LICENSE                   # MIT License
```

---

## 4. Testing Expectations

Every code change must be accompanied by appropriate automated tests. We maintain high test coverage across domain logic, security checks, and UI interactions.

### Running Backend Tests
```bash
pytest
```
Ensure all tests pass and no warnings introduce regressions in workflow contracts or safety isolation.

### Running Frontend Tests & Typecheck
```bash
cd frontend
npm test
npm run build
cd ..
```

---

## 5. Security-Sensitive Areas

Extra care and review are mandatory when touching the following areas:
- **Authentication & Microsoft Graph Integration** (`backend/app/infrastructure/msal_client.py`, `graph_client.py`):
  - Do NOT add `Mail.Send` permission.
  - MSAL token caching and silent authentication must remain non-secret and diagnostic-safe.
- **Keychain & Data Encryption** (`backend/app/infrastructure/keychain.py`, `persistence.py`):
  - Master key derivation and database payload encryption must remain AES-GCM compliant.
- **Draft Creation & Recipient Policy** (`backend/app/domain/workflow_policy_engine.py`, `backend/app/application/services.py`):
  - Draft BCC fields must start empty.
  - BCC recipients must strictly adhere to allowlisted internal domains (e.g. `@clifyx.com`).
  - Recipient changes must invalidate prior approval hashes.
- **Secrets and Privacy**:
  - NEVER commit API keys, access tokens, client secrets, passwords, real candidate data, or employee mailbox dumps.

---

## 6. AI-Assisted Development Guidance

AI coding agents, LLMs, and automated tools (including **OpenAI Codex**) may be used as development, refactoring, and maintenance aids. However:

- **Human Maintainer Authority**: Human maintainers hold sole ownership of architectural decisions, release approvals, and security reviews.
- **Tests Are Authoritative**: AI-generated code must pass the complete test suite and adhere to all domain contracts.
- **No Autonomous Production Decisions**: AI agents cannot make autonomous deployment or production decisions, nor can they bypass safety firewall rules.
- **No Unvetted Dependencies**: Do not introduce new third-party dependencies without clear justification and maintainer approval.

---

## 7. Pull Request (PR) Process

1. **Branch Naming**: Create a topic branch from `main` using descriptive names (e.g., `feat/interview-filter`, `fix/timer-boundary`, `docs/api-update`).
2. **Atomic Changes**: Keep PRs focused on a single issue or feature. Avoid large, unrelated refactorings.
3. **Commit Messages**: Write clear, descriptive commit messages following Conventional Commits (e.g., `feat:`, `fix:`, `docs:`, `test:`).
4. **Documentation**: Update relevant markdown specifications (in `01-BRD.md` through `25-PRODUCTION-READINESS-AND-LESSONS.md`) if requirements or behaviors change.
5. **Review & Approval**: All pull requests require review and approval from repository maintainers before merging.

---

## 8. Code of Conduct

We are committed to providing a welcoming, inclusive, and harassment-free environment for all contributors. Please treat everyone with respect, professionalism, and constructive collaboration.
