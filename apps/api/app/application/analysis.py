"""Application use case for one synchronous, traceable intake-analysis attempt."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.application.ports import (
    AnalysisRepository,
    AnalyzerRefusal,
    AnalyzerSuccess,
    IntakeAnalyzer,
    IntakeAnalyzerError,
)
from app.application.ports.repositories import (
    CaseRepository,
    DocumentMetadataRepository,
    SourceMessageRepository,
)
from app.domain import (
    ActorType,
    Case,
    CaseStatus,
    Contradiction,
    DomainError,
    ExtractedFact,
    IntakeAnalysis,
    InvalidTransitionError,
    ModelRun,
    ModelRunPurpose,
    ModelRunStatus,
    UnresolvedQuestion,
)


class AnalysisCaseNotFoundError(LookupError):
    """The requested case is absent."""


class AnalysisAttemptFailedError(RuntimeError):
    """A sanitized, already-persisted analysis failure for HTTP mapping."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AnalysisConfigurationError(RuntimeError):
    """The provider adapter cannot be configured safely."""


class AnalysisStateConflictError(RuntimeError):
    """The case lifecycle does not permit a new analysis attempt."""


@dataclass(frozen=True, slots=True)
class AnalysisAttempt:
    case: Case
    analysis: IntakeAnalysis
    model_run: ModelRun


class IntakeAnalysisService:
    """Coordinate persistence around, but never across, the provider call."""

    def __init__(
        self,
        cases: CaseRepository,
        messages: SourceMessageRepository,
        documents: DocumentMetadataRepository,
        analyses: AnalysisRepository,
        analyzer: IntakeAnalyzer,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._cases = cases
        self._messages = messages
        self._documents = documents
        self._analyses = analyses
        self._analyzer = analyzer
        self._clock = clock or (lambda: datetime.now(UTC))

    def analyze(self, case_id: UUID) -> AnalysisAttempt:
        case = self._cases.get(case_id)
        if case is None:
            raise AnalysisCaseNotFoundError(str(case_id))
        if case.status not in {CaseStatus.DRAFT, CaseStatus.ANALYSIS_FAILED}:
            raise AnalysisStateConflictError
        messages = self._messages.list_for_case(case_id)
        documents = self._documents.list_for_case(case_id)
        if (
            not messages
            or any(not message.is_synthetic for message in messages)
            or any(not document.is_synthetic for document in documents)
        ):
            raise AnalysisAttemptFailedError("synthetic_intake_required")

        started_at = self._clock()
        try:
            case = self._cases.transition(
                case_id,
                CaseStatus.ANALYZING,
                actor_type=ActorType.SYSTEM,
                actor_label="intake-analysis-workflow",
                occurred_at=started_at,
            ).case
        except InvalidTransitionError as error:
            raise AnalysisStateConflictError from error
        run_id = uuid4()
        try:
            result = self._analyzer.analyze(case, messages, documents)
        except IntakeAnalyzerError as error:
            completed_at = self._clock()
            run = self._model_run(
                run_id=run_id,
                case_id=case_id,
                started_at=started_at,
                completed_at=completed_at,
                status=ModelRunStatus.FAILED,
                request_id=error.request_id,
                error_code=error.code.value,
            )
            self._analyses.complete_failure(run)
            raise AnalysisAttemptFailedError(error.code.value) from error

        completed_at = self._clock()
        if isinstance(result, AnalyzerRefusal):
            run = self._model_run(
                run_id=run_id,
                case_id=case_id,
                started_at=started_at,
                completed_at=completed_at,
                status=ModelRunStatus.REFUSED,
                request_id=result.request_id,
                error_code="refusal",
            )
            self._analyses.complete_failure(run)
            raise AnalysisAttemptFailedError("analysis_refused")

        if not isinstance(result, AnalyzerSuccess):
            raise AssertionError("unsupported analyzer result")
        try:
            analysis = self._to_analysis(
                case_id=case_id,
                run_id=run_id,
                completed_at=completed_at,
                result=result,
            )
        except DomainError as error:
            run = self._model_run(
                run_id=run_id,
                case_id=case_id,
                started_at=started_at,
                completed_at=completed_at,
                status=ModelRunStatus.FAILED,
                request_id=result.request_id,
                error_code="no_structured_output",
            )
            self._analyses.complete_failure(run)
            raise AnalysisAttemptFailedError("no_structured_output") from error
        run = self._model_run(
            run_id=run_id,
            case_id=case_id,
            started_at=started_at,
            completed_at=completed_at,
            status=ModelRunStatus.SUCCEEDED,
            request_id=result.request_id,
            error_code=None,
        )
        stored_case = self._analyses.complete_success(run, analysis)
        return AnalysisAttempt(case=stored_case, analysis=analysis, model_run=run)

    def _to_analysis(
        self,
        *,
        case_id: UUID,
        run_id: UUID,
        completed_at: datetime,
        result: AnalyzerSuccess,
    ) -> IntakeAnalysis:
        output = result.output
        return IntakeAnalysis(
            id=uuid4(),
            case_id=case_id,
            procedure_type=output.procedure_type,
            procedure_reason=output.procedure_reason,
            facts=tuple(
                ExtractedFact(
                    field=fact.field,
                    value=fact.value,
                    source_reference=fact.source_reference,
                    status=fact.status,
                )
                for fact in output.facts
            ),
            assumptions=output.assumptions,
            unresolved_questions=tuple(
                UnresolvedQuestion(
                    code=question.code,
                    question=question.question,
                    reason=question.reason,
                    blocking=question.blocking,
                )
                for question in output.unresolved_questions
            ),
            contradictions=tuple(
                Contradiction(
                    code=contradiction.code,
                    description=contradiction.description,
                    source_references=contradiction.source_references,
                    blocking=contradiction.blocking,
                )
                for contradiction in output.contradictions
            ),
            requested_output_language=output.requested_output_language,
            prompt_version=self._analyzer.prompt_version,
            model_run_id=run_id,
            created_at=completed_at,
        )

    def _model_run(
        self,
        *,
        run_id: UUID,
        case_id: UUID,
        started_at: datetime,
        completed_at: datetime,
        status: ModelRunStatus,
        request_id: str | None,
        error_code: str | None,
    ) -> ModelRun:
        return ModelRun(
            id=run_id,
            case_id=case_id,
            purpose=ModelRunPurpose.INTAKE_ANALYSIS,
            provider="openai",
            model=self._analyzer.model,
            prompt_version=self._analyzer.prompt_version,
            started_at=started_at,
            completed_at=completed_at,
            status=status,
            request_id=request_id,
            sanitized_error_code=error_code,
        )
