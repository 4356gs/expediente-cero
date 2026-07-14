"""Persistence contracts owned by the application layer."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain import (
    ActorType,
    AuditEvent,
    Case,
    CaseStatus,
    DocumentMetadata,
    SourceMessage,
    TransitionOutcome,
)


class CaseRepository(Protocol):
    """Store and retrieve case aggregates."""

    def add(self, case: Case) -> None:
        """Persist a new case aggregate."""

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
