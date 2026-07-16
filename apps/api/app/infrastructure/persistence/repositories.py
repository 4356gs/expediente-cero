"""SQLite implementations of the application persistence ports."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.application.ports.repositories import (
    CaseReferenceConflictError,
    FollowUpActiveAttemptError,
    FollowUpApprovalBlockedError,
    FollowUpCaseNotFoundError,
    FollowUpDecisionExistsError,
    FollowUpDraftExistsError,
    FollowUpDraftMissingError,
    FollowUpStateChangedError,
    FollowUpVersionChangedError,
)
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
    ExtractedFact,
    FactStatus,
    FindingSeverity,
    FollowUpDraft,
    IntakeAnalysis,
    InvalidTransitionError,
    ModelRun,
    ModelRunPurpose,
    ModelRunStatus,
    OutputLanguage,
    ProcedureType,
    ReviewDecision,
    ReviewDecisionType,
    SourceMessage,
    TransitionOutcome,
    UnresolvedQuestion,
    ValidationFinding,
    transition_case,
)
from app.infrastructure.persistence.models import (
    AuditEventModel,
    CaseModel,
    ChecklistResultModel,
    DocumentMetadataModel,
    FollowUpDraftModel,
    IntakeAnalysisModel,
    ModelRunModel,
    ReviewDecisionModel,
    SourceMessageModel,
    ValidationFindingModel,
)


class CaseNotFoundError(LookupError):
    """Requested case does not exist in persistence."""


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _finding_to_domain(row: ValidationFindingModel) -> ValidationFinding:
    return ValidationFinding(
        id=row.id,
        case_id=row.case_id,
        code=row.code,
        severity=FindingSeverity(row.severity),
        message=row.message,
        field_reference=row.field_reference,
        created_at=_utc(row.created_at),
    )


def _decision_to_domain(row: ReviewDecisionModel | None) -> ReviewDecision | None:
    if row is None:
        return None
    return ReviewDecision(
        id=row.id,
        case_id=row.case_id,
        decision=ReviewDecisionType(row.decision),
        reason=row.reason,
        reviewer_label=row.reviewer_label,
        created_at=_utc(row.created_at),
    )


def _case_to_domain(row: CaseModel) -> Case:
    return Case(
        id=row.id,
        reference=row.reference,
        procedure_type=ProcedureType(row.procedure_type),
        output_language=OutputLanguage(row.output_language),
        status=CaseStatus(row.status),
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        intake_analysis_id=row.intake_analysis_id,
        validation_completed_at=(
            _utc(row.validation_completed_at) if row.validation_completed_at else None
        ),
        validation_template_version=row.validation_template_version,
        validation_findings=tuple(
            _finding_to_domain(finding)
            for finding in sorted(row.validation_findings, key=lambda item: str(item.id))
        ),
        review_decision=_decision_to_domain(row.review_decision),
    )


def _case_to_model(case: Case) -> CaseModel:
    return CaseModel(
        id=case.id,
        reference=case.reference,
        procedure_type=case.procedure_type.value,
        output_language=case.output_language.value,
        status=case.status.value,
        created_at=case.created_at,
        updated_at=case.updated_at,
        intake_analysis_id=case.intake_analysis_id,
        validation_completed_at=case.validation_completed_at,
        validation_template_version=case.validation_template_version,
        validation_findings=[
            ValidationFindingModel(
                id=finding.id,
                case_id=finding.case_id,
                code=finding.code,
                severity=finding.severity.value,
                message=finding.message,
                field_reference=finding.field_reference,
                created_at=finding.created_at,
            )
            for finding in case.validation_findings
        ],
        review_decision=(
            ReviewDecisionModel(
                id=case.review_decision.id,
                case_id=case.review_decision.case_id,
                decision=case.review_decision.decision.value,
                reason=case.review_decision.reason,
                reviewer_label=case.review_decision.reviewer_label,
                created_at=case.review_decision.created_at,
            )
            if case.review_decision
            else None
        ),
    )


def _audit_to_model(event: AuditEvent) -> AuditEventModel:
    return AuditEventModel(
        id=event.id,
        case_id=event.case_id,
        event_type=event.event_type.value,
        actor_type=event.actor_type.value,
        actor_label=event.actor_label,
        recorded_at=event.recorded_at,
        sanitized_metadata=dict(event.sanitized_metadata),
    )


def _audit_to_domain(row: AuditEventModel) -> AuditEvent:
    return AuditEvent(
        id=row.id,
        case_id=row.case_id,
        event_type=AuditEventType(row.event_type),
        actor_type=ActorType(row.actor_type),
        actor_label=row.actor_label,
        recorded_at=_utc(row.recorded_at),
        sanitized_metadata=row.sanitized_metadata,
    )


def _model_run_to_model(run: ModelRun) -> ModelRunModel:
    return ModelRunModel(
        id=run.id,
        case_id=run.case_id,
        purpose=run.purpose.value,
        provider=run.provider,
        model=run.model,
        prompt_version=run.prompt_version,
        started_at=run.started_at,
        completed_at=run.completed_at,
        status=run.status.value,
        request_id=run.request_id,
        sanitized_error_code=run.sanitized_error_code,
    )


def _draft_to_domain(row: FollowUpDraftModel) -> FollowUpDraft:
    return FollowUpDraft(
        id=row.id,
        case_id=row.case_id,
        language=OutputLanguage(row.language),
        model_text=row.model_text,
        reviewed_text=row.reviewed_text,
        prompt_version=row.prompt_version,
        model_run_id=row.model_run_id,
        version=row.version,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


def _draft_to_model(draft: FollowUpDraft) -> FollowUpDraftModel:
    return FollowUpDraftModel(
        id=draft.id,
        case_id=draft.case_id,
        language=draft.language.value,
        model_text=draft.model_text,
        reviewed_text=draft.reviewed_text,
        prompt_version=draft.prompt_version,
        model_run_id=draft.model_run_id,
        version=draft.version,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )


def _analysis_to_model(analysis: IntakeAnalysis) -> IntakeAnalysisModel:
    return IntakeAnalysisModel(
        id=analysis.id,
        case_id=analysis.case_id,
        procedure_type=analysis.procedure_type.value,
        procedure_reason=analysis.procedure_reason,
        facts=[
            {
                "field": fact.field,
                "value": fact.value,
                "source_reference": fact.source_reference,
                "status": fact.status.value,
            }
            for fact in analysis.facts
        ],
        assumptions=list(analysis.assumptions),
        unresolved_questions=[
            {
                "code": question.code,
                "question": question.question,
                "reason": question.reason,
                "blocking": question.blocking,
            }
            for question in analysis.unresolved_questions
        ],
        contradictions=[
            {
                "code": contradiction.code,
                "description": contradiction.description,
                "source_references": list(contradiction.source_references),
                "blocking": contradiction.blocking,
            }
            for contradiction in analysis.contradictions
        ],
        requested_output_language=analysis.requested_output_language.value,
        prompt_version=analysis.prompt_version,
        model_run_id=analysis.model_run_id,
        created_at=analysis.created_at,
    )


def _analysis_to_domain(row: IntakeAnalysisModel) -> IntakeAnalysis:
    return IntakeAnalysis(
        id=row.id,
        case_id=row.case_id,
        procedure_type=ProcedureType(row.procedure_type),
        procedure_reason=row.procedure_reason,
        facts=tuple(
            ExtractedFact(
                field=item["field"],
                value=item["value"],
                source_reference=item["source_reference"],
                status=FactStatus(item["status"]),
            )
            for item in row.facts
        ),
        assumptions=tuple(row.assumptions),
        unresolved_questions=tuple(
            UnresolvedQuestion(
                code=item["code"],
                question=item["question"],
                reason=item["reason"],
                blocking=item["blocking"],
            )
            for item in row.unresolved_questions
        ),
        contradictions=tuple(
            Contradiction(
                code=item["code"],
                description=item["description"],
                source_references=tuple(item["source_references"]),
                blocking=item["blocking"],
            )
            for item in row.contradictions
        ),
        requested_output_language=OutputLanguage(row.requested_output_language),
        prompt_version=row.prompt_version,
        model_run_id=row.model_run_id,
        created_at=_utc(row.created_at),
    )


def _load_case(session: Session, case_id: UUID) -> CaseModel | None:
    statement = (
        select(CaseModel)
        .where(CaseModel.id == case_id)
        .options(
            selectinload(CaseModel.validation_findings),
            selectinload(CaseModel.review_decision),
        )
    )
    return session.scalar(statement)


class SqliteCaseRepository:
    """SQLAlchemy case adapter with transaction-owned write operations."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add(self, case: Case) -> None:
        with self._session_factory.begin() as session:
            session.add(_case_to_model(case))

    def add_intake(
        self,
        case: Case,
        source_messages: tuple[SourceMessage, ...],
        documents: tuple[DocumentMetadata, ...],
    ) -> None:
        try:
            with self._session_factory.begin() as session:
                session.add(_case_to_model(case))
                session.add_all(
                    SourceMessageModel(
                        id=message.id,
                        case_id=message.case_id,
                        content=message.content,
                        is_synthetic=message.is_synthetic,
                        created_at=message.created_at,
                    )
                    for message in source_messages
                )
                session.add_all(
                    DocumentMetadataModel(
                        id=document.id,
                        case_id=document.case_id,
                        document_type=document.document_type,
                        display_name=document.display_name,
                        is_synthetic=document.is_synthetic,
                        created_at=document.created_at,
                    )
                    for document in documents
                )
        except IntegrityError as error:
            if "UNIQUE constraint failed: cases.reference" in str(error.orig):
                raise CaseReferenceConflictError(case.reference) from error
            raise

    def get(self, case_id: UUID) -> Case | None:
        with self._session_factory() as session:
            row = _load_case(session, case_id)
            return _case_to_domain(row) if row else None

    def list(self) -> tuple[Case, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(CaseModel)
                .options(
                    selectinload(CaseModel.validation_findings),
                    selectinload(CaseModel.review_decision),
                )
                .order_by(CaseModel.created_at, CaseModel.id)
            ).all()
            return tuple(_case_to_domain(row) for row in rows)

    def transition(
        self,
        case_id: UUID,
        target: CaseStatus,
        *,
        actor_type: ActorType,
        actor_label: str,
        occurred_at: datetime,
        reason: str | None = None,
        audit_event_id: UUID | None = None,
        decision_id: UUID | None = None,
    ) -> TransitionOutcome:
        with self._session_factory.begin() as session:
            row = _load_case(session, case_id)
            if row is None:
                raise CaseNotFoundError(str(case_id))

            outcome = transition_case(
                _case_to_domain(row),
                target,
                actor_type=actor_type,
                actor_label=actor_label,
                occurred_at=occurred_at,
                reason=reason,
                audit_event_id=audit_event_id,
                decision_id=decision_id,
            )
            result = session.connection().execute(
                update(CaseModel)
                .where(
                    CaseModel.id == case_id,
                    CaseModel.status == row.status,
                    CaseModel.updated_at == row.updated_at,
                )
                .values(
                    status=outcome.case.status.value,
                    updated_at=outcome.case.updated_at,
                )
            )
            if result.rowcount != 1:
                raise InvalidTransitionError("case state changed concurrently")
            if outcome.case.review_decision:
                decision = outcome.case.review_decision
                row.review_decision = ReviewDecisionModel(
                    id=decision.id,
                    case_id=decision.case_id,
                    decision=decision.decision.value,
                    reason=decision.reason,
                    reviewer_label=decision.reviewer_label,
                    created_at=decision.created_at,
                )
            session.add(_audit_to_model(outcome.audit_event))
            session.flush()
            return outcome


class SqliteAuditEventRepository:
    """Read-only adapter for append-only audit events."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_for_case(self, case_id: UUID) -> tuple[AuditEvent, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(AuditEventModel)
                .where(AuditEventModel.case_id == case_id)
                .order_by(AuditEventModel.recorded_at, AuditEventModel.id)
            ).all()
            return tuple(_audit_to_domain(row) for row in rows)


class SqliteAnalysisRepository:
    """Atomic SQLite adapter for completed intake-analysis attempts."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_for_case(self, case_id: UUID) -> IntakeAnalysis | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(IntakeAnalysisModel).where(IntakeAnalysisModel.case_id == case_id)
            )
            return _analysis_to_domain(row) if row else None

    def complete_success(self, model_run: ModelRun, analysis: IntakeAnalysis) -> Case:
        with self._session_factory.begin() as session:
            row = _load_case(session, analysis.case_id)
            if row is None:
                raise CaseNotFoundError(str(analysis.case_id))
            case_with_analysis = replace(_case_to_domain(row), intake_analysis_id=analysis.id)
            outcome = transition_case(
                case_with_analysis,
                CaseStatus.ANALYZED,
                actor_type=ActorType.SYSTEM,
                actor_label="intake-analysis-workflow",
                occurred_at=analysis.created_at,
            )
            session.add(_model_run_to_model(model_run))
            session.flush()
            session.add(_analysis_to_model(analysis))
            row.intake_analysis_id = analysis.id
            row.status = outcome.case.status.value
            row.updated_at = outcome.case.updated_at
            session.add(_audit_to_model(outcome.audit_event))
            session.flush()
            return outcome.case

    def complete_failure(self, model_run: ModelRun) -> Case:
        completed_at = model_run.completed_at
        if completed_at is None:
            raise ValueError("completed model runs require completed_at")
        with self._session_factory.begin() as session:
            row = _load_case(session, model_run.case_id)
            if row is None:
                raise CaseNotFoundError(str(model_run.case_id))
            outcome = transition_case(
                _case_to_domain(row),
                CaseStatus.ANALYSIS_FAILED,
                actor_type=ActorType.SYSTEM,
                actor_label="intake-analysis-workflow",
                occurred_at=completed_at,
            )
            session.add(_model_run_to_model(model_run))
            row.status = outcome.case.status.value
            row.updated_at = outcome.case.updated_at
            session.add(_audit_to_model(outcome.audit_event))
            session.flush()
            return outcome.case


class SqliteValidationRepository:
    """Atomic SQLite adapter for deterministic validation completion."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def complete_validation(
        self,
        case_id: UUID,
        *,
        template_version: str,
        completed_at: datetime,
        checklist_results: tuple[ChecklistResult, ...],
        findings: tuple[ValidationFinding, ...],
    ) -> Case:
        with self._session_factory.begin() as session:
            row = _load_case(session, case_id)
            if row is None:
                raise CaseNotFoundError(str(case_id))
            if row.status != CaseStatus.ANALYZED.value:
                raise InvalidTransitionError("case is not awaiting deterministic validation")

            validated_case = replace(
                _case_to_domain(row),
                updated_at=completed_at,
                validation_completed_at=completed_at,
                validation_template_version=template_version,
                validation_findings=findings,
            )
            outcome = transition_case(
                validated_case,
                CaseStatus.NEEDS_REVIEW,
                actor_type=ActorType.SYSTEM,
                actor_label="deterministic-validation-workflow",
                occurred_at=completed_at,
            )
            event = replace(
                outcome.audit_event,
                sanitized_metadata={
                    **outcome.audit_event.sanitized_metadata,
                    "template_version": template_version,
                    "checklist_count": str(len(checklist_results)),
                    "finding_count": str(len(findings)),
                    "blocking_count": str(
                        sum(finding.severity is FindingSeverity.BLOCKING for finding in findings)
                    ),
                },
            )
            session.add_all(
                ChecklistResultModel(
                    id=item.id,
                    case_id=item.case_id,
                    item_code=item.item_code,
                    label=item.label,
                    required=item.required,
                    status=item.status.value,
                    evidence_reference=item.evidence_reference,
                )
                for item in checklist_results
            )
            session.add_all(
                ValidationFindingModel(
                    id=finding.id,
                    case_id=finding.case_id,
                    code=finding.code,
                    severity=finding.severity.value,
                    message=finding.message,
                    field_reference=finding.field_reference,
                    created_at=finding.created_at,
                )
                for finding in findings
            )
            result = session.connection().execute(
                update(CaseModel)
                .where(
                    CaseModel.id == case_id,
                    CaseModel.status == CaseStatus.ANALYZED.value,
                    CaseModel.updated_at == row.updated_at,
                )
                .values(
                    validation_completed_at=completed_at,
                    validation_template_version=template_version,
                    status=outcome.case.status.value,
                    updated_at=outcome.case.updated_at,
                )
            )
            if result.rowcount != 1:
                raise InvalidTransitionError("case state changed concurrently")
            session.add(_audit_to_model(event))
            session.flush()
            return replace(outcome.case, validation_findings=findings)

    def get_checklist(self, case_id: UUID) -> tuple[ChecklistResult, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(ChecklistResultModel)
                .where(ChecklistResultModel.case_id == case_id)
                .order_by(ChecklistResultModel.item_code, ChecklistResultModel.id)
            ).all()
            return tuple(
                ChecklistResult(
                    id=row.id,
                    case_id=row.case_id,
                    item_code=row.item_code,
                    label=row.label,
                    required=row.required,
                    status=ChecklistStatus(row.status),
                    evidence_reference=row.evidence_reference,
                )
                for row in rows
            )

    def get_findings(self, case_id: UUID) -> tuple[ValidationFinding, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(ValidationFindingModel)
                .where(ValidationFindingModel.case_id == case_id)
                .order_by(ValidationFindingModel.created_at, ValidationFindingModel.id)
            ).all()
            return tuple(_finding_to_domain(row) for row in rows)


class SqliteFollowUpRepository:
    """Atomic SQLite adapter for follow-up drafting and review."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_draft(self, case_id: UUID) -> FollowUpDraft | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(FollowUpDraftModel).where(FollowUpDraftModel.case_id == case_id)
            )
            return _draft_to_domain(row) if row else None

    def generation_is_active(self, case_id: UUID, *, now: datetime, lease_seconds: int) -> bool:
        with self._session_factory() as session:
            active = session.scalar(
                select(ModelRunModel).where(
                    ModelRunModel.case_id == case_id,
                    ModelRunModel.purpose == ModelRunPurpose.FOLLOW_UP_DRAFT.value,
                    ModelRunModel.status == ModelRunStatus.IN_PROGRESS.value,
                )
            )
            if active is None:
                return False
            return now < _utc(active.started_at) + timedelta(seconds=lease_seconds)

    def begin_generation(
        self, case_id: UUID, model_run: ModelRun, *, now: datetime, lease_seconds: int
    ) -> None:
        try:
            with self._session_factory.begin() as session:
                case_row = _load_case(session, case_id)
                if case_row is None:
                    raise FollowUpCaseNotFoundError(str(case_id))
                draft_row = session.scalar(
                    select(FollowUpDraftModel).where(FollowUpDraftModel.case_id == case_id)
                )
                if draft_row is not None:
                    raise FollowUpDraftExistsError(_draft_to_domain(draft_row))
                if case_row.status != CaseStatus.NEEDS_REVIEW.value:
                    raise FollowUpStateChangedError

                active = session.scalar(
                    select(ModelRunModel).where(
                        ModelRunModel.case_id == case_id,
                        ModelRunModel.purpose == ModelRunPurpose.FOLLOW_UP_DRAFT.value,
                        ModelRunModel.status == ModelRunStatus.IN_PROGRESS.value,
                    )
                )
                if active is not None:
                    started_at = _utc(active.started_at)
                    if now < started_at + timedelta(seconds=lease_seconds):
                        raise FollowUpActiveAttemptError
                    claimed = session.connection().execute(
                        update(ModelRunModel)
                        .where(
                            ModelRunModel.id == active.id,
                            ModelRunModel.status == ModelRunStatus.IN_PROGRESS.value,
                            ModelRunModel.started_at == active.started_at,
                        )
                        .values(
                            status=ModelRunStatus.FAILED.value,
                            completed_at=now,
                            sanitized_error_code="follow_up_attempt_abandoned",
                        )
                    )
                    if claimed.rowcount != 1:
                        raise FollowUpActiveAttemptError
                    session.add(
                        _audit_to_model(
                            AuditEvent(
                                id=uuid4(),
                                case_id=case_id,
                                event_type=AuditEventType.FOLLOW_UP_GENERATION_FAILED,
                                actor_type=ActorType.SYSTEM,
                                actor_label="follow-up-workflow",
                                recorded_at=now,
                                sanitized_metadata={
                                    "model_run_id": str(active.id),
                                    "purpose": ModelRunPurpose.FOLLOW_UP_DRAFT.value,
                                    "error_code": "follow_up_attempt_abandoned",
                                    "lease_expires_at": (
                                        started_at + timedelta(seconds=lease_seconds)
                                    ).isoformat(),
                                },
                            )
                        )
                    )

                session.add(_model_run_to_model(model_run))
                session.add(
                    _audit_to_model(
                        AuditEvent(
                            id=uuid4(),
                            case_id=case_id,
                            event_type=AuditEventType.FOLLOW_UP_GENERATION_STARTED,
                            actor_type=ActorType.SYSTEM,
                            actor_label="follow-up-workflow",
                            recorded_at=now,
                            sanitized_metadata={
                                "model_run_id": str(model_run.id),
                                "purpose": model_run.purpose.value,
                                "model": model_run.model,
                                "prompt_version": model_run.prompt_version,
                                "language": OutputLanguage(case_row.output_language).value,
                            },
                        )
                    )
                )
                session.flush()
        except IntegrityError as error:
            if "UNIQUE constraint failed: model_runs.case_id" in str(error.orig):
                raise FollowUpActiveAttemptError from error
            raise

    def complete_generation(
        self, model_run: ModelRun, draft: FollowUpDraft | None, *, refused: bool = False
    ) -> FollowUpDraft | None:
        with self._session_factory.begin() as session:
            result = session.connection().execute(
                update(ModelRunModel)
                .where(
                    ModelRunModel.id == model_run.id,
                    ModelRunModel.status == ModelRunStatus.IN_PROGRESS.value,
                )
                .values(
                    status=model_run.status.value,
                    completed_at=model_run.completed_at,
                    request_id=model_run.request_id,
                    sanitized_error_code=model_run.sanitized_error_code,
                )
            )
            if result.rowcount != 1:
                raise FollowUpStateChangedError
            if draft is not None:
                session.add(_draft_to_model(draft))
                event_type = AuditEventType.FOLLOW_UP_DRAFT_CREATED
                metadata = {
                    "draft_id": str(draft.id),
                    "model_run_id": str(model_run.id),
                    "language": draft.language.value,
                    "prompt_version": draft.prompt_version,
                    "version": str(draft.version),
                }
            else:
                event_type = (
                    AuditEventType.FOLLOW_UP_GENERATION_REFUSED
                    if refused
                    else AuditEventType.FOLLOW_UP_GENERATION_FAILED
                )
                metadata = {
                    "model_run_id": str(model_run.id),
                    "error_code": model_run.sanitized_error_code or "provider_error",
                }
            completed_at = model_run.completed_at
            if completed_at is None:
                raise ValueError("completed model run required")
            session.add(
                _audit_to_model(
                    AuditEvent(
                        id=uuid4(),
                        case_id=model_run.case_id,
                        event_type=event_type,
                        actor_type=ActorType.SYSTEM,
                        actor_label="follow-up-workflow",
                        recorded_at=completed_at,
                        sanitized_metadata=metadata,
                    )
                )
            )
            session.flush()
            return draft

    def edit_draft(
        self,
        case_id: UUID,
        *,
        reviewed_text: str,
        expected_version: int,
        edited_at: datetime,
    ) -> FollowUpDraft:
        with self._session_factory.begin() as session:
            case_row = _load_case(session, case_id)
            if case_row is None:
                raise FollowUpCaseNotFoundError(str(case_id))
            if case_row.status != CaseStatus.NEEDS_REVIEW.value:
                raise FollowUpStateChangedError
            row = session.scalar(
                select(FollowUpDraftModel).where(FollowUpDraftModel.case_id == case_id)
            )
            if row is None:
                raise FollowUpDraftMissingError
            if row.version != expected_version:
                raise FollowUpVersionChangedError
            if row.reviewed_text == reviewed_text:
                return _draft_to_domain(row)
            changed = session.connection().execute(
                update(FollowUpDraftModel)
                .where(
                    FollowUpDraftModel.id == row.id,
                    FollowUpDraftModel.version == expected_version,
                )
                .values(
                    reviewed_text=reviewed_text,
                    version=expected_version + 1,
                    updated_at=edited_at,
                )
            )
            if changed.rowcount != 1:
                raise FollowUpVersionChangedError
            session.add(
                _audit_to_model(
                    AuditEvent(
                        id=uuid4(),
                        case_id=case_id,
                        event_type=AuditEventType.FOLLOW_UP_DRAFT_EDITED,
                        actor_type=ActorType.USER,
                        actor_label="human-reviewer",
                        recorded_at=edited_at,
                        sanitized_metadata={
                            "draft_id": str(row.id),
                            "previous_version": str(expected_version),
                            "new_version": str(expected_version + 1),
                        },
                    )
                )
            )
            session.flush()
            row.reviewed_text = reviewed_text
            row.version = expected_version + 1
            row.updated_at = edited_at
            return _draft_to_domain(row)

    def get_decision(self, case_id: UUID) -> ReviewDecision | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(ReviewDecisionModel).where(ReviewDecisionModel.case_id == case_id)
            )
            return _decision_to_domain(row)

    def decide(
        self,
        case_id: UUID,
        *,
        decision: ReviewDecision,
        expected_updated_at: datetime,
    ) -> Case:
        try:
            with self._session_factory.begin() as session:
                case_row = _load_case(session, case_id)
                if case_row is None:
                    raise FollowUpCaseNotFoundError(str(case_id))
                if case_row.review_decision is not None:
                    existing = _decision_to_domain(case_row.review_decision)
                    assert existing is not None
                    raise FollowUpDecisionExistsError(existing)
                if case_row.status != CaseStatus.NEEDS_REVIEW.value:
                    raise FollowUpStateChangedError
                draft = session.scalar(
                    select(FollowUpDraftModel).where(FollowUpDraftModel.case_id == case_id)
                )
                if draft is None:
                    raise FollowUpDraftMissingError
                case = _case_to_domain(case_row)
                if decision.decision is ReviewDecisionType.APPROVED and case.has_blocking_findings:
                    raise FollowUpApprovalBlockedError
                target = (
                    CaseStatus.APPROVED
                    if decision.decision is ReviewDecisionType.APPROVED
                    else CaseStatus.REJECTED
                )
                outcome = transition_case(
                    case,
                    target,
                    actor_type=ActorType.USER,
                    actor_label=decision.reviewer_label,
                    occurred_at=decision.created_at,
                    reason=decision.reason,
                    decision_id=decision.id,
                )
                changed = session.connection().execute(
                    update(CaseModel)
                    .where(
                        CaseModel.id == case_id,
                        CaseModel.status == CaseStatus.NEEDS_REVIEW.value,
                        CaseModel.updated_at == expected_updated_at,
                    )
                    .values(status=target.value, updated_at=decision.created_at)
                )
                if changed.rowcount != 1:
                    raise FollowUpStateChangedError
                session.add(
                    ReviewDecisionModel(
                        id=decision.id,
                        case_id=case_id,
                        decision=decision.decision.value,
                        reason=decision.reason,
                        reviewer_label=decision.reviewer_label,
                        created_at=decision.created_at,
                    )
                )
                specialized = AuditEvent(
                    id=uuid4(),
                    case_id=case_id,
                    event_type=(
                        AuditEventType.REVIEW_APPROVED
                        if target is CaseStatus.APPROVED
                        else AuditEventType.REVIEW_REJECTED
                    ),
                    actor_type=ActorType.USER,
                    actor_label=decision.reviewer_label,
                    recorded_at=decision.created_at,
                    sanitized_metadata={
                        "decision_id": str(decision.id),
                        "draft_id": str(draft.id),
                        "previous_status": CaseStatus.NEEDS_REVIEW.value,
                        "new_status": target.value,
                    },
                )
                session.add_all(
                    [_audit_to_model(specialized), _audit_to_model(outcome.audit_event)]
                )
                session.flush()
                return outcome.case
        except IntegrityError as error:
            existing = self.get_decision(case_id)
            if existing is not None:
                raise FollowUpDecisionExistsError(existing) from error
            raise


class SqliteSourceMessageRepository:
    """SQLite adapter for synthetic source messages."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add(self, message: SourceMessage) -> None:
        with self._session_factory.begin() as session:
            session.add(
                SourceMessageModel(
                    id=message.id,
                    case_id=message.case_id,
                    content=message.content,
                    is_synthetic=message.is_synthetic,
                    created_at=message.created_at,
                )
            )

    def list_for_case(self, case_id: UUID) -> tuple[SourceMessage, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(SourceMessageModel)
                .where(SourceMessageModel.case_id == case_id)
                .order_by(SourceMessageModel.created_at, SourceMessageModel.id)
            ).all()
            return tuple(
                SourceMessage(
                    id=row.id,
                    case_id=row.case_id,
                    content=row.content,
                    is_synthetic=row.is_synthetic,
                    created_at=_utc(row.created_at),
                )
                for row in rows
            )


class SqliteDocumentMetadataRepository:
    """SQLite adapter for synthetic document metadata."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add(self, document: DocumentMetadata) -> None:
        with self._session_factory.begin() as session:
            session.add(
                DocumentMetadataModel(
                    id=document.id,
                    case_id=document.case_id,
                    document_type=document.document_type,
                    display_name=document.display_name,
                    is_synthetic=document.is_synthetic,
                    created_at=document.created_at,
                )
            )

    def list_for_case(self, case_id: UUID) -> tuple[DocumentMetadata, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(DocumentMetadataModel)
                .where(DocumentMetadataModel.case_id == case_id)
                .order_by(DocumentMetadataModel.created_at, DocumentMetadataModel.id)
            ).all()
            return tuple(
                DocumentMetadata(
                    id=row.id,
                    case_id=row.case_id,
                    document_type=row.document_type,
                    display_name=row.display_name,
                    is_synthetic=row.is_synthetic,
                    created_at=_utc(row.created_at),
                )
                for row in rows
            )
