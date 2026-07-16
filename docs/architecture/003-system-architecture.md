# System Architecture

## Architectural objective

Deliver a working, traceable intake workflow within the hackathon period while
preserving a clear separation between generative interpretation, deterministic
validation, and professional judgment.

## Architecture style

Expediente Cero uses a modular monolith with two deployable applications:

- `apps/api`: FastAPI backend and application logic.
- `apps/web`: Next.js reviewer interface.

The MVP uses SQLite through SQLAlchemy and Alembic. Persistence remains behind
repositories so a later PostgreSQL migration does not change domain logic.

A distributed architecture is intentionally avoided. The MVP does not require
independent services, queues, or event infrastructure.

## Logical components

### Web application

Responsibilities:

- create and inspect synthetic cases;
- enter client messages and synthetic document metadata;
- select Spanish or Galician output;
- display structured analysis and deterministic validation separately;
- edit the follow-up draft;
- approve or reject a prepared case;
- display the audit timeline.

The browser never calls OpenAI directly and never receives the API key.

### HTTP API

Responsibilities:

- validate requests and responses;
- coordinate application use cases;
- enforce state transitions;
- expose the reviewer workflow;
- return typed error responses;
- provide health and readiness endpoints.

### Application layer

Use cases:

- create a case;
- analyze an intake;
- validate an analysis;
- generate a follow-up draft;
- approve a case;
- reject a case;
- retrieve a case and its audit history.

The application layer coordinates domain services and repositories but does not
contain HTTP or OpenAI SDK details.

### Domain layer

Responsibilities:

- case state and permitted transitions;
- supported procedure types;
- extracted facts and unresolved questions;
- checklist definitions and results;
- validation findings;
- review decisions;
- audit event semantics.

The domain layer must not import FastAPI, SQLAlchemy, the OpenAI SDK, or frontend
types.

## AI integration

A narrow `IntakeAnalyzer` interface isolates the model provider.

The OpenAI implementation:

- calls GPT-5.6 through the Responses API;
- requests Structured Outputs defined from Pydantic schemas;
- uses `store=false`;
- records model and prompt versions;
- returns typed data or an explicit failure;
- never decides whether a case is approved;
- never submits information to an external authority.

The MVP uses one model call for structured intake analysis and a separate,
bounded model call for the follow-up draft. `FollowUpDrafter` is an application
port independent of `IntakeAnalyzer`. The drafting call is synchronous, occurs
only after completed validation, and does not change the case out of
`needs_review` while it runs.

The drafter receives exclusively the persisted case, synthetic source message,
synthetic document metadata, analysis, checklist results, and validation
findings. Its language comes from the persisted `OutputLanguage` and cannot be
overridden by an HTTP request. The OpenAI implementation uses the Responses
API, strict Structured Outputs, `store=false`, the existing configurable model,
prompt version `follow-up-draft-v1`, and `max_output_tokens=1200`. Validated
output is 1 to 4000 characters; empty or oversized output is a typed
`no_structured_output` failure. It does not use agents, tools, function
calling, web search, retrieval, or external legislative knowledge.

Follow-up attempts use
`EXPEDIENTE_CERO_FOLLOW_UP_ATTEMPT_LEASE_SECONDS=300`, with no additional
alias. `Settings` construction requires
`follow_up_attempt_lease_seconds > openai_timeout_seconds`; invalid
configuration prevents application startup. `follow_up_configuration_error`
is reserved for configuration or dependency failures encountered while a new
generation resolves the provider after its provider-free precedence checks.

`started_at`, the derived `expires_at`, and the claim clock use UTC. SQLite
timestamps are restored as UTC before comparison. An attempt is expired exactly
when `now_utc >= started_at_utc + lease_seconds`.

## Deterministic validation

Validation executes after schema parsing and independently of the model.

An API client triggers it explicitly with
`POST /cases/{case_id}/validation` after analysis has produced `analyzed`. The
synchronous use case reads only persisted synthetic intake and analysis records
and performs no OpenAI request.

It checks:

- required fields for the selected procedure;
- required synthetic document types;
- incompatible or contradictory dates;
- unsupported procedure types;
- unresolved blocking questions;
- permitted case-state transitions.

Model confidence cannot override a deterministic blocking finding.

One transaction stores checklist results, findings, template version,
completion timestamp, the `needs_review` state, and its audit event. Blocking
findings do not fail validation; they prevent subsequent approval.

## Persistence

SQLite stores:

- cases;
- source messages;
- synthetic document metadata;
- structured analyses;
- checklist results;
- validation findings;
- generated drafts;
- review decisions;
- audit events;
- model-run metadata.

Raw documents and real personal information are outside the MVP.

## Audit trail

Each material action produces an append-only audit event containing:

- event type;
- case identifier;
- timestamp;
- actor type;
- prompt and model version when applicable;
- references to relevant records;
- sanitized metadata.

Secrets, hidden reasoning, API keys, and raw sensitive documents must never be
written to the audit trail.

## End-to-end request flow

1. The reviewer creates a synthetic case.
2. The API persists the original message and metadata.
3. The application invokes `IntakeAnalyzer`.
4. GPT-5.6 returns a schema-constrained analysis.
5. The API persists the model run and typed result.
6. Deterministic validators produce findings and checklist status.
7. The application requests a Spanish or Galician follow-up draft.
8. The reviewer edits and approves or rejects the prepared case.
9. The final decision and prior steps remain visible in the audit timeline.

## Block 6 HTTP contracts

All errors use the existing typed envelope
`{"error": {"code": "string", "message": "string", "issues": []}}`.
UUIDs and timestamps use their existing API representations.

### Generate and retrieve a draft

`POST /cases/{case_id}/follow-up-draft` has no request body. It first verifies
that the case exists, then returns an existing draft with `200` without checking
state or resolving the provider. With no draft, it validates `needs_review`,
persisted analysis and validation, then detects an active attempt. Only when a
new attempt is necessary does it resolve OpenAI. Missing configuration therefore
cannot hide `case_not_found`, a state conflict, an idempotent draft, or an active
attempt. First success returns `201` with `FollowUpDraftResponse`; both `200`
and `201` are explicit OpenAPI responses with that model.

`GET /cases/{case_id}/follow-up-draft` returns `200` with:

```text
FollowUpDraftResponse {
  id: UUID
  case_id: UUID
  language: OutputLanguage
  model_text: string, 1..4000 characters
  reviewed_text: string, 1..4000 characters
  prompt_version: string
  model_run_id: UUID
  version: integer >= 1
  created_at: datetime
  updated_at: datetime
}
```

Generation start atomically rechecks all preconditions and creates an
`in_progress` `ModelRun` plus `follow_up_generation_started`. Success completes
that run and stores the draft and `follow_up_draft_created` in one transaction.
Failure or refusal completes the run and records its event in one transaction,
without storing a draft. A failed or refused attempt may be retried with a new
run; a concurrent active attempt returns `follow_up_generation_in_progress`.
If that attempt is still `in_progress` but its lease has expired, the requesting
operation atomically rechecks status and expiry, marks the abandoned run
`failed` with `sanitized_error_code=follow_up_attempt_abandoned`, appends
`follow_up_generation_failed`, and creates the replacement `in_progress` run
and `follow_up_generation_started` event. The case remains in `needs_review`.
The atomic conditional claim permits one winner; concurrent losers observe the
new active run and return `follow_up_generation_in_progress`.

SQLite combines a partial unique index permitting only one
`follow_up_draft`/`in_progress` run per case with a conditional recovery update.
Recovery must affect exactly one expired row. Marking that row abandoned,
appending its failure event, creating the replacement run, and appending its
start event are one transaction; the partial index protects the residual race.

### Edit a draft

`PATCH /cases/{case_id}/follow-up-draft` accepts:

```text
FollowUpDraftUpdateRequest {
  reviewed_text: trimmed non-blank string, maximum 4000 characters
  expected_version: integer >= 1
}
```

It requires `needs_review`, an existing draft, no final decision, and a matching
version. It returns `200` with `FollowUpDraftResponse`. A changed value updates
only `reviewed_text`, increments `version`, and records
`follow_up_draft_edited` atomically. Text identical to the persisted value is a
no-op: the response is unchanged and no event is added.
Before validation and comparison, `reviewed_text` is trimmed only at its outer
edges and must remain non-empty.
Editing cannot alter `model_text`; the MVP enforces that invariant through the
domain, application, repository, and HTTP contracts rather than a SQLite
trigger. Direct administrative writes are outside scope.

### Record a human decision

`POST /cases/{case_id}/review-decision` accepts:

```text
ReviewDecisionRequest {
  decision: "approved" | "rejected"
  reason: string | null
  actor: HumanActor { label: non-blank string }
}
```

For a new decision, it requires `needs_review`, a persisted draft, and a human
actor. Rejection requires a non-blank reason; approval requires no active
deterministic blocking finding. It returns `201` with:

```text
ReviewDecisionResponse {
  id: UUID
  case_id: UUID
  decision: "approved" | "rejected"
  reason: string | null
  actor: HumanActor
  created_at: datetime
}
```

The use case first normalizes the request: `reviewer_label` is externally
trimmed, required, and compared case-sensitively; `reason` is externally
trimmed. Rejection with a null, empty, or whitespace-only reason returns
`422 rejection_reason_required`. Approval with an omitted, null, or
whitespace-only reason normalizes it to null; a non-empty reason returns
`422 request_validation_error` using the existing envelope.

The decision order is exact: normalize the request; query `ReviewDecision`;
return an existing semantically identical decision with `200`, including when
the case is terminal; return `409 review_decision_conflict` for an existing
different decision; and only when no decision exists require `needs_review`.
Both the creation `201` and idempotent `200` responses are explicit in OpenAPI
with `ReviewDecisionResponse`.
The new decision, terminal transition, specialized
`review_approved` or `review_rejected` event, and `case_status_changed` event
are persisted in one transaction. Both events share the operational timestamp
and have no causal ordering between them.

### Retrieve the timeline

`GET /cases/{case_id}/timeline` returns `200` with
`TimelineResponse { case_id: UUID, events: list[AuditEventResponse] }`. Each
event response contains `id`, `event_type`, `actor_type`, `actor_label`,
`recorded_at`, and sanitized `metadata`. `actor_label` is
mandatory and non-empty. Ordering is stable by `recorded_at` and then event
`id`; order between events with an equal timestamp carries no causal meaning.

### Block 6 errors

| HTTP | Code | Condition |
| --- | --- | --- |
| 404 | `case_not_found` | The case does not exist. |
| 404 | `follow_up_draft_not_found` | Retrieval or editing requires a missing draft. |
| 409 | `follow_up_state_conflict` | Case state, validation, or final-decision preconditions fail. |
| 409 | `follow_up_generation_in_progress` | A follow-up model run has an active, unexpired lease. |
| 409 | `follow_up_version_conflict` | `expected_version` is stale. |
| 409 | `review_decision_conflict` | A different immutable decision already exists. |
| 409 | `approval_blocked_by_findings` | Active deterministic blocking findings prevent approval. |
| 409 | `follow_up_draft_required` | A decision was requested before a draft exists. |
| 422 | `invalid_reviewed_text` | Reviewed text is blank or violates its bounded input contract. |
| 422 | `rejection_reason_required` | A rejection reason is absent or blank. |
| 502 | `follow_up_provider_error` | The provider failed without a more specific mapped outcome. |
| 502 | `follow_up_refused` | The provider refused to produce the structured draft. |
| 503 | `follow_up_configuration_error` | Configuration or a dependency is unavailable when a new generation resolves the provider after provider-free checks. |
| 504 | `follow_up_timeout` | The bounded synchronous request timed out. |
| 500 | `follow_up_persistence_error` | Draft lifecycle or audit persistence failed and rolled back. |
| 500 | `review_persistence_error` | Decision, transition, or audit persistence failed and rolled back. |

The active-attempt partial-index conflict maps to
`follow_up_generation_in_progress`; an optimistic edit affecting no row maps to
`follow_up_version_conflict`; a unique decision conflict causes a reread and
then an idempotent response or `review_decision_conflict`; a conditional
terminal transition affecting no row maps to `follow_up_state_conflict`;
blocking findings map to `approval_blocked_by_findings`; all other database
failures map to the corresponding persistence error.

## Case states

- `draft`: intake exists but has not been analyzed.
- `analyzing`: an analysis request is in progress.
- `analyzed`: a schema-valid analysis is persisted and awaits deterministic validation.
- `needs_review`: analysis and validation are available.
- `approved`: a professional accepted the prepared result.
- `rejected`: a professional rejected the prepared result.
- `analysis_failed`: the model request or schema validation failed.

Only the application layer may transition case state.

## Failure behavior

- Invalid input returns a typed validation error.
- Model refusal is recorded and displayed without fabrication.
- Model timeout or API failure moves the case to `analysis_failed`.
- Follow-up timeout, refusal, or provider failure leaves the case in
  `needs_review`, completes the run with a sanitized outcome, and stores no
  draft.
- Invalid structured output is rejected and never partially persisted as a
  successful analysis.
- Deterministic blocking findings prevent approval.
- Failed audit persistence fails the associated state-changing operation.
- Unique per-case draft and decision constraints, a single active follow-up
  attempt, and draft optimistic concurrency prevent duplicates and lost edits.

## Security and privacy baseline

- `OPENAI_API_KEY` exists only in backend environment configuration.
- `.env` files are excluded from Git.
- API calls use `store=false`.
- Logs use case IDs instead of client identities.
- Demonstration fixtures are synthetic and visibly marked.
- The frontend renders model output as untrusted content.
- No official portal credentials or integrations are present.
- No generated output is represented as professional advice.

## Repository structure

```text
apps/
  api/
    alembic/
    app/
      api/
      application/
      domain/
      infrastructure/
      integrations/openai/
    tests/
  web/
    app/
    components/
    lib/
    tests/
docs/
  architecture/
  hackathon/
  product/
  adr/
```

## Verification strategy

- Unit tests for domain state transitions.
- Unit tests for deterministic validators and checklists.
- Contract tests for structured model schemas.
- Integration tests for repository and API behavior.
- Recorded synthetic fixtures for offline tests.
- A small, explicitly marked live GPT-5.6 test suite.
- End-to-end tests for the three demonstration scenarios.

## Deferred decisions

The following are intentionally deferred until after the hackathon:

- PostgreSQL migration;
- multi-tenancy;
- production identity and access management;
- real document ingestion and OCR;
- public-sector integrations;
- queues and background workers;
- production hosting topology;
- billing and subscription management.

## Official OpenAI references

- Responses API:
  https://developers.openai.com/api/docs/guides/migrate-to-responses
- Structured Outputs:
  https://developers.openai.com/api/docs/guides/structured-outputs
- Data controls:
  https://developers.openai.com/api/docs/guides/your-data
