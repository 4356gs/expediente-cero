# ADR-001: Use Responses API with Structured Outputs

- Status: Accepted
- Date: 2026-07-13

## Context

Expediente Cero must turn an unstructured synthetic request into typed data that
can be validated and displayed. Free-form JSON would require fragile parsing
and could omit required fields or invent unsupported enum values.

The integration must also make the use of GPT-5.6 explicit for OpenAI Build
Week while keeping provider details outside the domain layer.

## Decision

Use GPT-5.6 through the OpenAI Responses API behind an `IntakeAnalyzer`
interface.

For intake analysis:

- define the response schema with Pydantic;
- request Structured Outputs in strict mode;
- reject outputs that cannot be parsed into the schema;
- set `store=false` on API requests;
- record model name, prompt version, request ID, timestamps, and outcome;
- keep deterministic validation outside the model call.

For follow-up drafting, use a separate bounded model request after validation.
No autonomous tool loop or multi-agent framework is introduced in the MVP.

## Consequences

Positive:

- schema-constrained output;
- simpler contract testing;
- explicit model boundary;
- easier replacement or testing with a fake analyzer;
- clear evidence of GPT-5.6 usage.

Negative:

- schemas must satisfy strict Structured Outputs requirements;
- schema changes require versioning and tests;
- live integration tests consume API credits;
- `store=false` does not by itself provide Zero Data Retention.

## Rejected alternatives

- Free-form JSON: insufficient schema guarantees.
- Chat Completions for new integration: Responses is the selected current API.
- Agents SDK: unnecessary for two bounded model calls.
- Direct SDK usage in routes: would couple HTTP, domain, and provider concerns.

## References

- https://developers.openai.com/api/docs/guides/structured-outputs
- https://developers.openai.com/api/docs/guides/migrate-to-responses
- https://developers.openai.com/api/docs/guides/your-data
