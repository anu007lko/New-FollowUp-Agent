# Data Retention and Deletion Policy

## Policy

Full message history, content-bearing headers, model raw outputs, and attachments are stored encrypted for three calendar months from the latest message in the exact Outlook conversation. At expiry they are deleted only from the app's local database/storage and irreversibly reduced to the basic operational record defined in the data dictionary. The app never deletes or changes Outlook messages. No cloud telemetry or unapproved export is created.

## Lifecycle

Active full-content → due for reduction → reduction verified → operational-only. A preview enumerates affected records/bytes and blockers. Application deletes content ciphertext, attachment bytes/thumbnails/temp files, extracted text, prompt caches, and content-bearing logs; then verifies absence and records a non-content retention event.

## Anchors and holds

Every newly reconciled conversation message moves the retention expiry to three calendar months after that message. Legal/investigation hold is not assumed; if needed, its authority, scope, expiry, and audit must be specified before implementation. Holds cannot be silently created.

## Backups and derived copies

M6 includes a manager-triggered encrypted local backup and tested restore process. The backup protects local decisions, notes, operational records, and audit history. Backup retention must not resurrect content past policy: any restore operation immediately executes a mandatory retention sweep before content becomes accessible to users. macOS Keychain protects encryption master keys. Outlook remains untouched and is the source for rebuilding available mailbox content if local storage is cleared. Temporary files expire promptly after operation and no later than 24 hours. Logs exclude bodies/attachments and follow a minimal retention period.


## Operations

The approved daily mailbox review is allowed, but retention deletion remains a separate manager-approved maintenance action. Failures are visible and block release/backup claims until resolved.

## Production control — 2026-08-08

Expiry may be calculated and displayed automatically. Deletion never runs unattended: the manager reviews the expiry list and confirms selected records. Only local encrypted content is reduced; Outlook is never changed and manager notes remain.

## Documentation refresh — 2026-08-09

The Retention & Operations visual screen presents existing local-only policy/status information. It does not itself authorize or perform retention deletion.
