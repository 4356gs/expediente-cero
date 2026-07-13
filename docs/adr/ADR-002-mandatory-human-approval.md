# ADR-002: Require Human Approval for Prepared Cases

- Status: Accepted
- Date: 2026-07-13

## Context

The product handles administrative intake that may precede tax, employment,
accounting, or grant work. Model output may be incomplete or incorrect, and the
MVP is not a professional advisory or filing system.

## Decision

Every prepared case requires an explicit human decision.

- GPT-5.6 may extract, classify, identify ambiguity, and draft text.
- Deterministic code calculates checklist status and blocking findings.
- Only a human reviewer may approve or reject the prepared case.
- Approval is technically blocked while deterministic blocking findings exist.
- Rejection requires a reason.
- Human edits, decisions, and timestamps are retained in the audit trail.
- No integration submits information to a public authority.

The interface must visually separate:

1. source information;
2. model-derived analysis;
3. deterministic validation;
4. human-reviewed output.

## Consequences

Positive:

- professional control remains explicit;
- failures are easier to detect and audit;
- the product avoids presenting generated text as authoritative advice;
- the demonstration has a clear and credible safety boundary.

Negative:

- the workflow cannot be fully autonomous;
- reviewer effort remains necessary;
- state transitions and audit persistence require additional implementation.

## Rejected alternatives

- Automatic approval above a confidence threshold: model confidence is not a
  guarantee of professional correctness.
- Warning-only review: insufficient control for high-impact administrative
  preparation.
- Direct filing integrations: outside scope and unsuitable for synthetic demo
  data.
