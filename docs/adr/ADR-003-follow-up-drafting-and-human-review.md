# ADR-003: Separate Follow-up Drafting from Human Review

- Status: Accepted
- Date: 2026-07-15

## Context

After deterministic validation, a case in `needs_review` needs a bounded
Spanish or Galician message that asks for the missing or contradictory intake
information. Draft generation and the final review decision have different
trust boundaries: generation is model-assisted, while approval or rejection is
an exclusively human action. The workflow must tolerate retries and concurrent
requests without losing edits, duplicating records, or hiding model failures.

The follow-up call also needs a narrower input boundary than intake analysis.
It must not recover information from external sources or silently reinterpret
request parameters as case configuration.

## Decision

### Generation boundary

Introduce `FollowUpDrafter` as an application port independent of
`IntakeAnalyzer`. Generation is a separate, synchronous, bounded call made only
after deterministic validation has completed and while the case remains in
`needs_review`; no `drafting` case state is introduced.

The drafter receives only the already persisted case, synthetic intake,
synthetic document metadata, intake analysis, checklist results, and validation
findings. It uses the persisted `OutputLanguage`; callers cannot override the
language in the generation request.

The OpenAI adapter uses the Responses API, strict Structured Outputs,
`store=false`, and the existing configurable model. The initial prompt version
is `follow-up-draft-v1`; it requests at most `1200` output tokens. Validated
`model_text` is between 1 and 4000 characters. Empty or oversized structured
output is treated as `no_structured_output` and no successful draft is stored.
The request uses no agents, tools, function calling,
web search, or external legislative knowledge.

Each follow-up attempt has a configurable lease. The effective setting is
`EXPEDIENTE_CERO_FOLLOW_UP_ATTEMPT_LEASE_SECONDS`, defaults to `300`, and has no
additional alias. `Settings` construction validates that
`follow_up_attempt_lease_seconds > openai_timeout_seconds`; invalid
configuration prevents application startup. `follow_up_configuration_error`
is reserved for configuration or dependency failures encountered when a new
generation actually resolves the provider.

`started_at`, the derived `expires_at`, and the claim clock use UTC. Timestamps
loaded from SQLite are restored as UTC before comparison. The exact expiry rule
is:

```text
expired = now_utc >= started_at_utc + lease_seconds
```

### Draft and review records

Each case has at most one `FollowUpDraft`. Its 1-to-4000-character `model_text`
is immutable and its editable, trimmed 1-to-4000-character `reviewed_text`
initially equals `model_text`. In the MVP, `model_text` immutability is enforced
by the domain, application, repository, and HTTP contracts; direct
administrative database writes are outside scope, so no SQLite trigger is
added. A monotonically
increasing `version` provides optimistic concurrency for edits.

Each case has at most one immutable `ReviewDecision`. Approval and rejection
require a persisted draft and a human actor. Rejection requires a non-blank
human reason. Approval is forbidden while any deterministic `blocking` finding
is active. The only terminal Block 6 transitions remain
`needs_review -> approved` and `needs_review -> rejected`.

Before validation or idempotency comparison, external whitespace is trimmed
from `reviewer_label`, `reason`, and `reviewed_text`. `reviewer_label` remains
required and is compared case-sensitively. A rejection with a null, empty, or
whitespace-only reason returns `rejection_reason_required`. For approval, an
omitted, null, or whitespace-only reason normalizes to null; a non-empty reason
returns the existing `request_validation_error`. Trimmed `reviewed_text` must
remain non-empty.

### Atomicity and idempotency

- Generation start atomically rechecks `needs_review`, completed validation,
  absence of a draft, and absence of an in-progress follow-up run, then creates
  a `ModelRun` with status `in_progress` and the
  `follow_up_generation_started` event.
- Generation success completes the run and persists the draft and
  `follow_up_draft_created` event in one transaction.
- Failure or refusal completes the run and persists the corresponding
  `follow_up_generation_failed` or `follow_up_generation_refused` event in one
  transaction, without a draft. A later request may create a new run.
- A generation request after success returns the existing draft without a new
  model call or audit event. If an `in_progress` follow-up run has an unexpired
  lease, the request returns `follow_up_generation_in_progress`.
- Error precedence is case existence, existing-draft idempotency, persisted
  state/analysis/validation, and active-attempt detection. Only after those
  checks does a new attempt resolve OpenAI; therefore missing provider
  configuration cannot hide a 404, state conflict, existing draft, or active
  attempt.
- If the lease has expired, the next request atomically rechecks that the run is
  still `in_progress` and expired, marks it `failed` with
  `sanitized_error_code=follow_up_attempt_abandoned`, appends
  `follow_up_generation_failed`, and creates a new `in_progress` run with its
  `follow_up_generation_started` event. The case remains in `needs_review`.
  Only one concurrent request can claim the expired run; other contenders see
  the replacement active run and return `follow_up_generation_in_progress`.
- SQLite enforces one `follow_up_draft`/`in_progress` run per case with a partial
  unique index. Recovery uses a conditional update and requires exactly one
  claimed row. Marking the abandoned run, its failure event, the replacement
  run, and its start event occur in one transaction; the unique index protects
  the residual race.
- Editing compares `expected_version`, changes only `reviewed_text`, increments
  the version, and appends `follow_up_draft_edited` in one transaction. An
  identical text is a no-op and returns the current draft without incrementing
  its version or appending an event.
- A decision request is normalized first and then looks up the immutable
  decision for the case. The same decision value, normalized reason, and
  case-sensitive normalized human actor returns that record even though the
  case is already terminal; any semantically different payload returns
  `review_decision_conflict`.
- Only when no decision exists does the use case require `needs_review`, then
  recheck draft existence, actor type, and approval blockers before persisting
  the decision, case transition, the `review_approved` or `review_rejected`
  event, and `case_status_changed` in one transaction. Both events share the
  operational timestamp. Neither has causal priority when their timestamps are
  equal; presentation remains stable by `recorded_at` and then event ID.
- Unique constraints on draft and decision `case_id`, the single active
  follow-up-run rule, and optimistic concurrency prevent duplicate drafts,
  decisions, and lost edits.

Audit metadata is sanitized. It may contain case, draft, decision, and model-run
IDs; purpose, language, model, prompt version, draft versions, prior and new
states, bounded error code, and lease expiry. It never contains `model_text`,
`reviewed_text`, the complete human reason, prompts, secrets, or hidden
reasoning.

Persistence conflicts have stable mappings: the active-run partial index maps
to `follow_up_generation_in_progress`; an optimistic draft update affecting no
row maps to `follow_up_version_conflict`; a unique-decision conflict triggers a
reread followed by idempotent return or `review_decision_conflict`; a
conditional terminal transition affecting no row maps to
`follow_up_state_conflict`; blocking findings map to
`approval_blocked_by_findings`; and all other database failures map to the
corresponding follow-up or review persistence error.

## Consequences

Positive:

- intake analysis and drafting can evolve and be faked independently;
- persisted data is the complete and reproducible drafting boundary;
- case status continues to describe business review state rather than a
  transient provider operation;
- retries and concurrent requests have explicit behavior;
- original model output and the human-edited result remain distinguishable;
- only a human can create a terminal decision.

Negative:

- generation requires a two-transaction lifecycle around an external call;
- generation recovery adds lease configuration and an atomic claim path;
- optimistic concurrency and idempotency add repository and HTTP complexity;
- synchronous generation occupies an API request until its configured timeout.

## Rejected alternatives

- Reuse `IntakeAnalyzer`: combines different schemas, prompts, inputs, and
  failure semantics behind one port.
- Generate during validation: couples deterministic work to a provider call and
  prevents independent retries.
- Add a `drafting` case state: exposes a transient technical operation as a
  business lifecycle state and complicates terminal transition rules.
- Accept language in the generation request: permits drift from the persisted
  case configuration.
- Overwrite model text on edit: destroys provenance.
- Let the model approve or reject: violates the mandatory human-review boundary.
- Use agents, tools, retrieval, or legislative search: unnecessary and outside
  the bounded synthetic MVP.
