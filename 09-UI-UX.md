# UI/UX Specification

## Design principles

Professional, calm, immersive, and low-clutter. Show the next safe action, explain every derived state, distinguish advice from facts, and never imply autonomous activity. Branding remains neutral pending decision.

## Information architecture

Dashboard; Import results; Needs Review; Follow-up due; Record workspace; Draft review; Audit/details; Settings/diagnostics; Retention maintenance.

## Dashboard

Top summary counts: Needs Review, Pending Follow-up, In Evaluation with due badge, and recently closed. Filters include status/category/date; search may include candidate/client/job display data, but selection never changes identity linkage. Primary global action is Import Submissions. No auto-refresh that performs Graph calls.

## Record workspace

Header shows candidate/position display fields, exact conversation indicator, current status, last review time, latest update sender/time, and due explanation. Main timeline shows complete reconciled messages and attachments; every meaningful newer message clearly displays sender, timestamp, evidence, and timer effect. Side decision panel shows deterministic findings first and LLM summary/classification clearly labeled “Advisory.” Evidence links jump to the message. Ambiguity banner blocks closure recommendations and selects Needs Review. Specific category UI behaviors:
- **Acknowledgement**: sets `In Evaluation` and displays timer restarted from that message's timestamp.
- **Feedback / Request for Info**: sets `Manager Action Required`, pausing ordinary follow-up timing until marked handled.
- **Rejection**: displays `Client Rejected` banner and prompts manager to close with reason `Client rejected`.
- **Position Closed**: displays `Position Closed` banner and prompts manager closure with reason `Position closed`.
- **Duplicate / Already Submitted**: places record in `Needs Review` and prompts manager decision.
- **Unrelated**: places record in `Needs Review` without resetting timer.
- **Scheduled Interview Passed**: shows confirmation card requiring manager decision (Completed starts 48h feedback timer; Rescheduled requires new date/time entry; Cancelled & Not Confirmed move record to `Needs Review` for immediate attention; zero auto-closures).

## Actions

Request Follow-up and Close are explicit buttons. Close opens a reason control; Other reveals required note and confirmation. Interview outcomes never close a record automatically. Request Follow-up enables Generate Suggestion, which does not create an Outlook draft. Draft review starts with an empty BCC field, displays editable To/CC, allows manager addition/removal of `@clifyx.com` BCC recipients only, omits/blocks external/historical BCC, surfaces policy warnings, and invalidates prior draft approval if recipients are edited. A final separate “Create draft in Outlook” confirmation states “This app cannot send email.” Success says “Draft created—review and send in Outlook,” never “Email sent.”


## States and feedback

Empty, loading, progress, partial success, offline Graph, unavailable Ollama, stale conversation, conflict, and retention-reduced states each have plain-language recovery. External calls show progress and cancellation where safe. Dates display New York time with zone abbreviation and an absolute timestamp in details.

## Accessibility/privacy

Full keyboard access, visible focus, semantic headings/controls, AA contrast, reduced motion, screen-reader announcements, no color-only status. Sensitive content is concealed in previews/app switcher where feasible; clipboard/export requires explicit action. Attachment rendering is sandboxed or download-only based on type.

## Production UI — 2026-08-08

Final navigation is Dashboard, Work Queue, Interviews, and Retention & Operations. Record details use Overview, Conversation, Notes, and Details tabs; one primary action is shown and secondary actions collapse. Labels plainly state local-only, daily review at 8:00 AM ET, and email sending disabled. Raw Graph IDs stay hidden.

The top bar exposes a clearly labelled **Review mailbox now** button rather than an ambiguous refresh icon. While running it displays **Reviewing…**, prevents a duplicate click, and announces completion, partial warnings, or failure in plain language. Completion reloads both the work queue and the currently open record. The action never creates a draft and never sends email.

## Approved visual-system release — 2026-08-09

The approved design language is a spacious, cinematic local workspace rather than a dense administration console. It is intentionally expressive without adding operational complexity.

- **Shell:** a slim permanent rail, restrained top bar, local-only indicator, and clearly named refresh/review control.
- **Dashboard:** a single high-priority focus card, a readable conversation path, and a compact later-today queue. The primary decision remains obvious: review the exact conversation before acting.
- **Surfaces:** dark aurora-room backdrop, translucent charcoal panels, fine hairline borders, teal/blue/violet highlights, soft depth, and controlled glow. Decoration never obscures data or actions.
- **Typography:** expressive serif display type for only the greeting/focus decision; an accessible sans-serif system for navigation, metadata, controls, tables, and workflow text. Font fallbacks are local and no remote font request is necessary.
- **Interaction:** cards and controls use small hover/focus feedback only. `prefers-reduced-motion` disables non-essential motion. Every interactive item has an obvious label and visible keyboard focus.
- **Responsive behavior:** desktop preserves the two-panel dashboard; narrower screens collapse deliberately to a readable single column with no horizontal overflow.
- **Safety language:** local-only status, review timing, Outlook-draft/manual-send policy, and no-send boundary remain visible in plain language.

The connected Figma file is the design reference. The final write-back is recorded in `PROJECT-HANDOFF.md` as pending solely on the current Figma Starter-plan connector limit; no design is considered saved until that write succeeds.
