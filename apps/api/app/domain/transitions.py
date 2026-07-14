"""Pure policy for auditable case-state transitions."""

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.entities import AuditEvent, Case, ReviewDecision
from app.domain.enums import (
    ActorType,
    AuditEventType,
    CaseStatus,
    ReviewDecisionType,
)
from app.domain.errors import DomainInvariantError, InvalidTransitionError

ALLOWED_TRANSITIONS: frozenset[tuple[CaseStatus, CaseStatus]] = frozenset(
    {
        (CaseStatus.DRAFT, CaseStatus.ANALYZING),
        (CaseStatus.ANALYZING, CaseStatus.NEEDS_REVIEW),
        (CaseStatus.ANALYZING, CaseStatus.ANALYSIS_FAILED),
        (CaseStatus.ANALYSIS_FAILED, CaseStatus.ANALYZING),
        (CaseStatus.NEEDS_REVIEW, CaseStatus.ANALYZING),
        (CaseStatus.NEEDS_REVIEW, CaseStatus.APPROVED),
        (CaseStatus.NEEDS_REVIEW, CaseStatus.REJECTED),
    }
)


@dataclass(frozen=True, slots=True)
class TransitionOutcome:
    """State change and its mandatory audit event, returned as one value."""

    case: Case
    audit_event: AuditEvent


def transition_case(
    case: Case,
    target: CaseStatus,
    *,
    actor_type: ActorType,
    actor_label: str,
    occurred_at: datetime,
    reason: str | None = None,
    audit_event_id: UUID | None = None,
    decision_id: UUID | None = None,
) -> TransitionOutcome:
    """Apply one permitted transition and produce its inseparable audit event."""
    if (case.status, target) not in ALLOWED_TRANSITIONS:
        raise InvalidTransitionError(f"transition {case.status} -> {target} is not allowed")
    if actor_type is ActorType.MODEL:
        raise DomainInvariantError("model output cannot directly transition a case")
    if occurred_at < case.updated_at:
        raise DomainInvariantError("transition timestamp cannot precede the current case state")

    review_decision: ReviewDecision | None = None
    if target in {CaseStatus.APPROVED, CaseStatus.REJECTED}:
        if actor_type is not ActorType.USER:
            raise DomainInvariantError("terminal decisions require a human reviewer")
        if target is CaseStatus.APPROVED:
            if case.has_blocking_findings:
                raise DomainInvariantError("approval is blocked by active findings")
            decision = ReviewDecisionType.APPROVED
        else:
            decision = ReviewDecisionType.REJECTED
        review_decision = ReviewDecision(
            id=decision_id or uuid4(),
            case_id=case.id,
            decision=decision,
            reason=reason,
            reviewer_label=actor_label,
            created_at=occurred_at,
        )

    transitioned_case = replace(
        case,
        status=target,
        updated_at=occurred_at,
        review_decision=review_decision,
    )
    audit_event = AuditEvent(
        id=audit_event_id or uuid4(),
        case_id=case.id,
        event_type=AuditEventType.CASE_STATUS_CHANGED,
        actor_type=actor_type,
        actor_label=actor_label,
        recorded_at=occurred_at,
        sanitized_metadata={"from_status": case.status, "to_status": target},
    )
    return TransitionOutcome(case=transitioned_case, audit_event=audit_event)
