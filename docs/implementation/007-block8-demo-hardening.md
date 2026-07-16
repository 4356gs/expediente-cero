# Block 8 Demo Hardening and Submission

## Objective

Turn the merged synthetic MVP into a reproducible, reviewable Build Week demo
without adding product capabilities. Block 8 hardens operations, evidence, and
delivery only; Blocks 0–7 remain the product boundary.

## Canonical decisions

- The primary recorded demonstration uses the configured live GPT-5.6 adapters.
- Automated tests and failure rehearsal remain deterministic and make no live
  model call.
- Exactly three canonical intake fixtures are seeded in `draft`, one per
  accepted procedure, with Spanish and Galician represented.
- Seed is idempotent. Reset rebuilds the configured SQLite schema and reseeds
  it only when `EXPEDIENTE_CERO_ENVIRONMENT=demo` and the caller supplies the
  exact confirmation `RESET-DEMO-DATA`.
- Reset is a CLI operation, never a browser or public API endpoint.
- The reference deployment is a Render Blueprint with separate FastAPI and
  Next.js web services in Frankfurt. The API uses a paid persistent disk for
  SQLite; secrets are entered in Render and never committed.
- Free Render web services are not the reference deployment because their
  filesystem is ephemeral and they can spin down while the demo is idle.
- Submission URLs, the final video, and the final `/feedback` Session ID are
  human-provided evidence and must never be fabricated.

## Deliverables

### Demo data lifecycle

- `expediente-cero-demo seed`: migrate and add missing canonical fixtures.
- `expediente-cero-demo status`: report canonical fixture states as JSON.
- `expediente-cero-demo reset --confirm RESET-DEMO-DATA`: rebuild and reseed a
  database explicitly configured for the demo environment.
- Integration tests prove the environment guard, exact confirmation,
  idempotency, deterministic identities, and reset behavior.

### Rehearsal

- One clean-machine runbook with pinned prerequisites and commands.
- One command that executes API quality, web quality, deterministic E2E, and a
  temporary demo database seed/reset rehearsal.
- A failure-path checklist covering refusal, unavailable provider, blocking
  validation, required rejection reason, optimistic edit conflict, and API
  unavailability without weakening production invariants.

### Visible safety boundary

- Every page identifies the environment as synthetic.
- Intake warns against real names, documents, and personal data.
- The reviewer workspace and footer state that output is preparatory, requires
  human review, is not professional advice, and is not submitted to an agency.
- Source, model-derived, deterministic, and human-reviewed evidence remain
  visually distinct.

### Evidence and submission

- The evidence ledger maps each claim to a commit, test, screenshot, session,
  or running URL.
- The shot list covers queue, intake, all four evidence regions, blocking
  approval, rejection reason, refusal/conflict state, and audit timeline.
- The demo script fits a short recorded walkthrough and includes a fallback to
  already persisted synthetic cases if the live provider is unavailable.
- Placeholders are explicit for the deployed URLs, video, submission, and
  `/feedback` Session ID.

## Deployment contract

- API health check: `/ready`.
- API binds to `0.0.0.0:$PORT` and runs migrations plus idempotent seed before
  serving.
- SQLite lives on the API persistent disk; a single API instance is required.
- Next.js runs as a server-rendered web service and calls the API only through
  its server-side same-origin proxy.
- `OPENAI_API_KEY` is a dashboard secret. The browser build receives no OpenAI
  credential and no public API base variable.
- API docs are disabled in the public demo.

## Acceptance criteria

1. A blank demo database migrates and receives exactly three canonical cases.
2. Repeated seed is a no-op and reset is impossible outside `demo` or without
   the exact confirmation.
3. API, web, E2E, and demo lifecycle rehearsal pass from documented commands.
4. The UI visibly communicates synthetic-only, no-advice, human-review, and
   no-submission boundaries.
5. The Render Blueprint contains no secret and preserves SQLite on a disk.
6. Every completed submission claim has evidence; unavailable human artifacts
   remain labeled pending rather than implied complete.
7. No authentication, OCR, real data, agency filing, calculation, legal
   retrieval, agents, tools, queues, new procedures, or Block 9 work is added.

## External completion gate

Block 8 can be merged when the repository deliverables and deterministic gates
pass. Final submission completion additionally requires a human to provide the
deployed URLs, record and upload the video, submit the entry, run `/feedback`,
and record those resulting links and identifiers in the evidence ledger.
