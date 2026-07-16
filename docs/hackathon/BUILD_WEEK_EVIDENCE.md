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
| Product and architecture baseline | `584908a`, PRs #1–#2, ADR-001–003 |
| Block 0 — API bootstrap | PR #3, merge `d7ed8f0` |
| Block 1 — domain kernel | PR #4, merge `d2de70a` |
| Block 2 — persistence and audit | PR #5, merge `eb4999d` |
| Block 3 — intake HTTP workflow | PR #6, merge `0c0fbc3` |
| Block 4 — structured model analysis | PR #7, merge `b3acdd3` |
| Block 5 — deterministic validation | PR #8, merge `3dfd540` |
| Block 6 — drafting and human decisions | PR #9, merge `57c087b`; coverage gate PR #10, `ec3e85b` |
| Block 7 — reviewer interface | PR #11, merge `8fde464`; API CI and Web CI passed |
| Block 8 — demo hardening | Pending PR and merge commit |

## Current verification evidence

- API: Ruff, strict mypy over 41 source files, 228 tests, and 96.21% coverage in
  the Block 8 rehearsal.
- Web: ESLint, TypeScript, production build, 17 component/integration tests,
  91.57% statement coverage, and responsive desktop/mobile E2E.
- `make rehearse-demo` passed API, web, temporary seed/reset, three canonical
  draft fixtures, and both E2E viewport projects without a live model call.
- OpenAI integration tests verify strict schema parsing, refusal/failure
  handling, `store=false`, and separated analyzer/drafter adapters without
  placing credentials in normal CI.

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
| Screenshots | Pending human capture | `docs/hackathon/screenshots/` |
| Demo web URL | Pending deployment | — |
| Demo API URL | Pending deployment | — |
| Video URL | Pending human recording/upload | — |
| Submission URL | Pending human submission | — |
| Final `/feedback` Session ID | Pending human action | — |

## Evidence policy

- Claims must be supported by commits, tests, screenshots, or session records.
- Codex assistance must not be represented as autonomous authorship.
- Human product, safety, and engineering decisions must be identified.
- No credentials, API keys, personal data, or private prompts are recorded here.
