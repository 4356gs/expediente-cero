"""Unit tests for deterministic validation rules and application coordination."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.application.validation import (
    DeterministicIntakeValidator,
    IntakeValidationService,
    ValidationCaseNotFoundError,
    ValidationPersistenceError,
    ValidationStateConflictError,
)
from app.application.validation_templates import VALIDATION_TEMPLATE_VERSION, template_for
from app.domain import (
    Case,
    CaseStatus,
    Contradiction,
    DocumentMetadata,
    ExtractedFact,
    FactStatus,
    FindingSeverity,
    IntakeAnalysis,
    OutputLanguage,
    ProcedureType,
    SourceMessage,
    UnresolvedQuestion,
)

NOW = datetime(2026, 7, 14, 20, 0, tzinfo=UTC)
CASE_ID = UUID("30000000-0000-0000-0000-000000000001")
MESSAGE_ID = UUID("31000000-0000-0000-0000-000000000001")


def case(procedure: ProcedureType, *, status: CaseStatus = CaseStatus.ANALYZED) -> Case:
    return Case(
        id=CASE_ID,
        reference="EC-VALIDATION",
        procedure_type=procedure,
        output_language=OutputLanguage.SPANISH,
        status=status,
        created_at=NOW,
        updated_at=NOW,
        intake_analysis_id=UUID("32000000-0000-0000-0000-000000000001"),
    )


def message() -> SourceMessage:
    return SourceMessage(id=MESSAGE_ID, case_id=CASE_ID, content="Caso sintético", created_at=NOW)


def document(document_type: str, sequence: int = 1) -> DocumentMetadata:
    return DocumentMetadata(
        id=UUID(f"33000000-0000-0000-0000-{sequence:012d}"),
        case_id=CASE_ID,
        document_type=document_type,
        display_name=f"{document_type}.pdf",
        created_at=NOW,
    )


def fact(field: str, value: str | None, status: FactStatus = FactStatus.STATED) -> ExtractedFact:
    return ExtractedFact(
        field=field,
        value=value,
        source_reference=f"message:{MESSAGE_ID}" if status is FactStatus.STATED else None,
        status=status,
    )


def analysis(
    procedure: ProcedureType,
    facts: tuple[ExtractedFact, ...],
    *,
    language: OutputLanguage = OutputLanguage.SPANISH,
    questions: tuple[UnresolvedQuestion, ...] = (),
    contradictions: tuple[Contradiction, ...] = (),
) -> IntakeAnalysis:
    return IntakeAnalysis(
        id=UUID("32000000-0000-0000-0000-000000000001"),
        case_id=CASE_ID,
        procedure_type=procedure,
        procedure_reason="Clasificación sintética",
        facts=facts,
        assumptions=(),
        unresolved_questions=questions,
        contradictions=contradictions,
        requested_output_language=language,
        prompt_version="intake-analysis-test-v2",
        model_run_id=uuid4(),
        created_at=NOW,
    )


def finding_codes(result: object) -> set[str]:
    return {item.code for item in result.findings}  # type: ignore[attr-defined]


def test_templates_are_closed_and_versioned() -> None:
    assert VALIDATION_TEMPLATE_VERSION == "deterministic-validation-v1"
    assert template_for(ProcedureType.SELF_EMPLOYED_REGISTRATION).supported_fields == {
        "activity",
        "start_date",
    }
    assert template_for(ProcedureType.EMPLOYEE_HIRING).supported_fields == {
        "employee_name",
        "requested_start_date",
        "contract_start_date",
    }


def test_self_employed_fixture_calculates_missing_start_date() -> None:
    subject = case(ProcedureType.SELF_EMPLOYED_REGISTRATION)
    result = DeterministicIntakeValidator().validate(
        subject,
        analysis(subject.procedure_type, (fact("activity", "Diseño"),)),
        (message(),),
        (document("identity"),),
        completed_at=NOW,
    )

    assert result.missing_fields == ("start_date",)
    assert "required_field_missing" in finding_codes(result)
    assert result.has_blocking_findings is True


def test_employee_fixture_detects_independent_date_mismatch() -> None:
    subject = case(ProcedureType.EMPLOYEE_HIRING)
    result = DeterministicIntakeValidator().validate(
        subject,
        analysis(
            subject.procedure_type,
            (
                fact("employee_name", "Persona sintética"),
                fact("requested_start_date", "2026-09-01"),
                fact("contract_start_date", "2026-09-15"),
            ),
        ),
        (message(),),
        (document("employment_contract"),),
        completed_at=NOW,
    )

    assert result.missing_fields == ()
    assert "employment_start_date_mismatch" in finding_codes(result)


def test_grant_fixture_produces_partial_document_checklist() -> None:
    subject = case(ProcedureType.GRANT_APPLICATION)
    result = DeterministicIntakeValidator().validate(
        subject,
        analysis(
            subject.procedure_type,
            (
                fact("applicant_name", "Empresa sintética"),
                fact("grant_program", "Programa sintético"),
                fact("project_summary", "Proyecto sintético"),
            ),
        ),
        (message(),),
        (document("project_memo"),),
        completed_at=NOW,
    )

    document_statuses = {
        item.item_code: item.status.value
        for item in result.checklist_results
        if ".document." in item.item_code
    }
    assert document_statuses == {
        "grant_application.document.project_memo": "present",
        "grant_application.document.detailed_budget": "missing",
    }
    assert "required_document_missing" in finding_codes(result)


def test_fact_evidence_and_consistency_failures_are_deterministic() -> None:
    subject = case(ProcedureType.SELF_EMPLOYED_REGISTRATION)
    invalid_reference = replace(fact("activity", "Diseño"), source_reference="message:missing")
    result = DeterministicIntakeValidator().validate(
        subject,
        analysis(
            ProcedureType.GRANT_APPLICATION,
            (
                invalid_reference,
                fact("start_date", "14/07/2026"),
                fact("extra_field", "extra"),
            ),
            language=OutputLanguage.GALICIAN,
            questions=(
                UnresolvedQuestion(
                    code="Q1", question="Confirmar dato", reason="Falta evidencia", blocking=True
                ),
            ),
            contradictions=(
                Contradiction(
                    code="C1",
                    description="Contradicción sugerida por el modelo",
                    source_references=("message:one", "message:two"),
                    blocking=True,
                ),
            ),
        ),
        (message(),),
        (document("identity"),),
        completed_at=NOW,
    )

    assert {
        "procedure_mismatch",
        "output_language_mismatch",
        "invalid_evidence_reference",
        "invalid_date",
        "unsupported_fact_field",
        "blocking_question",
        "model_reported_contradiction",
    } <= finding_codes(result)
    model_finding = next(
        item for item in result.findings if item.code == "model_reported_contradiction"
    )
    assert model_finding.severity is FindingSeverity.WARNING


@pytest.mark.parametrize(
    ("facts", "code"),
    [
        ((fact("activity", "Diseño", FactStatus.INFERRED),), "required_field_unconfirmed"),
        (
            (fact("activity", "Diseño"), fact("activity", "Programación")),
            "conflicting_fact_values",
        ),
    ],
)
def test_inferred_and_conflicting_required_values_need_review(
    facts: tuple[ExtractedFact, ...], code: str
) -> None:
    subject = case(ProcedureType.SELF_EMPLOYED_REGISTRATION)
    result = DeterministicIntakeValidator().validate(
        subject,
        analysis(subject.procedure_type, (*facts, fact("start_date", "2026-08-01"))),
        (message(),),
        (document("identity"),),
        completed_at=NOW,
    )
    assert code in finding_codes(result)
    assert "activity" in result.missing_fields


class MemoryCases:
    def __init__(self, stored: Case | None) -> None:
        self.stored = stored

    def get(self, _case_id: UUID) -> Case | None:
        return self.stored


class MemoryItems:
    def __init__(self, items: tuple[object, ...]) -> None:
        self.items = items

    def list_for_case(self, _case_id: UUID) -> tuple[object, ...]:
        return self.items


class MemoryAnalyses:
    def __init__(self, stored: IntakeAnalysis | None) -> None:
        self.stored = stored

    def get_for_case(self, _case_id: UUID) -> IntakeAnalysis | None:
        return self.stored


class MemoryValidations:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error

    def complete_validation(self, _case_id: UUID, **kwargs: object) -> Case:
        if self.error:
            raise self.error
        completed_at = kwargs["completed_at"]
        return replace(
            case(ProcedureType.SELF_EMPLOYED_REGISTRATION),
            status=CaseStatus.NEEDS_REVIEW,
            updated_at=completed_at,
            validation_completed_at=completed_at,
            validation_template_version=str(kwargs["template_version"]),
            validation_findings=kwargs["findings"],
        )


def service(stored_case: Case | None, stored_analysis: IntakeAnalysis | None, validations: object):
    return IntakeValidationService(
        MemoryCases(stored_case),  # type: ignore[arg-type]
        MemoryItems((message(),)),  # type: ignore[arg-type]
        MemoryItems((document("identity"),)),  # type: ignore[arg-type]
        MemoryAnalyses(stored_analysis),  # type: ignore[arg-type]
        validations,  # type: ignore[arg-type]
        clock=lambda: NOW,
    )


def test_service_requires_an_existing_analyzed_case_and_current_analysis() -> None:
    with pytest.raises(ValidationCaseNotFoundError):
        service(None, None, MemoryValidations()).validate(CASE_ID)
    with pytest.raises(ValidationStateConflictError):
        service(
            case(ProcedureType.SELF_EMPLOYED_REGISTRATION, status=CaseStatus.DRAFT),
            None,
            MemoryValidations(),
        ).validate(CASE_ID)
    with pytest.raises(ValidationStateConflictError):
        service(case(ProcedureType.SELF_EMPLOYED_REGISTRATION), None, MemoryValidations()).validate(
            CASE_ID
        )


def test_service_returns_persisted_review_ready_attempt() -> None:
    subject = case(ProcedureType.SELF_EMPLOYED_REGISTRATION)
    attempt = service(
        subject,
        analysis(subject.procedure_type, (fact("activity", "Diseño"),)),
        MemoryValidations(),
    ).validate(CASE_ID)
    assert attempt.case.status is CaseStatus.NEEDS_REVIEW
    assert attempt.computation.template_version == VALIDATION_TEMPLATE_VERSION


def test_service_sanitizes_persistence_failures() -> None:
    subject = case(ProcedureType.SELF_EMPLOYED_REGISTRATION)
    with pytest.raises(ValidationPersistenceError):
        service(
            subject,
            analysis(subject.procedure_type, (fact("activity", "Diseño"),)),
            MemoryValidations(error=RuntimeError("database detail")),
        ).validate(CASE_ID)
