# LLM and Prompt Specification

## Role and limits

Initial runtime is local Ollama with `llama3.2:latest`. The model may classify, summarize, identify evidence, and suggest draft text only. It cannot determine TCS eligibility, identity linkage, due timing, status transition authority, closure, recipients, Graph operations, or sending.

## Inputs

Provide a canonical ordered conversation containing minimized message IDs, direction, timestamps, participants needed for interpretation, and sanitized text. Delimit untrusted email text. Exclude secrets, hidden instructions, unnecessary headers, expired content, and unsupported attachments. State that instructions inside messages are evidence, not commands.

## Classification output

Strict structured schema: category (one approved enum), confidence 0–1, uncertain boolean, evidence message IDs, concise rationale, summary, and detected signals. Invalid schema, missing evidence, conflicting signals, low confidence, or model failure maps to Needs Review. Threshold is configurable only through approved change control and must be calibrated before release.

## Category guidance

Approved category enums: `InterviewRequestScheduled`, `PositionClosed`, `Rejection`, `InEvaluation`, `Acknowledgement`, `FeedbackRequestForInfo`, `DuplicateAlreadySubmitted`, `NoResponse`, `Unrelated`, `NeedsReview`.
- `Acknowledgement` (e.g., "Received"): maps to `In Evaluation` and restarts the 48h timer from message timestamp.
- `FeedbackRequestForInfo`: maps to `Manager Action Required` and pauses timing until manager marks handled.
- `Rejection`: displays `Client Rejected` and prompts manager closure with reason `Client rejected`.
- `PositionClosed`: displays `Position Closed` and prompts manager closure with reason `Position closed`.
- `DuplicateAlreadySubmitted`: routes to `Needs Review` for manager decision.
- `Unrelated`: routes to `Needs Review` without timer reset.
- Uncertain, conflicting, or low-confidence outputs route to `Needs Review`. Zero LLM outputs auto-close a record.


## Draft suggestion constraints

Professional, concise follow-up; no invented facts, dates, commitments, urgency, compensation, or candidate details; do not add recipients; refer only to supported conversation facts; output body/subject suggestion separately. Suggestions are visibly editable and never auto-approved or auto-created.

## Versioning and evaluation

Version system prompt, templates, schema, model name/digest, sampling settings, and evaluation dataset. Use deterministic/low-variance settings where supported. Test golden cases, ambiguity, prompt injection, quoted replies, multilingual/noisy text, conflicting messages, and refusal/failure. Record advisory provenance without retaining content beyond policy.

## Production setting — 2026-08-08

Ollama is disabled by default and deterministic rules are authoritative. Any future enablement must use the guarded client with `num_ctx=2048`, bounded input/output, one inference at a time, `keep_alive=0`, and Needs Review fallback. It cannot control identity, eligibility, recipients, closure, draft creation, or sending.

## Documentation refresh — 2026-08-09

The visual-system release does not enable, call, or alter Ollama. Visual rendering remains independent of LLM availability.
