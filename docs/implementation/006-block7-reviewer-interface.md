# Block 7 Reviewer Interface

## Objective

Deliver one responsive Next.js reviewer interface that completes the three
approved synthetic procedures in Spanish or Galician while preserving the
trust boundary between source data, model-derived analysis, deterministic
validation, and human-reviewed output.

Block 7 includes only the provider-free read contracts required to reconstruct
an existing review after a reload. It does not change analysis, validation,
drafting, or decision behavior.

## Reviewer surfaces

### Case queue

- List cases in stable API order with reference, procedure, language, status,
  and updated time.
- Distinguish loading, empty, and typed-error states.
- Link every row to the same case workspace.

### Synthetic intake

- Create one synthetic case with a bounded reference, one or more source
  messages, optional synthetic document metadata, one of the three supported
  procedures, and Spanish or Galician output.
- Mark the form and resulting records visibly as synthetic.
- Reject undeclared real-data, OCR, file-upload, and new-procedure behavior.

### Case workspace

The workspace uses four visibly independent regions:

1. Source information: case metadata, source messages, and document metadata.
2. Model-derived analysis: procedure rationale, facts with provenance status,
   assumptions, unresolved questions, contradictions, prompt version, and
   model-run reference.
3. Deterministic validation: template and completion metadata, checklist,
   findings, and a prominent blocking summary.
4. Human-reviewed output: immutable model text, editable reviewed text,
   optimistic version, reviewer label, approval, and rejection with a required
   reason.

The audit timeline remains a fifth supporting region and presents stable API
order. Events sharing a timestamp are not described as causally ordered.

## Workflow

The case status determines the next available action:

- `draft`: run analysis.
- `analyzing`: disable duplicate analysis and refresh the case.
- `analysis_failed`: display the typed failure and permit the existing retry.
- `analyzed`: run deterministic validation.
- `needs_review`: generate or retrieve the follow-up, edit it, and make a human
  decision.
- `approved` or `rejected`: render the immutable final decision and disable
  editing and new decisions.

Approval is disabled visually when the persisted validation contains a
blocking finding. The API remains authoritative and a concurrent
`approval_blocked_by_findings` response is rendered as a blocking conflict.
Rejection keeps its reason field required in both client validation and the
backend contract.

## Read contracts added for Block 7

All reads are provider-free and use the existing typed error envelope.

- `GET /cases/{case_id}/analysis` returns the persisted
  `IntakeAnalysisResponse`, or `404 analysis_not_found`.
- `GET /cases/{case_id}/validation-result` returns persisted case validation
  metadata, checklist items, findings, and `has_blocking_findings`, or
  `404 validation_result_not_found`.
- `GET /cases/{case_id}/review-decision` returns the immutable
  `ReviewDecisionResponse`, or `404 review_decision_not_found`.

Each endpoint returns `404 case_not_found` when the case itself is absent.
The three artifact-specific 404 codes are expected empty states in the
workspace, not fatal page errors.

## Browser and environment boundary

The browser calls only same-origin Next.js route handlers. The route handlers
proxy the bounded Expediente Cero API surface using the server-only
`EXPEDIENTE_CERO_API_BASE_URL`, which defaults to `http://127.0.0.1:8000` for
local development. `OPENAI_API_KEY` remains an API-only setting and is never
referenced by `apps/web`, included in a public environment variable, or sent to
the browser.

## State and error strategy

- Initial queue and workspace reads use explicit loading and empty views.
- Each mutation owns an independent busy state and disables duplicate submits.
- `request_validation_error`, `domain_error`, and bounded input errors are
  presented beside the affected form.
- Provider refusal is labeled as refusal, never as an empty successful output.
- Timeouts and provider failures offer an explicit retry when the backend state
  permits it.
- `follow_up_generation_in_progress` instructs the reviewer to refresh before
  retrying.
- `follow_up_version_conflict` preserves the local text, refreshes the server
  version on request, and requires a deliberate resubmission.
- State and decision conflicts refresh the workspace and keep the backend as
  the source of truth.
- Unknown and persistence failures use a generic sanitized message while
  retaining the typed code for support.

## Accessibility and responsive behavior

- Semantic headings, landmarks, labels, tables, lists, and status messages.
- Keyboard-operable controls with visible focus treatment.
- `aria-live` status/error announcements and programmatic field errors.
- Color never acts as the only status or severity signal.
- Desktop uses a queue/workspace layout; narrow viewports stack regions and
  keep primary actions reachable without horizontal scrolling.
- Model and source text render as plain untrusted text, never injected HTML.

## Verification

- Vitest and Testing Library cover rendering, action gating, rejection reason,
  blocking approval, typed errors, refusal, and optimistic edit conflicts.
- HTTP-client tests cover successful decoding, the typed error envelope, the
  same-origin proxy boundary, and all Block 7 read contracts.
- Playwright covers the three synthetic procedures through the same interface,
  with Spanish and Galician represented across the scenarios.
- API integration tests cover present and absent analysis, validation, and
  decision records without resolving OpenAI.
- `npm run check` runs TypeScript, ESLint, unit/integration tests, and the
  production build. `make check` continues to enforce the API gate.

## Acceptance criteria

1. A reviewer can create and reopen any of the three synthetic scenarios.
2. Reloading a case reconstructs all persisted workflow regions.
3. Source, model, deterministic, and human-reviewed evidence are never merged
   into one unlabeled representation.
4. Spanish and Galician are selectable at intake and displayed from persisted
   case/draft data.
5. A reviewer can generate, edit, approve, or reject when backend invariants
   permit it; rejection requires a reason and blocking findings prevent
   approval in both UI and API.
6. Loading, empty, typed error, refusal, and concurrency conflict states are
   visible and recoverable where the backend permits recovery.
7. The timeline remains available after terminal decisions.
8. No browser request targets OpenAI and no OpenAI credential enters the web
   build or browser runtime.
9. Component, HTTP integration, API integration, and three-scenario E2E tests
   pass with no live model call.

## Exclusions

Authentication, OCR, real data, official submission, legal or eligibility
research, calculations, agents, tools, function calling, web search, queues,
new procedures, deployment, and Block 8 remain excluded.
