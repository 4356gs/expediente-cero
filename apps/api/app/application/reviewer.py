"""Provider-free reads required to reconstruct the reviewer workspace."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.application.ports.repositories import (
    AnalysisRepository,
    CaseRepository,
    FollowUpRepository,
    ValidationRepository,
)
from app.domain import (
    Case,
    ChecklistResult,
    FindingSeverity,
    IntakeAnalysis,
    ReviewDecision,
    ValidationFinding,
)


class ReviewerCaseNotFound(LookupError): ...


class AnalysisResultNotFound(LookupError): ...


class ValidationResultNotFound(LookupError): ...


class ReviewDecisionNotFound(LookupError): ...


@dataclass(frozen=True, slots=True)
class PersistedValidation:
    """Stored deterministic output plus its case-level completion metadata."""

    template_version: str
    completed_at: datetime
    checklist_results: tuple[ChecklistResult, ...]
    findings: tuple[ValidationFinding, ...]

    @property
    def has_blocking_findings(self) -> bool:
        return any(item.severity is FindingSeverity.BLOCKING for item in self.findings)


class ReviewerReadService:
    """Read persisted reviewer artifacts without resolving a model provider."""

    def __init__(
        self,
        cases: CaseRepository,
        analyses: AnalysisRepository,
        validations: ValidationRepository,
        follow_ups: FollowUpRepository,
    ) -> None:
        self._cases = cases
        self._analyses = analyses
        self._validations = validations
        self._follow_ups = follow_ups

    def get_analysis(self, case_id: UUID) -> IntakeAnalysis:
        self._require_case(case_id)
        analysis = self._analyses.get_for_case(case_id)
        if analysis is None:
            raise AnalysisResultNotFound
        return analysis

    def get_validation(self, case_id: UUID) -> PersistedValidation:
        case = self._require_case(case_id)
        if case.validation_template_version is None or case.validation_completed_at is None:
            raise ValidationResultNotFound
        return PersistedValidation(
            template_version=case.validation_template_version,
            completed_at=case.validation_completed_at,
            checklist_results=self._validations.get_checklist(case_id),
            findings=self._validations.get_findings(case_id),
        )

    def get_decision(self, case_id: UUID) -> ReviewDecision:
        self._require_case(case_id)
        decision = self._follow_ups.get_decision(case_id)
        if decision is None:
            raise ReviewDecisionNotFound
        return decision

    def _require_case(self, case_id: UUID) -> Case:
        case = self._cases.get(case_id)
        if case is None:
            raise ReviewerCaseNotFound
        return case
