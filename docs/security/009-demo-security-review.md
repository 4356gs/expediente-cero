# Demo Security and Privacy Review

## Result

Repository controls are suitable for a synthetic hackathon demonstration when
the documented demo environment and deployment topology are used. This is not
a production security assessment.

## Verified controls

- HTTP schemas and domain invariants require synthetic source messages and
  document metadata.
- No document bytes, real customer data, credentials, or raw sensitive files
  are part of the MVP.
- OpenAI calls use bounded prompts, strict Structured Outputs, and `store=false`.
- The browser calls only the bounded same-origin Next.js proxy and never reads
  `OPENAI_API_KEY`.
- Model output, deterministic validation, and human-reviewed output remain
  distinct.
- Only a labeled human can approve or reject; blocking findings prevent
  approval and rejection requires a reason.
- Audit metadata is sanitized and the timeline is append-only through product
  contracts.
- Demo reset is unavailable through HTTP, requires environment `demo`, and
  requires an exact destructive confirmation.
- Render receives the OpenAI key as an unsynced secret and API docs are disabled.

## Accepted demo risks

- The demo has no authentication and must contain synthetic data only.
- SQLite plus one service instance is appropriate only for this bounded demo.
- Render `starter` and its persistent disk incur cost and require account-level
  access controls managed by the human owner.
- A public demo URL can be used by third parties and consume model quota.
- Provider availability can interrupt a live recording; persisted synthetic
  fallback evidence must be labeled accurately.

## Required operator actions

- Never enter real names, identifiers, files, or case details.
- Restrict or remove the deployment after the judging window.
- Rotate the OpenAI key if it appears in a recording, log, shell history, or
  support exchange.
- Inspect screenshots and video for secrets and personal data before upload.
- Monitor model usage during the public demo.
- Do not describe generated output as legal, tax, accounting, employment, or
  eligibility advice.

## Deferred production controls

Authentication, authorization, rate limiting, abuse protection, PostgreSQL,
backups, production observability, data retention, incident response, and
multi-tenancy remain explicitly outside this MVP.
