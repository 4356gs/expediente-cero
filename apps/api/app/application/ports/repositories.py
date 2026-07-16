"""Persistence contracts owned by the application layer."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain import (
    ActorType,
    AuditEvent,
    Case,
    CaseStatus,
    ChecklistResult,
    DocumentMetadata,
    FollowUpDraft,
    IntakeAnalysis,
    ModelRun,
    ReviewDecision,
    SourceMessage,
    TransitionOutcome,
    ValidationFinding,
)


class CaseReferenceConflictError(RuntimeError):
    """A new case uses a reference that is already persisted."""


class FollowUpCaseNotFoundError(LookupError): ...


class FollowUpDraftExistsError(RuntimeError):
    def __init__(self, draft: FollowUpDraft) -> None:
        self.draft = draft


class FollowUpDraftMissingError(LookupError): ...


class FollowUpActiveAttemptError(RuntimeError): ...


class FollowUpStateChangedError(RuntimeError): ...


class FollowUpVersionChangedError(RuntimeError): ...


class FollowUpDecisionExistsError(RuntimeError):
    def __init__(self, decision: ReviewDecision) -> None:
        self.decision = decision


class FollowUpApprovalBlockedError(RuntimeError): ...


class CaseRepository(Protocol):
    """Store and retrieve case aggregates."""

    def add(self, case: Case) -> None:
        """Persist a new case aggregate."""

    def add_intake(
        self,
        case: Case,
        source_messages: tuple[SourceMessage, ...],
        documents: tuple[DocumentMetadata, ...],
    ) -> None:
        """Persist a case and its complete synthetic intake atomically."""

    def get(self, case_id: UUID) -> Case | None:
        """Return a case by identifier, or ``None`` when absent."""

    def list(self) -> tuple[Case, ...]:
        """Return cases in stable creation order."""

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
        """Persist a state transition and its audit event atomically."""


class AuditEventRepository(Protocol):
    """Read the append-only audit timeline."""

    def list_for_case(self, case_id: UUID) -> tuple[AuditEvent, ...]:
        """Return events in recording order."""


class SourceMessageRepository(Protocol):
    """Store synthetic source messages."""

    def add(self, message: SourceMessage) -> None:
        """Persist one source message."""

    def list_for_case(self, case_id: UUID) -> tuple[SourceMessage, ...]:
        """Return source messages in creation order."""


class DocumentMetadataRepository(Protocol):
    """Store metadata for synthetic documents."""

    def add(self, document: DocumentMetadata) -> None:
        """Persist one document metadata record."""

    def list_for_case(self, case_id: UUID) -> tuple[DocumentMetadata, ...]:
        """Return document metadata in creation order."""


class AnalysisRepository(Protocol):
    """Persist final model-attempt outcomes with their case transition."""

    def complete_success(self, model_run: ModelRun, analysis: IntakeAnalysis) -> Case:
        """Atomically store success metadata, current analysis, state, and audit."""

    def complete_failure(self, model_run: ModelRun) -> Case:
        """Atomically store failure metadata, failed state, and audit."""

    def get_for_case(self, case_id: UUID) -> IntakeAnalysis | None:
        """Return the current structured analysis for a case, if present."""


class ValidationRepository(Protocol):
    """Persist one complete deterministic validation transaction."""

    def complete_validation(
        self,
        case_id: UUID,
        *,
        template_version: str,
        completed_at: datetime,
        checklist_results: tuple[ChecklistResult, ...],
        findings: tuple[ValidationFinding, ...],
    ) -> Case:
        """Store results, review-ready state, timestamp, version, and audit atomically."""

    def get_checklist(self, case_id: UUID) -> tuple[ChecklistResult, ...]: ...

    def get_findings(self, case_id: UUID) -> tuple[ValidationFinding, ...]: ...


class FollowUpRepository(Protocol):
    """Own Block 6 transactions and concurrency controls."""

    def get_draft(self, case_id: UUID) -> FollowUpDraft | None: ...

    def generation_is_active(self, case_id: UUID, *, now: datetime, lease_seconds: int) -> bool: ...

    def begin_generation(
        self, case_id: UUID, model_run: ModelRun, *, now: datetime, lease_seconds: int
    ) -> None: ...

    def complete_generation(
        self, model_run: ModelRun, draft: FollowUpDraft | None, *, refused: bool = False
    ) -> FollowUpDraft | None: ...

    def edit_draft(
        self,
        case_id: UUID,
        *,
        reviewed_text: str,
        expected_version: int,
        edited_at: datetime,
    ) -> FollowUpDraft: ...

    def get_decision(self, case_id: UUID) -> ReviewDecision | None: ...

    def decide(
        self,
        case_id: UUID,
        *,
        decision: ReviewDecision,
        expected_updated_at: datetime,
    ) -> Case: ...
