# Demo Runbook

## Purpose

Rehearse and present the three synthetic Expediente Cero scenarios without
introducing real data, autonomous decisions, or unverified submission claims.

## Clean-machine prerequisites

- Linux or WSL 2.
- Python 3.12 or 3.13.
- Node.js 24 and npm.
- Git.
- An OpenAI API key only for the explicitly live walkthrough.

## Deterministic rehearsal

From a clean checkout:

```text
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
npm --prefix apps/web ci
make rehearse-demo
```

The rehearsal must finish with API checks, 3 seeded draft cases, web checks,
and desktop/mobile E2E. It does not call OpenAI.

## Local live walkthrough

Use a dedicated demo database and never a retained development database:

```text
export EXPEDIENTE_CERO_ENVIRONMENT=demo
export EXPEDIENTE_CERO_DATABASE_URL=sqlite:///./data/expediente-cero-demo.db
export OPENAI_API_KEY=<set outside shell history when possible>
make demo-reset
make demo-status
make run-api
```

In a second terminal:

```text
make run-web
```

Never record or paste the key. Confirm that the queue contains exactly
`EC-DEMO-001`, `EC-DEMO-002`, and `EC-DEMO-003` before recording.

## Recorded walkthrough

1. Show the persistent synthetic-only and no-advice boundary.
2. Open `EC-DEMO-001`; run analysis and deterministic validation.
3. Generate the Spanish follow-up and identify immutable model text versus the
   editable reviewed text.
4. Show that a blocking finding disables approval. Reject with a human label
   and a required reason.
5. Open `EC-DEMO-002` to show Galician and the inconsistent hiring dates.
6. Open `EC-DEMO-003` to show the partial grant checklist without an
   eligibility claim.
7. Finish on the stable audit timeline and restate that no filing occurs.

If the live provider is unavailable, stop retrying after one bounded attempt
and use already persisted synthetic results. Do not present mocked output as a
live call.

## Failure-path rehearsal

| Condition | Expected evidence |
| --- | --- |
| Provider unavailable or timeout | Typed error, retry only from an allowed state |
| Provider refusal | Refusal is labeled and no draft is stored |
| Blocking deterministic finding | Approval is visibly and functionally disabled |
| Rejection without reason | Reject action remains unavailable; API also rejects it |
| Concurrent draft edit | Local text is preserved and version conflict is explicit |
| API unavailable | Sanitized `api_unavailable` state with no upstream details |

Use automated tests for deterministic failure evidence. A recording does not
need to manufacture every failure.

## Render deployment

1. Create a Render Blueprint from `render.yaml`.
2. Confirm both services use the Frankfurt region and `starter` plan.
3. Enter `OPENAI_API_KEY` only when Render prompts for the unsynced secret.
4. Confirm the API has a 1 GB disk mounted at
   `/var/data/expediente-cero` and exactly one instance.
5. Wait for `/ready` and the web root health checks.
6. Open the web URL, verify the three seeded cases, and record both deployed
   URLs in the evidence ledger.

Render free services are not equivalent to this reference deployment: they do
not support persistent disks and can lose SQLite data or cold-start during a
demo. Delete the services or scale them down after judging if ongoing cost is
not intended.

## Screenshot shot list

- Queue with three canonical cases and synthetic boundary.
- New-case form with Spanish/Galician choices and real-data warning.
- Four evidence regions in one workspace.
- Blocking finding with disabled approval.
- Required rejection reason and human reviewer label.
- Refusal or typed conflict state from deterministic evidence.
- Final audit timeline.
- Responsive mobile workspace.

Store selected screenshots under `docs/hackathon/screenshots/` and record their
paths in `BUILD_WEEK_EVIDENCE.md`.

## Human completion checklist

- Record and upload the video.
- Add deployed API and web URLs.
- Run `/feedback` and record the final Session ID.
- Add the submission URL and timestamp.
- Verify that no screenshot, video, log, or document contains a secret or real
  personal data.
