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

The MVP uses one model call for structured intake analysis and one model call
for the follow-up draft. It does not implement an autonomous agent loop.

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
- Invalid structured output is rejected and never partially persisted as a
  successful analysis.
- Deterministic blocking findings prevent approval.
- Failed audit persistence fails the associated state-changing operation.

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
