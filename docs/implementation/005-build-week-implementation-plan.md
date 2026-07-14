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

- Separate bounded Spanish/Galician follow-up draft call.
- Immutable model text plus editable reviewed text.
- Approve/reject use cases; rejection reason and approval blockers enforced.
- Complete audit timeline.

Exit gate: both languages are demonstrated; only a human action can produce a
terminal state.

### Block 7 — Reviewer interface

- Next.js interface for case intake, four-way evidence separation, draft edit,
  review decision, and audit timeline.
- No direct browser-to-OpenAI traffic.

Exit gate: the same interface completes all three synthetic scenarios.

### Block 8 — Demo hardening and submission

- End-to-end tests, failure-path rehearsal, seed/reset command, and demo script.
- Security/privacy review and visible synthetic-data/advice boundaries.
- Build Week evidence, screenshots, video, deployment, and submission links.

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
