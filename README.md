# Expediente Cero

AI-assisted client intake for Galician accounting and administrative firms.

Expediente Cero converts unstructured client messages and documents into structured case files, identifies missing or contradictory information, applies configurable checklists, and drafts follow-up messages in Spanish or Galician.

## OpenAI Build Week

This project was started during OpenAI Build Week 2026 and is being built with Codex and GPT-5.6.

## Safety boundary

Expediente Cero:

- does not provide legal, tax, employment, or accounting advice;
- does not submit information to public authorities;
- uses synthetic data in its demonstration;
- requires professional review and approval before any output is used.

## Local development

The API and reviewer are separate local processes:

```text
make install
make migrate
make run-api
```

In another terminal:

```text
make install-web
make run-web
```

The reviewer defaults to `http://127.0.0.1:8000`. Copy
`apps/web/.env.example` to `apps/web/.env.local` only when a different local API
URL is required. This server-only value is proxied by Next.js; no OpenAI key is
available to the browser.

Quality commands:

```text
make check
make check-web
make test-web-e2e
```

## Demo rehearsal

The canonical Block 8 scope and safety gates are documented in
`docs/implementation/007-block8-demo-hardening.md`. From an installed checkout,
the deterministic rehearsal is:

```text
make rehearse-demo
```

This runs API and web quality gates, rebuilds and seeds a temporary demo-only
SQLite database, verifies its three canonical cases, and runs desktop/mobile
E2E without a live model call. See `docs/demo/008-demo-runbook.md` before a live
GPT-5.6 walkthrough or Render deployment.

## Status

Blocks 0–7 implement the typed synthetic intake, structured model analysis,
deterministic validation, bounded follow-up drafting, mandatory human decision,
audit history, and the responsive reviewer interface. Block 8 hardening is in
progress; external demo, video, `/feedback`, and submission evidence remain
human completion gates.
