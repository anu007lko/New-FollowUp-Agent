# Recruitment Follow-Up Agent

A local-first, safety-conscious AI-assisted recruitment follow-up workflow for Microsoft Outlook.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![React 19](https://img.shields.io/badge/react-19.0-cyan.svg)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-teal.svg)](https://fastapi.tiangolo.com/)

---

## Overview

**Recruitment Follow-Up Agent** is a specialized desktop-grade application designed for talent acquisition teams and recruitment account managers. It automates candidate submission tracking, monitors client interview milestones, calculates SLA feedback deadlines, and drafts professional follow-up communications directly within Microsoft Outlook—without ever sending an email autonomously.

Built with a local-first architecture and strict human-in-the-loop governance, the agent ensures that recruitment communications maintain context, adhere to corporate recipient policies, and require explicit manager review before any message is dispatched.

### Who It Is For
- **Recruitment Account Managers & Staffing Specialists**: Managing high volumes of candidate submissions across multiple enterprise client accounts.
- **Talent Acquisition Operations**: Requiring deterministic tracking of client response SLAs (such as 48-hour feedback windows) and interview scheduling stages.
- **Privacy- & Security-Conscious Organizations**: Requiring local-only execution, zero external cloud telemetry, and strict Microsoft Graph permission boundaries.

### Why It Exists
Traditional recruitment automation often suffers from two extremes:
1. **Unsafe Automated Senders**: Black-box bots that broadcast emails automatically, risking damaged client relationships from misclassified replies or obsolete context.
2. **Manual Spreadsheets & Inbox Searching**: Labor-intensive tracking that leads to missed client feedback windows and delayed interview coordination.

Recruitment Follow-Up Agent solves this by pairing a **deterministic workflow state machine** with **advisory AI text analysis** and **manager-approved Outlook drafts**.

---

## Key Safety & Architectural Invariants

- **Strictly No Automated Email Sending**: The application creates draft replies in Microsoft Outlook for human verification. It never requests the Microsoft Graph `Mail.Send` permission and cannot send emails.
- **Deterministic State Machine Precedence**: Core business decisions (e.g. eligibility filtering, 48-hour feedback timers, interview state progression) are governed by deterministic rules. AI models operate solely in an advisory capacity (summarizing threads and proposing draft wording).
- **Exact Graph Conversation Identity**: Thread and reply association uses immutable Microsoft Graph message and conversation IDs (`conversationId`, `graph_immutable_id`), never brittle fuzzy matching on candidate names or Job IDs.
- **Local-First & Cryptographically Encrypted**: Binds exclusively to loopback (`127.0.0.1`), stores credentials in the native OS Keychain (macOS Keychain), and encrypts candidate records and email bodies at rest using AES-GCM in SQLite.
- **BCC Recipient Allowlist**: Draft BCC fields start empty and restrict additions strictly to allowlisted corporate domains. Any recipient modification invalidates prior draft approval hashes.
- **3-Month Cryptographic Retention**: Full email content and attachments are cryptographically shredded after 3 months, retaining only non-identifying operational summary records.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    React 19 Frontend                        │
│   (Today Queue · Interviews · Record Workspace · Retention) │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / JSON (127.0.0.1 + CSRF)
┌──────────────────────────────▼──────────────────────────────┐
│                    FastAPI Backend Core                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Deterministic Policy Engine             │  │
│  │  (48h Timers · Status Machine · Recipient Validator) │  │
│  └──────────────────────────┬───────────────────────────┘  │
│                             │                               │
│  ┌──────────────────────────┴───────────────────────────┐  │
│  │               Advisory AI Engine (Optional)          │  │
│  │        (Local Ollama / LLaMA 3.2 · Prompt Sandwich)   │  │
│  └──────────────────────────────────────────────────────┘  │
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
┌───────────────▼───────────────┐ ┌───────────▼───────────────┐
│     Microsoft Graph API       │ │   Local Encrypted Storage │
│  (Mail.Read · Draft Creation) │ │  (SQLite AES-GCM · Keyring)│
└───────────────────────────────┘ └───────────────────────────┘
```

---

## Quick Start

### 1. Prerequisites
- **Python 3.9+**
- **Node.js 18+** & **npm**
- **macOS** (for native Keychain integration) or local keyring support

### 2. Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/anu007lko/New-FollowUp-Agent.git
cd New-FollowUp-Agent

# Backend setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend setup
cd frontend
npm install
cd ..
```

### 3. Running in Offline Synthetic Mode (Default)

The application includes synthetic test data fixtures, allowing you to explore the full dashboard, decision queue, and interview workflows without configuring live credentials:

```bash
# Start backend on 127.0.0.1:8000
python3 backend/app/main.py

# In a separate terminal, start frontend on http://localhost:5173
cd frontend
npm run dev
```

### 4. Running with Live Microsoft Graph (Optional)

To connect to a configured Microsoft Outlook mailbox:
1. Configure Azure App Registration with delegated `Mail.Read` and `Mail.ReadWrite` permissions (ensure `Mail.Send` is **not** granted).
2. Set environment variables:
   ```bash
   export AZURE_CLIENT_ID="<your-client-id>"
   export AZURE_TENANT_ID="<your-tenant-id>"
   ```
3. Run the interactive device authentication:
   ```bash
   python3 backend/app/infrastructure/msal_interactive.py
   ```
4. Start the application with `python3 backend/app/main.py`.

---

## AI-Assisted Development

This repository utilizes AI coding assistants, including **OpenAI Codex**, as tools for development, code maintenance, and automated testing assistance.

The following engineering governance principles apply to all AI-assisted contributions:
- **Maintainer Authority**: Human maintainers hold sole responsibility for architectural decisions, security reviews, and release readiness.
- **Test Suite Authority**: All AI-suggested changes must satisfy existing domain contracts, unit tests, and type checks.
- **Safety Boundary Enforcement**: AI tools cannot modify safety invariants (such as the prohibition of `Mail.Send` or automated email transmission).
- **No Unvetted Code**: AI-generated code is reviewed line-by-line prior to integration.

---

## Project Status & Metadata

- **Current Version**: `v0.1.0`
- **Author / Maintainer**: Tarun Srivastava
- **Configured Mailbox**: Configured Outlook mailbox (via Microsoft Graph)
- **Deployment**: Local-only, bound strictly to `127.0.0.1`
- **Time Zone**: `America/New_York`
- **License**: [MIT License](LICENSE)
- **Contributing**: [CONTRIBUTING.md](CONTRIBUTING.md)
- **Security Policy**: [SECURITY.md](SECURITY.md)

---

## Technical Specifications & Documentation Map

When documents conflict, use this order of precedence: approved ADRs; approved SRS/PRD; approved API/data/security specifications; other plans.

1. [01-BRD: Business Requirements Document](01-BRD.md)
2. [02-SOW: Statement of Work](02-SOW.md)
3. [03-PRD: Product Requirements Document](03-PRD.md)
4. [04-SRS: Software Requirements Specification](04-SRS.md)
5. [05-TRD: Technical Requirements Document](05-TRD.md)
6. [06-ARCHITECTURE: Architecture Specification](06-ARCHITECTURE.md)
7. [07-DATA-MODEL: Data Model & Dictionary](07-DATA-MODEL.md)
8. [08-API-CONTRACT: API Contract](08-API-CONTRACT.md)
9. [09-UI-UX: UI/UX Specification](09-UI-UX.md)
10. [10-SECURITY-THREAT-MODEL: Security & Threat Model](10-SECURITY-THREAT-MODEL.md)
11. [11-GRAPH-INTEGRATION: Microsoft Graph Integration](11-GRAPH-INTEGRATION.md)
12. [12-LLM-PROMPTS: LLM & Prompt Specification](12-LLM-PROMPTS.md)
13. [13-RETENTION-POLICY: Retention & Cryptographic Reduction Policy](13-RETENTION-POLICY.md)
14. [14-MIGRATION-IMPORT: Migration & Import Plan](14-MIGRATION-IMPORT.md)
15. [15-TEST-STRATEGY: Test Strategy & Safety Verification](15-TEST-STRATEGY.md)
16. [16-ACCEPTANCE-CRITERIA: Acceptance Criteria](16-ACCEPTANCE-CRITERIA.md)
17. [17-OPERATIONS-RUNBOOK: Operations Runbook](17-OPERATIONS-RUNBOOK.md)
18. [18-RELEASE-PLAN: Release Plan](18-RELEASE-PLAN.md)
19. [19-ADRS: Architecture Decision Records](19-ADRS.md)
20. [20-RISK-REGISTER: Risk Register](20-RISK-REGISTER.md)
21. [21-RACI: RACI Matrix](21-RACI.md)
22. [22-SOURCE-CODE-STANDARDS: Source Code Standards](22-SOURCE-CODE-STANDARDS.md)
23. [23-MILESTONE-TRACKER: Milestone Tracker](23-MILESTONE-TRACKER.md)
24. [24-OPEN-DECISIONS: Open Decisions Log](24-OPEN-DECISIONS.md)
25. [25-PRODUCTION-READINESS-AND-LESSONS: Production Readiness & Lessons Learned](25-PRODUCTION-READINESS-AND-LESSONS.md)

---

## Core Invariants

- The application never sends mail and never requests `Mail.Send`.
- The approved 8:00 AM America/New_York mailbox review may import and update deterministic local statuses. Follow-up decisions, drafts, closure, deletion, and sending remain manager-controlled; automatic drafts and email sending are prohibited.
- Reply association uses immutable source-message identity plus exact Outlook conversation identity, never Job ID.
- Deterministic rules decide eligibility and actions; the LLM only classifies, summarizes, and suggests text.
- Uncertainty remains in Needs Review and can never silently close a record.
- Full content and attachments are encrypted and retained for 3 months; afterward only the defined basic operational record remains.
- No production change occurs without explicit approval; the 8:00 AM unattended review was explicitly approved on 2026-08-08.

---

## Production Baseline — 2026-08-08

- Loopback-only FastAPI and React app on `127.0.0.1` with encrypted SQLite and macOS Keychain.
- Existing Microsoft Graph consent only; `Mail.Send` is absent and prohibited.
- Daily review at 8:00 AM ET plus one missed-run catch-up; no automatic drafts, closure, deletion, or sending.
- **Review mailbox now** is the manual equivalent of the daily review: it imports new eligible Submissions messages, re-reads every stored primary and manager-linked interview conversation by exact Graph `conversationId`, recalculates deterministic statuses/timers, and reloads the dashboard/open record. It never creates a draft or sends email.
- Manager-approved Reply All drafts preserve Outlook history and are sent manually in Outlook.
- See `25-PRODUCTION-READINESS-AND-LESSONS.md`.

---

## Visual-System Release and Handoff — 2026-08-09

The released local UI uses the calm, cinematic workspace visual system: Today, Work Queue, Interviews, and Retention & Operations; a focused dashboard decision card; conversation path; and clear manager actions. The update is presentation-only: it makes no Graph, database, draft, or send action by itself, retains local assets/font fallbacks, and honors reduced-motion preferences.

See `PROJECT-HANDOFF.md` for the current operating state and `09-UI-UX.md` for the visual specification.
