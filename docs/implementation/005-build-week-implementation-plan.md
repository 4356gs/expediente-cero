# Build Week Implementation Plan

## Delivery objective

Produce one credible end-to-end demonstration of synthetic intake preparation
with typed GPT-5.6 output, independent deterministic validation, mandatory human
review, and a traceable audit history. Scope remains limited to the three
approved procedures.

## Blocks

### Block 0 — Backend bootstrap and quality baseline

- FastAPI application factory and package boundaries.
- Environment-backed configuration with no committed secrets.
- Typed liveness and readiness endpoints.
- Ruff, strict mypy, pytest, coverage threshold, and API CI.
- No frontend, persistence, domain behavior, or OpenAI call.

Exit gate: `make check` passes and both operational endpoints return HTTP 200.

### Block 1 — Domain kernel and transition rules

- Enumerations and framework-independent entities from the approved domain model.
- Case transition policy and aggregate invariants.
- Unit tests for every allowed and forbidden transition.

Exit gate: domain imports no FastAPI, SQLAlchemy, or OpenAI modules; transition
tests cover terminal states and human-decision constraints.

### Block 2 — SQLite persistence and audit foundation

- SQLAlchemy models, repository interfaces, SQLite adapters, and Alembic.
- Atomic case transition plus append-only audit event.
- Synthetic fixtures for the three demo scenarios.

Exit gate: migrations upgrade a blank database; repository integration tests
prove atomic state and audit persistence.

### Block 3 — Intake HTTP workflow

- Typed endpoints to create, retrieve, and list synthetic cases.
- Source-message and synthetic document-metadata persistence.
- Typed error envelope and input constraints.

Exit gate: API integration tests create and retrieve each demo case without
model calls.

### Block 4 — GPT-5.6 structured intake analysis

- Versioned prompt and strict Pydantic response schema.
- `IntakeAnalyzer` interface, fake implementation, and Responses API adapter.
- `store=false`, refusal/failure handling, and sanitized model-run metadata.

Exit gate: offline contract tests pass; one explicitly marked live test proves
schema-constrained GPT-5.6 output without exposing credentials.

### Block 5 — Deterministic validation and checklists

- Versioned templates for self-employed registration, employee hiring, and
  grant application.
- Required-field, document, date-consistency, and blocking-question checks.
- Checklist results kept separate from model-derived analysis.
- Explicit synchronous `POST /cases/{case_id}/validation` trigger for cases in
  `analyzed`; validation never performs a model call.
- Atomic persistence of checklist results, findings, template version,
  `validation_completed_at`, the `analyzed` -> `needs_review` transition, and
  its audit event.

The initial template version is `deterministic-validation-v1`. It defines
bounded internal intake requirements, not legal requirements:

| Procedure | Required fact fields | Required document types |
| --- | --- | --- |
| `self_employed_registration` | `activity`, `start_date` | `identity` |
| `employee_hiring` | `employee_name`, `requested_start_date`, `contract_start_date` | `employment_contract` |
| `grant_application` | `applicant_name`, `grant_program`, `project_summary` | `project_memo`, `detailed_budget` |

Only a non-blank `stated` fact with a valid persisted source reference satisfies
a required field. Inferred values require review; unknown, absent, or blank
values are missing. Dates use `YYYY-MM-DD`. Employee requested and contract
start dates must match. Procedure and output-language mismatches, invalid
evidence references, invalid dates, conflicting stated values, and unresolved
blocking questions create blocking findings. Model-reported contradictions are
warnings unless an independent deterministic rule confirms them.

Validation completes even when it produces blocking findings. The case enters
`needs_review`, while the aggregate invariant prevents later approval.
Repeating validation outside `analyzed` returns a state conflict; results are
never partially persisted.

Exit gate: fixture-based tests demonstrate missing data, contradictory dates,
and a partial grant checklist; blocking findings cannot be overridden.

### Block 6 — Follow-up drafting and human decisions

- Independent `FollowUpDrafter` application port and fake adapter, separate
  from `IntakeAnalyzer`.
- Separate synchronous bounded call after validation while the case remains in
  `needs_review`; generation reads only persisted case, synthetic intake and
  document metadata, analysis, checklist, and findings.
- Persisted `OutputLanguage` as the sole language source; no request override.
- Responses API adapter with strict Structured Outputs, `store=false`, the
  existing configurable model, prompt version `follow-up-draft-v1`, and a
  `1200` output-token maximum. Generated and reviewed text are limited to
  1..4000 characters after validation or outer trim; no
  agents, tools, function calling, web search, or legislative retrieval.
- `ModelRun.in_progress` plus atomic generation start, completion, failure, and
  refusal boundaries. Failure and refusal store no draft and permit a new run.
- Configurable follow-up-attempt lease through
  `EXPEDIENTE_CERO_FOLLOW_UP_ATTEMPT_LEASE_SECONDS=300`, without an alias.
  `Settings` construction rejects a lease not greater than
  `openai_timeout_seconds` and prevents startup. Runtime service-resolution
  configuration failures retain `follow_up_configuration_error` when a new
  generation resolves the provider after provider-free checks.
- UTC lease calculation with SQLite timestamps restored to UTC and the exact
  boundary `now_utc >= started_at_utc + lease_seconds`. An unexpired attempt
  returns a conflict; an expired attempt is atomically failed with
  `follow_up_attempt_abandoned`, audited, and replaced while the case remains
  in `needs_review`.
- SQLite partial unique index for one active follow-up run per case, conditional
  expired-run claim requiring one affected row, atomic replacement and events,
  and unique-constraint protection for the residual race.
- Unique per-case `FollowUpDraft`, immutable `model_text`, initially equal and
  editable `reviewed_text`, and optimistic `version` updates. Immutability is
  enforced by domain, application, repository, and HTTP contracts, without a
  SQLite trigger.
- Unique immutable `ReviewDecision`; only a labeled human can approve or
  reject, rejection requires a non-blank reason, and deterministic blocking
  findings prevent approval.
- Decision lookup before state validation: a semantically identical retry
  returns the existing decision from a terminal case, a different retry
  conflicts, and `needs_review` is required only when no decision exists.
- External trimming and validation for reviewer label, reason, and reviewed
  text before idempotency. Approval forbids a non-empty reason with
  `422 request_validation_error`; rejection requires one with
  `422 rejection_reason_required`.
- Atomic terminal decision, transition, specialized review event, and
  `case_status_changed`; both events share a timestamp, have no causal order at
  equal timestamps, and are displayed stably by `recorded_at` and ID.
- Only `needs_review -> approved` and `needs_review -> rejected` terminal
  transitions; no drafting state.
- Typed generate, retrieve, edit, decision, and stable timeline endpoints
  defined in the system architecture, including explicit `200` idempotent and
  `201` creation responses for both POST operations.
- Generation checks case existence, existing draft, persisted prerequisites,
  and an active attempt before resolving OpenAI, preserving canonical error
  precedence when provider configuration is unavailable.
- Idempotent successful drafting and identical decisions, edit no-op behavior,
  concurrency conflicts, unique constraints, and transactional audit events.
- Sanitized events for generation start, draft creation, failure, refusal,
  edit, approval, and rejection.

Planned verification covers all three procedures in both languages, the strict
Structured Outputs contract and `store=false`, exclusive use of persisted
inputs, immutable model text, edit versioning, idempotency and concurrent
conflicts, refusal/timeouts/provider errors, mandatory rejection reasons,
approval blockers, exclusively human decisions, rollback on persistence or
audit failure, and a complete stable timeline. Lease-specific cases cover an
active unexpired attempt, expired-attempt detection, recovery with a new
`ModelRun`, concurrent competition to claim an expired attempt, and atomic
rollback of the recovery transaction. Additional cases cover the exact expiry
boundary, startup rejection when lease is less than or equal to provider
timeout, `ModelRun` completion timestamp invariants, normalization before edit
and decision idempotency, approval with a non-empty reason returning the
existing `422 request_validation_error` envelope, both terminal events with a
shared timestamp, stable non-causal timeline ordering, conflict mappings, and
the allowed and forbidden audit metadata fields.
Migration verification includes populated `0003 -> 0004 -> 0003` preservation,
version backfill, ORM/Alembic invariant parity, checks, and the partial index.
Recovery rollback verification fails between abandoned-attempt handling and
replacement start and proves that no partial run or event remains.

Exit gate: the three procedures work in Spanish and Galician through the API;
retries and concurrency preserve one draft and one decision; failure paths roll
back consistently; and only a human action can produce a terminal state.

### Block 7 — Reviewer interface

- Next.js interface for case intake, four-way evidence separation, draft edit,
  review decision, and audit timeline.
- Provider-free read contracts for persisted analysis, validation, and review
  decision so an existing workspace can be reconstructed after reload.
- Typed same-origin API proxy, explicit loading/empty/error/refusal/conflict
  states, responsive accessibility, and component/integration/E2E coverage.
- No direct browser-to-OpenAI traffic.

The detailed screens, contracts, behavior, verification matrix, and acceptance
criteria are canonical in `006-block7-reviewer-interface.md`.

Exit gate: the same interface completes and reopens all three synthetic
scenarios, represents both languages, preserves all four evidence boundaries,
and passes API plus web quality gates without a live model call.

### Block 8 — Demo hardening and submission

- End-to-end tests, failure-path rehearsal, seed/reset command, and demo script.
- Security/privacy review and visible synthetic-data/advice boundaries.
- Build Week evidence, screenshots, video, deployment, and submission links.

The repository deliverables, safe demo-data lifecycle, Render reference
deployment, evidence policy, and external human completion gate are canonical
in `007-block8-demo-hardening.md`.

Exit gate: clean-machine rehearsal succeeds and every submission claim is tied
to a test, commit, screenshot, session record, or running artifact.

## Time-box policy

Blocks 0–3 establish the reliable vertical skeleton. Blocks 4–6 are the judged
product core. Block 7 begins only after the complete workflow works through the
API. Block 8 reserves the final delivery window; new features are not accepted
once hardening starts.

If schedule pressure appears, reduce interface polish and deployment breadth.
Do not remove deterministic validation, human approval, auditability, the three
accepted demo scenarios, or the GPT-5.6 structured-output evidence.
