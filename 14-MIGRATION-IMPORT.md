# Migration and Import Plan

## Principle

This is a clean rebuild. Do not reuse, modify, connect to, or directly import the old app, its database, tokens, configuration, repository, service, or deployment. The Outlook mailbox is the authoritative initial source.

## Initial import phases

1. Readiness: verify approved configuration, existing permissions, key protection, storage capacity, and source folder identity without changing consent.
2. Dry-run preview: count messages on or after July 10, 2026 and deterministic TCS candidates; write no domain records if preview mode is chosen.
3. Bounded pilot: manager selects a date window; import idempotently; review exceptions.
4. Reconciliation: compare counts, duplicate handling, identity completeness, exclusions, and spot-check conversations.
5. Approved expansion: import remaining agreed window only after pilot sign-off.

## Mapping and validation

Map immutable Graph message identity and exact conversation identity before business fields. Job ID remains informational. Reject/quarantine records missing required identity. Record source folder ID, import run, rule version, and eligibility evidence. Deduplicate only on authoritative immutable identity.

## Rollback

Before production use, local imported records from a named import run may be removed using a tested, audited rollback that does not touch Outlook. Draft creation is disabled during import validation. Never delete/move mailbox messages. Old-app material remains untouched.

## Optional legacy data

Legacy import is a future separate decision requiring provenance, schema mapping, malware/privacy review, identity reconciliation against Outlook, and owner approval. No legacy Job-ID link is trusted.

## Migration completion — 2026-08-08

The clean rebuild contains 114 complete mailbox-derived records and no placeholders after the approved 2026-08-08 catch-up. Import is idempotent by immutable ID, refreshes exact conversations, and preserves manager state. The old app and port `8765` service were not reused or modified.

## Documentation refresh — 2026-08-09

The visual-system release performs no import, migration, hydration, or record mutation and does not change the import boundary.
