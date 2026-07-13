# MVP Scope

## In scope

### Intake

- Create a synthetic client case.
- Enter an unstructured message.
- Select or infer one supported procedure.
- Attach synthetic document metadata.
- Select Spanish or Galician output.

### AI analysis

- Extract structured facts with GPT-5.6.
- Classify the likely procedure.
- distinguish facts, assumptions, and unresolved questions.
- Flag potential contradictions.
- Produce confidence indicators without presenting them as probabilities of
  legal correctness.

### Deterministic validation

- Validate the model response against typed schemas.
- Apply procedure-specific required-field rules.
- Apply configurable document checklists.
- Prevent approval when mandatory internal validation fails.
- Record validation results independently of the model output.

### Human review

- Display the original request and structured analysis together.
- Allow the reviewer to edit the follow-up draft.
- Approve or reject the prepared case.
- Require a reason when rejecting.
- Record reviewer action and timestamp.

### Auditability

- Record model name and prompt version.
- Record structured model output.
- Record deterministic validation results.
- Record human edits and final decision.
- Exclude secrets and raw sensitive documents from logs.

## Out of scope

- Legal, tax, accounting, or employment advice.
- Calculation of taxes, payroll, contributions, or benefits.
- Submission to AEAT, Seguridad Social, Xunta de Galicia, or other authorities.
- Authentication with public-sector systems.
- Real customer data.
- Production document storage.
- Electronic signatures.
- Payments.
- Autonomous approval or submission.
- Broad retrieval over legislation.
- More than three procedure templates.
- Multi-tenant billing and production deployment controls.

## Demo scenarios

### Scenario A — Self-employed registration

The client describes a planned activity and start date but omits required
identification or activity information. The system prepares a missing-data
request.

### Scenario B — Employee hiring

The client provides candidate and start information with an inconsistent date.
The system flags the contradiction and blocks approval until reviewed.

### Scenario C — Grant application

The client asks about applying for a grant and provides partial company
information. The system structures the request and prepares a checklist without
claiming eligibility.

## Acceptance boundary

The MVP is complete only when all three scenarios can be demonstrated through
the same end-to-end interface using synthetic fixtures.
