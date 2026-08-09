# Implementation Decisions & Resolutions

## Genuinely Unresolved Blockers

There are currently **zero** unresolved implementation blockers remaining. All core architectural, workflow, policy, backup, and technology decisions have been resolved and approved by the Product Owner.

## Final decisions — 2026-08-08

- Daily review at 08:00 America/New_York with deterministic local updates: approved.
- Automatic drafts and email sending: prohibited; `Mail.Send` remains absent.
- Separate interview chains require candidate + Job ID/full unique subject + interview evidence + manager confirmation; never EP alone.
- Branding and multiple manager identities are future enhancements, not blockers.

## Resolved Decisions

1. **Category State Transition Mapping:**
   - *Acknowledgement*: set status to `In Evaluation` and restart the 48-calendar-hour timer from that message's timestamp.
   - *Feedback / Request for info*: set status to `Manager Action Required` and pause follow-up timing until marked handled by manager; never send automatically.
   - *Rejection*: display `Client Rejected` and prompt manager to close with reason `Client rejected`. Never auto-close.
   - *Position closed*: display `Position Closed` and prompt manager closure with reason `Position closed`. Never auto-close.
   - *Duplicate / Already submitted*: place in `Needs Review` and prompt manager closure or another decision. Never auto-close.
   - *Unrelated*: place in `Needs Review` without resetting the follow-up timer.
   - *Uncertain or conflicting*: remain in `Needs Review`.
   - *Message Visibility*: A newer meaningful message must always be visible with sender, timestamp, evidence, and timer effect.

2. **Draft BCC Policy:**
   - Every draft starts with an **empty** BCC field.
   - Manager may optionally add or remove BCC recipients strictly ending in `@clifyx.com`.
   - External or historical BCC is never copied automatically.
   - Recipient changes invalidate prior draft approval and require reapproval.

3. **Interview Outcome State Machine:**
   - After a scheduled interview passes, manager confirmation is required:
     - *Completed*: starts the 48-hour feedback timer.
     - *Rescheduled*: requires entry of a new date and time.
     - *Cancelled & Not Confirmed*: move record to `Needs Review` for immediate manager attention.
     - *Auto-closure*: No interview outcome closes a record automatically.

4. **Encrypted Local Backup & Restore (M6):**
   - M6 includes a manager-triggered encrypted local backup and tested restore process protecting local decisions, notes, operational records, and audit history.
   - Restores immediately enforce 3-calendar-month retention reduction before content becomes accessible to users.
   - Outlook remains untouched as the source for rebuilding available mailbox content.

5. **Approved Technology Stack (ADR-009):**
   - Python 3.11+ with FastAPI backend for local application and domain API.
   - React with TypeScript and Vite for the local presentation layer.
   - SQLite with SQLCipher (or reviewed encrypted SQLite design) for local data storage.
   - macOS Keychain for protecting master encryption keys.
   - Strictly bound to `127.0.0.1` (loopback listener only).

6. **Prior Baseline Decisions:** Strict `tcs.com` To/CC eligibility, end-client co-recipients allowed, July 10, 2026 initial import start, newest message retention anchor, local-only deletion (never Outlook), reopening closed records, retention of Other notes, macOS-login-only initial access.

## External follow-up, not a product decision — 2026-08-09

The connected Figma file requires one final verified write-back of the accepted visual frame/tokens. It is blocked only by the Figma Starter-plan connector quota. This does not block the local application or change any approved product requirement; completion is recorded in `PROJECT-HANDOFF.md` when the connector permits the write.
