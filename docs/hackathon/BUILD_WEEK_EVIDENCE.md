# OpenAI Build Week Evidence

## Project status

Expediente Cero is a new project created during OpenAI Build Week 2026.

## Baseline

- Initial commit: `584908a`
- Baseline tag: `build-week-start`
- Initial branch: `main`

## Required evidence

This document will be updated throughout the project with:

- dated milestones and commit references;
- Codex sessions used for core functionality;
- the final `/feedback` Codex Session ID;
- product and engineering decisions made by the author;
- areas where Codex accelerated implementation;
- specific uses of GPT-5.6 in the running product;
- testing and validation evidence;
- demo and submission links.

## Milestone ledger

| Milestone | Evidence |
| --- | --- |
| Product and architecture baseline | `584908a`, PRs #1–#2, ADR-001–002 |
| Block 0 — API bootstrap | PR #3, merge `d7ed8f0` |
| Block 1 — domain kernel | PR #4, merge `d2de70a` |
| Block 2 — persistence and audit | PR #5, merge `eb4999d` |
| Block 3 — intake HTTP workflow | PR #6, merge `0c0fbc3` |
| Block 4 — structured model analysis | PR #7, merge `b3acdd3` |
| Block 5 — deterministic validation | PR #8, merge `3dfd540` |
| Block 6 — drafting and human decisions | PR #9, merge `57c087b`; coverage gate PR #10, `ec3e85b` |
| Block 7 — reviewer interface | PR #11, merge `8fde464`; API CI and Web CI passed |
| Block 8 — demo hardening | PR #12, merge `dd261bd` |
| Render SQLite startup and migration correction | PR #13, merge `4e240262` |
| Installed-wheel migration correction | PR #14, merge `f658ee1d` |
| Bounded Galician structured-analysis correction | PR #15, merge `4e9b20e`; `intake-analysis-v3`; API CI and Web CI passed |

## Current verification evidence

- API: Ruff passed; strict mypy passed over 41 source files; 231 tests passed;
  API coverage is 96.14%.
- Web: lint and typecheck passed; 17 tests passed; the production build passed.
- API CI and Web CI passed on PR #15.
- `make rehearse-demo` passed API, web, temporary seed/reset, three canonical
  draft fixtures, and both E2E viewport projects without a live model call.
- OpenAI integration tests verify strict schema parsing, refusal/failure
  handling, `store=false`, and separated analyzer/drafter adapters without
  placing credentials in normal CI.

## Deployment and HTTP verification

- Web: <https://expediente-cero-web.onrender.com/>
- API: <https://expediente-cero-api.onrender.com>
- Readiness: <https://expediente-cero-api.onrender.com/ready>
- The readiness endpoint returned HTTP 200 with body
  `{"status":"ok","service":"expediente-cero-api","version":"0.1.0"}`.
- The web endpoint returned HTTP 200 with content type
  `text/html; charset=utf-8`.

## Live synthetic verification

- `EC-DEMO-001`: structured analysis and follow-up in Spanish; deterministic
  validation remained blocking; the human edit was persisted as version 2;
  human reviewer `Gelo S. — Build Week` rejected the case with the mandatory
  reason recorded. The case showed 12 audit events.
- `EC-DEMO-002`: two historical analysis attempts ended in
  `no_structured_output`. After PR #15, the case recovered with
  `intake-analysis-v3`: `requested_start_date` and `contract_start_date` were
  preserved as separate facts and no model contradiction was reported.
  Deterministic validation produced 6 blocking findings for incomplete
  year/date formatting and the absent employee name. The follow-up was
  generated in Galician. The case showed 9 audit events. It did not produce
  `employment_start_date_mismatch`, because the supplied dates did not include
  a year.
- `EC-DEMO-003`: structured analysis in Spanish and a partial checklist;
  deterministic validation produced 7 blocking findings. No eligibility claim
  was made.
- Responses API calls use `store=false`; consequently, the call contents are
  not available in OpenAI Logs.

## Human decisions and Codex contribution

- The human owner chose the three procedures, synthetic-only boundary,
  mandatory human decisions, Spanish/Galician support, and the exclusion of
  filing, advice, calculations, legislative search, and autonomous approval.
- Codex assisted with implementation, tests, documentation, and review under
  those product and safety decisions. It is not represented as autonomous
  authorship or as the final reviewer.

## Submission artifacts

| Artifact | Status | Evidence |
| --- | --- | --- |
| Demo runbook | Complete | `docs/demo/008-demo-runbook.md` |
| Security/privacy review | Complete | `docs/security/009-demo-security-review.md` |
| Screenshots | Complete | 13 individual captures listed below |
| Demo web URL | Complete | <https://expediente-cero-web.onrender.com/> |
| Demo API URL | Complete | <https://expediente-cero-api.onrender.com> |
| Readiness URL | Complete | <https://expediente-cero-api.onrender.com/ready> |
| Video URL | Pending human recording/upload | — |
| Submission URL | Pending human submission | — |
| Final `/feedback` Session ID | Pending human action | — |

## Screenshots

1. [Desktop case queue](screenshots/01-queue-desktop.png)
2. [Mobile case queue](screenshots/02-queue-mobile.png)
3. [Spanish structured analysis](screenshots/03-spanish-structured-analysis.png)
4. [Spanish deterministic blocking validation](screenshots/04-spanish-deterministic-blocking.png)
5. [Spanish follow-up with approval blocked](screenshots/05-spanish-follow-up-approval-blocked.png)
6. [Spanish human edit version 2](screenshots/06-spanish-human-edit-version-2.png)
7. [Spanish human rejection](screenshots/07-spanish-human-rejection.png)
8. [Galician analysis with intake-analysis-v3](screenshots/08-galician-analysis-v3.png)
9. [Galician deterministic validation](screenshots/09-galician-deterministic-validation.png)
10. [Galician follow-up](screenshots/10-galician-follow-up.png)
11. [Grant partial checklist](screenshots/11-grant-partial-checklist.png)
12. [Mobile reviewer workspace](screenshots/12-mobile-reviewer-workspace.png)
13. [Typed no_structured_output failure](screenshots/13-typed-no-structured-output.png)

## Evidence policy

- Claims must be supported by commits, tests, screenshots, or session records.
- Codex assistance must not be represented as autonomous authorship.
- Human product, safety, and engineering decisions must be identified.
- No credentials, API keys, personal data, or private prompts are recorded here.
