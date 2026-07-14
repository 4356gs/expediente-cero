"""Unit tests for framework-independent entities and aggregate invariants."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from app.domain import (
    ActorType,
    AuditEvent,
    AuditEventType,
    Case,
    CaseStatus,
    ChecklistResult,
    ChecklistStatus,
    Contradiction,
    DocumentMetadata,
    DomainInvariantError,
    ExtractedFact,
    FactStatus,
    FindingSeverity,
    FollowUpDraft,
    IntakeAnalysis,
    ModelRun,
    ModelRunPurpose,
    ModelRunStatus,
    OutputLanguage,
    ProcedureType,
    ReviewDecision,
    ReviewDecisionType,
    SourceMessage,
    UnresolvedQuestion,
    ValidationFinding,
)

NOW = datetime(2026, 7, 13, 18, 0, tzinfo=UTC)
CASE_ID = UUID("00000000-0000-0000-0000-000000000001")
ENTITY_ID = UUID("00000000-0000-0000-0000-000000000002")


def test_supporting_entities_represent_the_documented_domain() -> None:
    fact = ExtractedFact(
        field="tax_id", value="SYNTHETIC-1", source_reference="message:1", status=FactStatus.STATED
    )
    question = UnresolvedQuestion(
        code="START_DATE", question="¿Fecha de inicio?", reason="Dato obligatorio", blocking=True
    )
    contradiction = Contradiction(
        code="DATE_CONFLICT",
        description="Dos fechas distintas",
        source_references=("message:1", "document:1"),
        blocking=True,
    )
    analysis = IntakeAnalysis(
        id=ENTITY_ID,
        case_id=CASE_ID,
        procedure_type=ProcedureType.SELF_EMPLOYED_REGISTRATION,
        procedure_reason="El mensaje solicita un alta.",
        facts=(fact,),
        assumptions=("La fecha es orientativa",),
        unresolved_questions=(question,),
        contradictions=(contradiction,),
        requested_output_language=OutputLanguage.SPANISH,
        prompt_version="intake-v1",
        model_run_id=uuid4(),
        created_at=NOW,
    )
    checklist = ChecklistResult(
        id=uuid4(),
        case_id=CASE_ID,
        item_code="IDENTITY",
        label="Identificación",
        required=True,
        status=ChecklistStatus.PRESENT,
        evidence_reference="document:1",
    )
    finding = ValidationFinding(
        id=uuid4(),
        case_id=CASE_ID,
        code="MISSING_DATE",
        severity=FindingSeverity.BLOCKING,
        message="Falta la fecha.",
        field_reference="start_date",
        created_at=NOW,
    )

    assert analysis.facts == (fact,)
    assert checklist.status is ChecklistStatus.PRESENT
    assert finding.severity is FindingSeverity.BLOCKING


def test_synthetic_only_entities_accept_marked_demo_data() -> None:
    message = SourceMessage(
        id=ENTITY_ID, case_id=CASE_ID, content="Solicitud sintética", created_at=NOW
    )
    document = DocumentMetadata(
        id=uuid4(),
        case_id=CASE_ID,
        document_type="identity",
        display_name="Identificación sintética",
        created_at=NOW,
    )

    assert message.is_synthetic is True
    assert document.is_synthetic is True


@pytest.mark.parametrize(
    ("entity_factory", "message"),
    [
        (
            lambda: SourceMessage(
                id=ENTITY_ID,
                case_id=CASE_ID,
                content="demo",
                is_synthetic=False,
                created_at=NOW,
            ),
            "source messages must be synthetic",
        ),
        (
            lambda: DocumentMetadata(
                id=ENTITY_ID,
                case_id=CASE_ID,
                document_type="identity",
                display_name="demo",
                is_synthetic=False,
                created_at=NOW,
            ),
            "document metadata must be synthetic",
        ),
    ],
)
def test_real_data_is_rejected_in_the_mvp(entity_factory: object, message: str) -> None:
    with pytest.raises(DomainInvariantError, match=message):
        entity_factory()  # type: ignore[operator]


@pytest.mark.parametrize(
    "entity_factory",
    [
        lambda: SourceMessage(id=ENTITY_ID, case_id=CASE_ID, content=" ", created_at=NOW),
        lambda: DocumentMetadata(
            id=ENTITY_ID,
            case_id=CASE_ID,
            document_type=" ",
            display_name="demo",
            created_at=NOW,
        ),
        lambda: DocumentMetadata(
            id=ENTITY_ID,
            case_id=CASE_ID,
            document_type="identity",
            display_name=" ",
            created_at=NOW,
        ),
        lambda: UnresolvedQuestion(code=" ", question="Q", reason="R", blocking=False),
        lambda: UnresolvedQuestion(code="Q", question=" ", reason="R", blocking=False),
        lambda: UnresolvedQuestion(code="Q", question="Q", reason=" ", blocking=False),
        lambda: ValidationFinding(
            id=ENTITY_ID,
            case_id=CASE_ID,
            code=" ",
            severity=FindingSeverity.INFO,
            message="message",
            created_at=NOW,
        ),
        lambda: ValidationFinding(
            id=ENTITY_ID,
            case_id=CASE_ID,
            code="CODE",
            severity=FindingSeverity.INFO,
            message=" ",
            created_at=NOW,
        ),
    ],
)
def test_blank_required_text_is_rejected(entity_factory: object) -> None:
    with pytest.raises(DomainInvariantError, match="must not be blank"):
        entity_factory()  # type: ignore[operator]


def test_fact_evidence_rules_are_enforced() -> None:
    with pytest.raises(DomainInvariantError, match="unknown facts cannot carry a value"):
        ExtractedFact(
            field="date", value="2026-01-01", source_reference=None, status=FactStatus.UNKNOWN
        )
    with pytest.raises(DomainInvariantError, match="stated facts require"):
        ExtractedFact(
            field="date", value="2026-01-01", source_reference=None, status=FactStatus.STATED
        )


def test_contradictions_require_two_non_blank_sources() -> None:
    with pytest.raises(DomainInvariantError, match="at least two"):
        Contradiction(code="C", description="Conflict", source_references=("one",), blocking=True)
    with pytest.raises(DomainInvariantError, match="must not be blank"):
        Contradiction(
            code="C", description="Conflict", source_references=("one", " "), blocking=True
        )


def test_model_derived_entities_require_versions_and_valid_times() -> None:
    run = ModelRun(
        id=ENTITY_ID,
        case_id=CASE_ID,
        purpose=ModelRunPurpose.INTAKE_ANALYSIS,
        provider="openai",
        model="gpt-5.6",
        prompt_version="intake-v1",
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=1),
        status=ModelRunStatus.SUCCEEDED,
        request_id="req_synthetic",
    )
    draft = FollowUpDraft(
        id=uuid4(),
        case_id=CASE_ID,
        language=OutputLanguage.GALICIAN,
        model_text="Texto do modelo",
        reviewed_text="Texto revisado",
        prompt_version="follow-up-v1",
        model_run_id=run.id,
        created_at=NOW,
        updated_at=NOW,
    )

    assert run.completed_at is not None
    assert draft.model_text == "Texto do modelo"
    with pytest.raises(FrozenInstanceError):
        draft.model_text = "changed"  # type: ignore[misc]


def test_invalid_entity_timestamps_are_rejected() -> None:
    local_time = NOW.astimezone(timezone(timedelta(hours=-4)))
    with pytest.raises(DomainInvariantError, match="must use UTC"):
        SourceMessage(id=ENTITY_ID, case_id=CASE_ID, content="demo", created_at=local_time)
    with pytest.raises(DomainInvariantError, match="timezone-aware"):
        SourceMessage(
            id=ENTITY_ID, case_id=CASE_ID, content="demo", created_at=NOW.replace(tzinfo=None)
        )
    with pytest.raises(DomainInvariantError, match="cannot precede"):
        FollowUpDraft(
            id=ENTITY_ID,
            case_id=CASE_ID,
            language=OutputLanguage.SPANISH,
            model_text="model",
            reviewed_text="reviewed",
            prompt_version="v1",
            model_run_id=uuid4(),
            created_at=NOW,
            updated_at=NOW - timedelta(seconds=1),
        )
    with pytest.raises(DomainInvariantError, match="cannot precede"):
        ModelRun(
            id=ENTITY_ID,
            case_id=CASE_ID,
            purpose=ModelRunPurpose.INTAKE_ANALYSIS,
            provider="openai",
            model="gpt-5.6",
            prompt_version="v1",
            started_at=NOW,
            completed_at=NOW - timedelta(seconds=1),
            status=ModelRunStatus.FAILED,
        )


def test_rejection_requires_a_reason() -> None:
    with pytest.raises(DomainInvariantError, match="rejection requires"):
        ReviewDecision(
            id=ENTITY_ID,
            case_id=CASE_ID,
            decision=ReviewDecisionType.REJECTED,
            reason=" ",
            reviewer_label="Reviewer",
            created_at=NOW,
        )


def test_audit_metadata_is_immutable() -> None:
    source = {"key": "value"}
    event = AuditEvent(
        id=ENTITY_ID,
        case_id=CASE_ID,
        event_type=AuditEventType.CASE_STATUS_CHANGED,
        actor_type=ActorType.SYSTEM,
        actor_label="workflow",
        recorded_at=NOW,
        sanitized_metadata=source,
    )
    source["key"] = "changed"

    assert event.sanitized_metadata["key"] == "value"
    with pytest.raises(TypeError):
        event.sanitized_metadata["key"] = "changed"  # type: ignore[index]


def make_case(**overrides: object) -> Case:
    values: dict[str, object] = {
        "id": CASE_ID,
        "reference": "EC-0001",
        "procedure_type": ProcedureType.EMPLOYEE_HIRING,
        "output_language": OutputLanguage.SPANISH,
        "status": CaseStatus.DRAFT,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return Case(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"reference": " "}, "reference must not be blank"),
        ({"updated_at": NOW - timedelta(seconds=1)}, "updated_at cannot precede"),
        (
            {"validation_completed_at": NOW + timedelta(seconds=1)},
            "validation timestamp must be within",
        ),
        ({"status": CaseStatus.NEEDS_REVIEW}, "require an intake analysis"),
        (
            {"status": CaseStatus.NEEDS_REVIEW, "intake_analysis_id": uuid4()},
            "require deterministic validation",
        ),
    ],
)
def test_case_rejects_invalid_non_terminal_state(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(DomainInvariantError, match=message):
        make_case(**overrides)


def test_case_rejects_invalid_terminal_decisions() -> None:
    base = {
        "intake_analysis_id": uuid4(),
        "validation_completed_at": NOW,
        "status": CaseStatus.APPROVED,
    }
    with pytest.raises(DomainInvariantError, match="require a review decision"):
        make_case(**base)

    wrong_case = ReviewDecision(
        id=uuid4(),
        case_id=uuid4(),
        decision=ReviewDecisionType.APPROVED,
        reviewer_label="Reviewer",
        created_at=NOW,
    )
    with pytest.raises(DomainInvariantError, match="belong to the case"):
        make_case(**base, review_decision=wrong_case)

    wrong_decision = ReviewDecision(
        id=uuid4(),
        case_id=CASE_ID,
        decision=ReviewDecisionType.REJECTED,
        reason="Reason",
        reviewer_label="Reviewer",
        created_at=NOW,
    )
    with pytest.raises(DomainInvariantError, match="does not match"):
        make_case(**base, review_decision=wrong_decision)

    approval = ReviewDecision(
        id=uuid4(),
        case_id=CASE_ID,
        decision=ReviewDecisionType.APPROVED,
        reviewer_label="Reviewer",
        created_at=NOW,
    )
    with pytest.raises(DomainInvariantError, match="active blocking"):
        make_case(
            **base,
            validation_findings=(
                ValidationFinding(
                    id=uuid4(),
                    case_id=CASE_ID,
                    code="BLOCKER",
                    severity=FindingSeverity.BLOCKING,
                    message="Blocking",
                    created_at=NOW,
                ),
            ),
            review_decision=approval,
        )


def test_case_rejects_a_finding_from_another_case() -> None:
    finding = ValidationFinding(
        id=uuid4(),
        case_id=uuid4(),
        code="OTHER_CASE",
        severity=FindingSeverity.WARNING,
        message="Wrong aggregate",
        created_at=NOW,
    )
    with pytest.raises(DomainInvariantError, match="findings must belong"):
        make_case(validation_findings=(finding,))


def test_non_terminal_case_cannot_carry_a_review_decision() -> None:
    decision = ReviewDecision(
        id=uuid4(),
        case_id=CASE_ID,
        decision=ReviewDecisionType.APPROVED,
        reviewer_label="Reviewer",
        created_at=NOW,
    )
    with pytest.raises(DomainInvariantError, match="non-terminal"):
        make_case(review_decision=decision)
