"""Deterministic validation use case for one persisted structured intake."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from app.application.ports import (
    AnalysisRepository,
    CaseRepository,
    DocumentMetadataRepository,
    SourceMessageRepository,
    ValidationRepository,
)
from app.application.validation_templates import (
    VALIDATION_TEMPLATE_VERSION,
    ProcedureTemplate,
    RequiredFact,
    template_for,
)
from app.domain import (
    Case,
    CaseStatus,
    ChecklistResult,
    ChecklistStatus,
    DocumentMetadata,
    ExtractedFact,
    FactStatus,
    FindingSeverity,
    IntakeAnalysis,
    InvalidTransitionError,
    SourceMessage,
    ValidationFinding,
)

ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class ValidationCaseNotFoundError(LookupError):
    """The requested case is absent."""


class ValidationStateConflictError(RuntimeError):
    """The case is not awaiting deterministic validation."""


class ValidationPersistenceError(RuntimeError):
    """The complete validation transaction could not be persisted."""


@dataclass(frozen=True, slots=True)
class ValidationComputation:
    template_version: str
    completed_at: datetime
    checklist_results: tuple[ChecklistResult, ...]
    findings: tuple[ValidationFinding, ...]
    missing_fields: tuple[str, ...]

    @property
    def has_blocking_findings(self) -> bool:
        return any(item.severity is FindingSeverity.BLOCKING for item in self.findings)


@dataclass(frozen=True, slots=True)
class ValidationAttempt:
    case: Case
    computation: ValidationComputation


class DeterministicIntakeValidator:
    """Calculate checklist and findings without provider or persistence access."""

    def __init__(self, *, id_factory: Callable[[], UUID] = uuid4) -> None:
        self._id_factory = id_factory

    def validate(
        self,
        case: Case,
        analysis: IntakeAnalysis,
        messages: tuple[SourceMessage, ...],
        documents: tuple[DocumentMetadata, ...],
        *,
        completed_at: datetime,
    ) -> ValidationComputation:
        template = template_for(case.procedure_type)
        valid_references = {
            *(f"message:{message.id}" for message in messages),
            *(f"document:{document.id}" for document in documents),
        }
        facts_by_field: dict[str, list[ExtractedFact]] = {}
        for fact in analysis.facts:
            facts_by_field.setdefault(fact.field, []).append(fact)

        checklist: list[ChecklistResult] = []
        findings: list[ValidationFinding] = []
        missing_fields: list[str] = []

        if analysis.procedure_type is not case.procedure_type:
            findings.append(
                self._finding(
                    case.id,
                    completed_at,
                    "procedure_mismatch",
                    "El procedimiento del análisis no coincide con el expediente.",
                    "procedure_type",
                )
            )
        if analysis.requested_output_language is not case.output_language:
            findings.append(
                self._finding(
                    case.id,
                    completed_at,
                    "output_language_mismatch",
                    "El idioma del análisis no coincide con el idioma solicitado.",
                    "output_language",
                )
            )

        for fact_definition in template.facts:
            item, item_findings = self._fact_item(
                case.id,
                template,
                fact_definition,
                tuple(facts_by_field.get(fact_definition.code, ())),
                valid_references,
                completed_at,
            )
            checklist.append(item)
            findings.extend(item_findings)
            if item.status is not ChecklistStatus.PRESENT:
                missing_fields.append(fact_definition.code)

        document_types: dict[str, list[DocumentMetadata]] = {}
        for document in documents:
            document_types.setdefault(document.document_type, []).append(document)
        for document_definition in template.documents:
            matching = sorted(
                document_types.get(document_definition.document_type, ()),
                key=lambda item: str(item.id),
            )
            if matching:
                status = ChecklistStatus.PRESENT
                evidence_reference = f"document:{matching[0].id}"
            else:
                status = ChecklistStatus.MISSING
                evidence_reference = None
                findings.append(
                    self._finding(
                        case.id,
                        completed_at,
                        "required_document_missing",
                        f"Falta el documento requerido: {document_definition.label}.",
                        document_definition.document_type,
                    )
                )
            checklist.append(
                ChecklistResult(
                    id=self._id_factory(),
                    case_id=case.id,
                    item_code=(
                        f"{template.procedure_type.value}.document."
                        f"{document_definition.document_type}"
                    ),
                    label=document_definition.label,
                    required=True,
                    status=status,
                    evidence_reference=evidence_reference,
                )
            )

        for field_code in sorted(facts_by_field.keys() - template.supported_fields):
            findings.append(
                self._finding(
                    case.id,
                    completed_at,
                    "unsupported_fact_field",
                    "El análisis contiene un campo fuera de la plantilla seleccionada.",
                    field_code,
                    severity=FindingSeverity.WARNING,
                )
            )
        for question in analysis.unresolved_questions:
            if question.blocking:
                findings.append(
                    self._finding(
                        case.id,
                        completed_at,
                        "blocking_question",
                        question.question,
                        f"question:{question.code}",
                    )
                )
        for contradiction in analysis.contradictions:
            findings.append(
                self._finding(
                    case.id,
                    completed_at,
                    "model_reported_contradiction",
                    contradiction.description,
                    f"contradiction:{contradiction.code}",
                    severity=FindingSeverity.WARNING,
                )
            )

        if case.procedure_type.value == "employee_hiring":
            requested = self._confirmed_date(
                tuple(facts_by_field.get("requested_start_date", ())), valid_references
            )
            contract = self._confirmed_date(
                tuple(facts_by_field.get("contract_start_date", ())), valid_references
            )
            if requested is not None and contract is not None and requested != contract:
                findings.append(
                    self._finding(
                        case.id,
                        completed_at,
                        "employment_start_date_mismatch",
                        "La fecha solicitada no coincide con la fecha del contrato.",
                        "requested_start_date,contract_start_date",
                    )
                )

        return ValidationComputation(
            template_version=VALIDATION_TEMPLATE_VERSION,
            completed_at=completed_at,
            checklist_results=tuple(checklist),
            findings=tuple(findings),
            missing_fields=tuple(missing_fields),
        )

    def _fact_item(
        self,
        case_id: UUID,
        template: ProcedureTemplate,
        definition: RequiredFact,
        facts: tuple[ExtractedFact, ...],
        valid_references: set[str],
        completed_at: datetime,
    ) -> tuple[ChecklistResult, tuple[ValidationFinding, ...]]:
        findings: list[ValidationFinding] = []
        stated = [
            fact
            for fact in facts
            if fact.status is FactStatus.STATED and fact.value is not None and fact.value.strip()
        ]
        distinct_values = {fact.value.strip() for fact in stated if fact.value is not None}
        evidence_reference: str | None = None

        if len(distinct_values) > 1:
            status = ChecklistStatus.NEEDS_REVIEW
            findings.append(
                self._finding(
                    case_id,
                    completed_at,
                    "conflicting_fact_values",
                    f"Hay valores declarados incompatibles para {definition.label}.",
                    definition.code,
                )
            )
        elif stated:
            fact = stated[0]
            if fact.source_reference not in valid_references:
                status = ChecklistStatus.NEEDS_REVIEW
                findings.append(
                    self._finding(
                        case_id,
                        completed_at,
                        "invalid_evidence_reference",
                        f"La evidencia de {definition.label} no existe en el expediente.",
                        definition.code,
                    )
                )
            elif definition.is_date and not self._parse_date(fact.value):
                status = ChecklistStatus.NEEDS_REVIEW
                findings.append(
                    self._finding(
                        case_id,
                        completed_at,
                        "invalid_date",
                        f"{definition.label} debe usar el formato YYYY-MM-DD.",
                        definition.code,
                    )
                )
            else:
                status = ChecklistStatus.PRESENT
                evidence_reference = fact.source_reference
        elif any(
            fact.status is FactStatus.INFERRED and fact.value is not None and fact.value.strip()
            for fact in facts
        ):
            status = ChecklistStatus.NEEDS_REVIEW
            findings.append(
                self._finding(
                    case_id,
                    completed_at,
                    "required_field_unconfirmed",
                    f"Debe confirmarse el campo requerido: {definition.label}.",
                    definition.code,
                )
            )
        else:
            status = ChecklistStatus.MISSING
            findings.append(
                self._finding(
                    case_id,
                    completed_at,
                    "required_field_missing",
                    f"Falta el campo requerido: {definition.label}.",
                    definition.code,
                )
            )

        return (
            ChecklistResult(
                id=self._id_factory(),
                case_id=case_id,
                item_code=f"{template.procedure_type.value}.field.{definition.code}",
                label=definition.label,
                required=True,
                status=status,
                evidence_reference=evidence_reference,
            ),
            tuple(findings),
        )

    def _finding(
        self,
        case_id: UUID,
        completed_at: datetime,
        code: str,
        message: str,
        field_reference: str,
        *,
        severity: FindingSeverity = FindingSeverity.BLOCKING,
    ) -> ValidationFinding:
        return ValidationFinding(
            id=self._id_factory(),
            case_id=case_id,
            code=code,
            severity=severity,
            message=message,
            field_reference=field_reference,
            created_at=completed_at,
        )

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        if value is None or ISO_DATE.fullmatch(value) is None:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def _confirmed_date(
        self, facts: tuple[ExtractedFact, ...], valid_references: set[str]
    ) -> date | None:
        values = {
            fact.value.strip()
            for fact in facts
            if fact.status is FactStatus.STATED
            and fact.value is not None
            and fact.value.strip()
            and fact.source_reference in valid_references
        }
        if len(values) != 1:
            return None
        return self._parse_date(next(iter(values)))


class IntakeValidationService:
    """Load persisted evidence, calculate results, and complete validation atomically."""

    def __init__(
        self,
        cases: CaseRepository,
        messages: SourceMessageRepository,
        documents: DocumentMetadataRepository,
        analyses: AnalysisRepository,
        validations: ValidationRepository,
        *,
        validator: DeterministicIntakeValidator | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._cases = cases
        self._messages = messages
        self._documents = documents
        self._analyses = analyses
        self._validations = validations
        self._validator = validator or DeterministicIntakeValidator()
        self._clock = clock or (lambda: datetime.now(UTC))

    def validate(self, case_id: UUID) -> ValidationAttempt:
        case = self._cases.get(case_id)
        if case is None:
            raise ValidationCaseNotFoundError(str(case_id))
        if case.status is not CaseStatus.ANALYZED:
            raise ValidationStateConflictError
        analysis = self._analyses.get_for_case(case_id)
        if analysis is None or analysis.id != case.intake_analysis_id:
            raise ValidationStateConflictError
        completed_at = self._clock()
        computation = self._validator.validate(
            case,
            analysis,
            self._messages.list_for_case(case_id),
            self._documents.list_for_case(case_id),
            completed_at=completed_at,
        )
        try:
            stored_case = self._validations.complete_validation(
                case_id,
                template_version=computation.template_version,
                completed_at=completed_at,
                checklist_results=computation.checklist_results,
                findings=computation.findings,
            )
        except InvalidTransitionError as error:
            raise ValidationStateConflictError from error
        except Exception as error:
            raise ValidationPersistenceError from error
        return ValidationAttempt(case=stored_case, computation=computation)
