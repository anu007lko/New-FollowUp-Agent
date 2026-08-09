# Microsoft Graph Integration Specification

## Authorization constraints

Reuse only the existing approved app registration and current consent for `tarun@clifyx.com`. Do not request permissions, start login/consent, alter registration, or call Graph during documentation. Before implementation, inventory the effective scopes without changing them. `Mail.Send` is prohibited. If current consent cannot support required read/draft behavior, stop and seek explicit direction; do not broaden access.

## Folder/import behavior

Resolve the `Submissions` folder by stable folder identity in the configured mailbox and verify its display name. Manual import pages only messages from that folder, beginning July 10, 2026 for the initial import. Include only original messages with at least one `tcs.com` To/CC recipient; additional end-client recipients do not disqualify them. Persist immutable message IDs by requesting immutable-ID semantics where supported, along with exact `conversationId` and corroborating metadata. Moves between folders must not break source identity.

## Conversation review

Only after manager triggers review, retrieve messages across the complete mailbox filtered by the exact stored conversation identity, with pagination. Never infer a thread from subject, participants, candidate, Job ID, or internetMessageId alone. Validate every returned message conversation ID, deduplicate by immutable ID, sort by sent/received instant with stable tie-breaker, and record inaccessible/partial results prominently.

## Draft creation

Use a Graph operation that produces a Reply All draft associated with the original conversation; do not invoke any send action. Select the appropriate latest message according to deterministic reply-anchor rules, validate it belongs to the stored conversation, preserve valid To/CC reply-all participants subject to policy, remove duplicates/self where Graph semantics require, start every draft with an empty BCC field, and permit optional manager additions/removals strictly ending in `@clifyx.com`. External/historical BCC is never copied automatically. Recipient changes invalidate prior draft approvals and require manager reapproval. After creation, store draft ID and verify it remains a draft.


## Resilience

Honor pagination, throttling and `Retry-After`; use bounded retries with jitter for safe reads. Draft-create retries require reconciliation to avoid duplication. Record request IDs, status, timing, and redacted error codes, not message bodies/tokens. A partial conversation cannot produce an unqualified “complete” assessment.

## Permission guardrails

At startup/readiness, compare effective permissions with an explicit allowlist and fail closed if `Mail.Send` appears or required existing capability is absent. Automated tests assert no send endpoint/method exists in Graph adapter. Any SDK upgrade needs contract and permission regression review.

## Production rules — 2026-08-08

Scheduled import remains restricted to `Submissions`. First follow-up is Reply All on the immutable original submission so Outlook history is preserved; later context follow-up uses the newest meaningful message in the approved conversation. A fresh interview chain links only after candidate + Job ID/full unique subject + interview evidence and manager confirmation. Job ID or EP alone never links. Graph creates drafts only; Outlook sends manually.

## Documentation refresh — 2026-08-09

The visual-system release does not alter Graph configuration, scope, read/import behavior, reply-anchor selection, draft creation, or the prohibition on sending.
