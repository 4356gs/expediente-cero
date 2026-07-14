"""SQLite implementations of the application persistence ports."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.application.ports.repositories import CaseReferenceConflictError
from app.domain import (
    ActorType,
    AuditEvent,
    AuditEventType,
    Case,
    CaseStatus,
    DocumentMetadata,
    FindingSeverity,
    OutputLanguage,
    ProcedureType,
    ReviewDecision,
    ReviewDecisionType,
    SourceMessage,
    TransitionOutcome,
    ValidationFinding,
    transition_case,
)
from app.infrastructure.persistence.models import (
    AuditEventModel,
    CaseModel,
    DocumentMetadataModel,
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
            row.status = outcome.case.status.value
            row.updated_at = outcome.case.updated_at
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
