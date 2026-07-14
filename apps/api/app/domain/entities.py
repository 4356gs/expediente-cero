"""Framework-independent domain entities and aggregate invariants."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from app.domain.enums import (
    ActorType,
    AuditEventType,
    CaseStatus,
    ChecklistStatus,
    FactStatus,
    FindingSeverity,
    ModelRunPurpose,
    ModelRunStatus,
    OutputLanguage,
    ProcedureType,
    ReviewDecisionType,
)
from app.domain.errors import DomainInvariantError


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise DomainInvariantError(f"{field_name} must not be blank")


def _require_utc(value: datetime, field_name: str) -> None:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None:
        raise DomainInvariantError(f"{field_name} must be timezone-aware")
    if offset.total_seconds() != 0:
        raise DomainInvariantError(f"{field_name} must use UTC")


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceMessage:
    """Unstructured synthetic intake supplied by a reviewer."""

    id: UUID
    case_id: UUID
    content: str
    created_at: datetime
    is_synthetic: bool = True

    def __post_init__(self) -> None:
        _require_text(self.content, "content")
        _require_utc(self.created_at, "created_at")
        if not self.is_synthetic:
            raise DomainInvariantError("source messages must be synthetic in the MVP")


@dataclass(frozen=True, slots=True, kw_only=True)
class DocumentMetadata:
    """Metadata for a synthetic document; file bytes are outside the MVP."""

    id: UUID
    case_id: UUID
    document_type: str
    display_name: str
    created_at: datetime
    is_synthetic: bool = True

    def __post_init__(self) -> None:
        _require_text(self.document_type, "document_type")
        _require_text(self.display_name, "display_name")
        _require_utc(self.created_at, "created_at")
        if not self.is_synthetic:
            raise DomainInvariantError("document metadata must be synthetic in the MVP")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtractedFact:
    """One typed fact with its evidence classification."""

    field: str
    value: str | None
    source_reference: str | None
    status: FactStatus

    def __post_init__(self) -> None:
        _require_text(self.field, "field")
        if self.status is FactStatus.UNKNOWN and self.value is not None:
            raise DomainInvariantError("unknown facts cannot carry a value")
        if self.status is FactStatus.STATED and not self.source_reference:
            raise DomainInvariantError("stated facts require a source reference")


@dataclass(frozen=True, slots=True, kw_only=True)
class UnresolvedQuestion:
    """Question that must be answered before or during review."""

    code: str
    question: str
    reason: str
    blocking: bool

    def __post_init__(self) -> None:
        _require_text(self.code, "code")
        _require_text(self.question, "question")
        _require_text(self.reason, "reason")


@dataclass(frozen=True, slots=True, kw_only=True)
class Contradiction:
    """Conflict found between two or more source references."""

    code: str
    description: str
    source_references: tuple[str, ...]
    blocking: bool

    def __post_init__(self) -> None:
        _require_text(self.code, "code")
        _require_text(self.description, "description")
        if len(self.source_references) < 2:
            raise DomainInvariantError("contradictions require at least two source references")
        if any(not reference.strip() for reference in self.source_references):
            raise DomainInvariantError("source references must not be blank")


@dataclass(frozen=True, slots=True, kw_only=True)
class IntakeAnalysis:
    """Schema-validated model result retained as review evidence."""

    id: UUID
    case_id: UUID
    procedure_type: ProcedureType
    procedure_reason: str
    facts: tuple[ExtractedFact, ...]
    assumptions: tuple[str, ...]
    unresolved_questions: tuple[UnresolvedQuestion, ...]
    contradictions: tuple[Contradiction, ...]
    requested_output_language: OutputLanguage
    prompt_version: str
    model_run_id: UUID
    created_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.procedure_reason, "procedure_reason")
        _require_text(self.prompt_version, "prompt_version")
        _require_utc(self.created_at, "created_at")
        if any(not assumption.strip() for assumption in self.assumptions):
            raise DomainInvariantError("assumptions must not be blank")


@dataclass(frozen=True, slots=True, kw_only=True)
class ChecklistResult:
    """One deterministically calculated checklist result."""

    id: UUID
    case_id: UUID
    item_code: str
    label: str
    required: bool
    status: ChecklistStatus
    evidence_reference: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.item_code, "item_code")
        _require_text(self.label, "label")
        if self.status is ChecklistStatus.PRESENT and not self.evidence_reference:
            raise DomainInvariantError("present checklist items require evidence")


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidationFinding:
    """Finding produced by deterministic validation."""

    id: UUID
    case_id: UUID
    code: str
    severity: FindingSeverity
    message: str
    created_at: datetime
    field_reference: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.code, "code")
        _require_text(self.message, "message")
        _require_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True, kw_only=True)
class FollowUpDraft:
    """Immutable model text plus the separately reviewed text."""

    id: UUID
    case_id: UUID
    language: OutputLanguage
    model_text: str
    reviewed_text: str
    prompt_version: str
    model_run_id: UUID
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.model_text, "model_text")
        _require_text(self.reviewed_text, "reviewed_text")
        _require_text(self.prompt_version, "prompt_version")
        _require_utc(self.created_at, "created_at")
        _require_utc(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise DomainInvariantError("updated_at cannot precede created_at")


@dataclass(frozen=True, slots=True, kw_only=True)
class ReviewDecision:
    """Final decision made by a human reviewer."""

    id: UUID
    case_id: UUID
    decision: ReviewDecisionType
    reviewer_label: str
    created_at: datetime
    reason: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.reviewer_label, "reviewer_label")
        _require_utc(self.created_at, "created_at")
        if self.decision is ReviewDecisionType.REJECTED and not (
            self.reason and self.reason.strip()
        ):
            raise DomainInvariantError("rejection requires a human-provided reason")


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelRun:
    """Sanitized metadata for one bounded model operation."""

    id: UUID
    case_id: UUID
    purpose: ModelRunPurpose
    provider: str
    model: str
    prompt_version: str
    started_at: datetime
    status: ModelRunStatus
    completed_at: datetime | None = None
    request_id: str | None = None
    sanitized_error_code: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.provider, "provider")
        _require_text(self.model, "model")
        _require_text(self.prompt_version, "prompt_version")
        _require_utc(self.started_at, "started_at")
        if self.completed_at is not None:
            _require_utc(self.completed_at, "completed_at")
            if self.completed_at < self.started_at:
                raise DomainInvariantError("completed_at cannot precede started_at")


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditEvent:
    """Append-only description of a material domain action."""

    id: UUID
    case_id: UUID
    event_type: AuditEventType
    actor_type: ActorType
    actor_label: str
    recorded_at: datetime
    sanitized_metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.actor_label, "actor_label")
        _require_utc(self.recorded_at, "recorded_at")
        object.__setattr__(
            self,
            "sanitized_metadata",
            MappingProxyType(dict(self.sanitized_metadata)),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Case:
    """Aggregate root that owns the case lifecycle."""

    id: UUID
    reference: str
    procedure_type: ProcedureType
    output_language: OutputLanguage
    status: CaseStatus
    created_at: datetime
    updated_at: datetime
    intake_analysis_id: UUID | None = None
    validation_completed_at: datetime | None = None
    validation_template_version: str | None = None
    validation_findings: tuple[ValidationFinding, ...] = ()
    review_decision: ReviewDecision | None = None

    def __post_init__(self) -> None:
        _require_text(self.reference, "reference")
        _require_utc(self.created_at, "created_at")
        _require_utc(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise DomainInvariantError("updated_at cannot precede created_at")
        if self.validation_completed_at is not None:
            _require_utc(self.validation_completed_at, "validation_completed_at")
            if not self.created_at <= self.validation_completed_at <= self.updated_at:
                raise DomainInvariantError("validation timestamp must be within the case lifetime")
        if self.validation_template_version is not None:
            _require_text(self.validation_template_version, "validation_template_version")
        if (self.validation_completed_at is None) != (self.validation_template_version is None):
            raise DomainInvariantError(
                "validation timestamp and template version must be recorded together"
            )
        if any(finding.case_id != self.id for finding in self.validation_findings):
            raise DomainInvariantError("validation findings must belong to the case")

        if self.status is CaseStatus.ANALYZED and self.intake_analysis_id is None:
            raise DomainInvariantError("analyzed cases require an intake analysis")

        review_ready = {
            CaseStatus.NEEDS_REVIEW,
            CaseStatus.APPROVED,
            CaseStatus.REJECTED,
        }
        if self.status in review_ready:
            if self.intake_analysis_id is None:
                raise DomainInvariantError("review-ready cases require an intake analysis")
            if self.validation_completed_at is None:
                raise DomainInvariantError("review-ready cases require deterministic validation")

        expected_decision = {
            CaseStatus.APPROVED: ReviewDecisionType.APPROVED,
            CaseStatus.REJECTED: ReviewDecisionType.REJECTED,
        }.get(self.status)
        if expected_decision is None and self.review_decision is not None:
            raise DomainInvariantError("non-terminal cases cannot have a review decision")
        if expected_decision is not None:
            if self.review_decision is None:
                raise DomainInvariantError("terminal cases require a review decision")
            if self.review_decision.case_id != self.id:
                raise DomainInvariantError("review decision must belong to the case")
            if self.review_decision.decision is not expected_decision:
                raise DomainInvariantError("review decision does not match terminal status")
        if self.status is CaseStatus.APPROVED and self.has_blocking_findings:
            raise DomainInvariantError("approved cases cannot have active blocking findings")

    @property
    def has_blocking_findings(self) -> bool:
        """Return whether current deterministic results block approval."""
        return any(
            finding.severity is FindingSeverity.BLOCKING for finding in self.validation_findings
        )
