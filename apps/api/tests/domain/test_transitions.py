"""Exhaustive tests for the case transition policy."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.domain import (
    ALLOWED_TRANSITIONS,
    ActorType,
    AuditEventType,
    Case,
    CaseStatus,
    DomainInvariantError,
    FindingSeverity,
    InvalidTransitionError,
    OutputLanguage,
    ProcedureType,
    ReviewDecision,
    ReviewDecisionType,
    ValidationFinding,
    transition_case,
)

NOW = datetime(2026, 7, 13, 18, 0, tzinfo=UTC)
CASE_ID = UUID("00000000-0000-0000-0000-000000000001")


def make_case(
    status: CaseStatus, *, blocking: int = 0, prepared: bool = False, analyzed: bool = False
) -> Case:
    has_analysis = (
        prepared
        or analyzed
        or status
        in {
            CaseStatus.ANALYZED,
            CaseStatus.NEEDS_REVIEW,
            CaseStatus.APPROVED,
            CaseStatus.REJECTED,
        }
    )
    review_ready = prepared or status in {
        CaseStatus.NEEDS_REVIEW,
        CaseStatus.APPROVED,
        CaseStatus.REJECTED,
    }
    decision = None
    if status in {CaseStatus.APPROVED, CaseStatus.REJECTED}:
        decision_type = ReviewDecisionType(status.value)
        decision = ReviewDecision(
            id=uuid4(),
            case_id=CASE_ID,
            decision=decision_type,
            reason="Reason" if status is CaseStatus.REJECTED else None,
            reviewer_label="Reviewer",
            created_at=NOW,
        )
    return Case(
        id=CASE_ID,
        reference="EC-0001",
        procedure_type=ProcedureType.GRANT_APPLICATION,
        output_language=OutputLanguage.GALICIAN,
        status=status,
        created_at=NOW,
        updated_at=NOW,
        intake_analysis_id=uuid4() if has_analysis else None,
        validation_completed_at=NOW if review_ready else None,
        validation_template_version="deterministic-validation-test-v1" if review_ready else None,
        validation_findings=tuple(
            ValidationFinding(
                id=uuid4(),
                case_id=CASE_ID,
                code=f"BLOCKER_{index}",
                severity=FindingSeverity.BLOCKING,
                message="Blocking finding",
                created_at=NOW,
            )
            for index in range(blocking)
        ),
        review_decision=decision,
    )


@pytest.mark.parametrize(("source", "target"), sorted(ALLOWED_TRANSITIONS))
def test_every_allowed_transition_returns_state_and_audit_event(
    source: CaseStatus, target: CaseStatus
) -> None:
    actor = (
        ActorType.USER if target in {CaseStatus.APPROVED, CaseStatus.REJECTED} else ActorType.SYSTEM
    )
    occurred_at = NOW + timedelta(minutes=1)
    outcome = transition_case(
        make_case(
            source,
            prepared=target is CaseStatus.NEEDS_REVIEW,
            analyzed=target is CaseStatus.ANALYZED,
        ),
        target,
        actor_type=actor,
        actor_label="Reviewer" if actor is ActorType.USER else "workflow",
        occurred_at=occurred_at,
        reason="Documentación inconsistente" if target is CaseStatus.REJECTED else None,
    )

    assert outcome.case.status is target
    assert outcome.case.updated_at == occurred_at
    assert outcome.audit_event.event_type is AuditEventType.CASE_STATUS_CHANGED
    assert outcome.audit_event.case_id == CASE_ID
    assert outcome.audit_event.sanitized_metadata == {
        "from_status": source,
        "to_status": target,
    }


FORBIDDEN_TRANSITIONS = sorted(
    {
        (source, target)
        for source in CaseStatus
        for target in CaseStatus
        if (source, target) not in ALLOWED_TRANSITIONS
    }
)


@pytest.mark.parametrize(("source", "target"), FORBIDDEN_TRANSITIONS)
def test_every_other_transition_is_forbidden(source: CaseStatus, target: CaseStatus) -> None:
    with pytest.raises(InvalidTransitionError, match="is not allowed"):
        transition_case(
            make_case(source),
            target,
            actor_type=ActorType.USER,
            actor_label="Reviewer",
            occurred_at=NOW + timedelta(minutes=1),
            reason="Reason",
        )


def test_model_cannot_directly_transition_a_case() -> None:
    with pytest.raises(DomainInvariantError, match="model output cannot directly"):
        transition_case(
            make_case(CaseStatus.DRAFT),
            CaseStatus.ANALYZING,
            actor_type=ActorType.MODEL,
            actor_label="gpt-5.6",
            occurred_at=NOW + timedelta(minutes=1),
        )


def test_transition_timestamp_cannot_move_backwards() -> None:
    with pytest.raises(DomainInvariantError, match="timestamp cannot precede"):
        transition_case(
            make_case(CaseStatus.DRAFT),
            CaseStatus.ANALYZING,
            actor_type=ActorType.SYSTEM,
            actor_label="workflow",
            occurred_at=NOW - timedelta(seconds=1),
        )


@pytest.mark.parametrize("target", [CaseStatus.APPROVED, CaseStatus.REJECTED])
def test_terminal_decisions_require_a_human(target: CaseStatus) -> None:
    with pytest.raises(DomainInvariantError, match="require a human reviewer"):
        transition_case(
            make_case(CaseStatus.NEEDS_REVIEW),
            target,
            actor_type=ActorType.SYSTEM,
            actor_label="workflow",
            occurred_at=NOW + timedelta(minutes=1),
            reason="Reason",
        )


def test_blocking_findings_prevent_approval() -> None:
    with pytest.raises(DomainInvariantError, match="blocked by active findings"):
        transition_case(
            make_case(CaseStatus.NEEDS_REVIEW, blocking=1),
            CaseStatus.APPROVED,
            actor_type=ActorType.USER,
            actor_label="Reviewer",
            occurred_at=NOW + timedelta(minutes=1),
        )


def test_rejection_requires_a_human_reason() -> None:
    with pytest.raises(DomainInvariantError, match="rejection requires"):
        transition_case(
            make_case(CaseStatus.NEEDS_REVIEW),
            CaseStatus.REJECTED,
            actor_type=ActorType.USER,
            actor_label="Reviewer",
            occurred_at=NOW + timedelta(minutes=1),
            reason=" ",
        )


@pytest.mark.parametrize(
    ("target", "decision_type"),
    [
        (CaseStatus.APPROVED, ReviewDecisionType.APPROVED),
        (CaseStatus.REJECTED, ReviewDecisionType.REJECTED),
    ],
)
def test_terminal_transition_records_the_human_decision(
    target: CaseStatus, decision_type: ReviewDecisionType
) -> None:
    decision_id = uuid4()
    event_id = uuid4()
    outcome = transition_case(
        make_case(CaseStatus.NEEDS_REVIEW),
        target,
        actor_type=ActorType.USER,
        actor_label="Ana Gestora",
        occurred_at=NOW + timedelta(minutes=1),
        reason="Reason" if target is CaseStatus.REJECTED else None,
        audit_event_id=event_id,
        decision_id=decision_id,
    )

    assert outcome.case.review_decision is not None
    assert outcome.case.review_decision.id == decision_id
    assert outcome.case.review_decision.decision is decision_type
    assert outcome.case.review_decision.reviewer_label == "Ana Gestora"
    assert outcome.audit_event.id == event_id
