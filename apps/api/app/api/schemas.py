"""Strict HTTP schemas for synthetic case intake and typed errors."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.application.analysis import AnalysisAttempt
from app.application.intake import CaseIntake, CasePage
from app.application.reviewer import PersistedValidation
from app.application.validation import ValidationAttempt
from app.domain import (
    AuditEvent,
    CaseStatus,
    ChecklistStatus,
    FactStatus,
    FindingSeverity,
    FollowUpDraft,
    IntakeAnalysis,
    ModelRunStatus,
    OutputLanguage,
    ProcedureType,
    ReviewDecision,
    ReviewDecisionType,
)

Reference = Annotated[str, Field(min_length=1, max_length=32)]
MessageContent = Annotated[str, Field(min_length=1, max_length=8_000)]
DocumentType = Annotated[str, Field(min_length=1, max_length=64)]
DisplayName = Annotated[str, Field(min_length=1, max_length=255)]


class StrictSchema(BaseModel):
    """Base schema that rejects undeclared fields and trims bounded text."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceMessageCreate(StrictSchema):
    """One explicitly synthetic source message."""

    content: MessageContent
    is_synthetic: Literal[True]


class DocumentMetadataCreate(StrictSchema):
    """One explicitly synthetic document description without file bytes."""

    document_type: DocumentType
    display_name: DisplayName
    is_synthetic: Literal[True]


class CaseCreateRequest(StrictSchema):
    """Complete bounded payload for an atomic synthetic intake."""

    reference: Reference
    procedure_type: ProcedureType
    output_language: OutputLanguage
    is_synthetic: Literal[True]
    source_messages: Annotated[list[SourceMessageCreate], Field(min_length=1, max_length=20)]
    documents: Annotated[list[DocumentMetadataCreate], Field(max_length=20)] = Field(
        default_factory=list
    )


class SourceMessageResponse(StrictSchema):
    id: UUID
    case_id: UUID
    content: str
    is_synthetic: bool
    created_at: datetime


class DocumentMetadataResponse(StrictSchema):
    id: UUID
    case_id: UUID
    document_type: str
    display_name: str
    is_synthetic: bool
    created_at: datetime


class CaseSummaryResponse(StrictSchema):
    id: UUID
    reference: str
    procedure_type: ProcedureType
    output_language: OutputLanguage
    status: CaseStatus
    created_at: datetime
    updated_at: datetime


class CaseResponse(CaseSummaryResponse):
    source_messages: list[SourceMessageResponse]
    documents: list[DocumentMetadataResponse]

    @classmethod
    def from_intake(cls, intake: CaseIntake) -> "CaseResponse":
        case = intake.case
        return cls(
            id=case.id,
            reference=case.reference,
            procedure_type=case.procedure_type,
            output_language=case.output_language,
            status=case.status,
            created_at=case.created_at,
            updated_at=case.updated_at,
            source_messages=[
                SourceMessageResponse(
                    id=message.id,
                    case_id=message.case_id,
                    content=message.content,
                    is_synthetic=message.is_synthetic,
                    created_at=message.created_at,
                )
                for message in intake.source_messages
            ],
            documents=[
                DocumentMetadataResponse(
                    id=document.id,
                    case_id=document.case_id,
                    document_type=document.document_type,
                    display_name=document.display_name,
                    is_synthetic=document.is_synthetic,
                    created_at=document.created_at,
                )
                for document in intake.documents
            ],
        )


class CaseListResponse(StrictSchema):
    items: list[CaseSummaryResponse]
    total: int
    offset: int
    limit: int

    @classmethod
    def from_page(cls, page: CasePage) -> "CaseListResponse":
        return cls(
            items=[
                CaseSummaryResponse(
                    id=case.id,
                    reference=case.reference,
                    procedure_type=case.procedure_type,
                    output_language=case.output_language,
                    status=case.status,
                    created_at=case.created_at,
                    updated_at=case.updated_at,
                )
                for case in page.items
            ],
            total=page.total,
            offset=page.offset,
            limit=page.limit,
        )


class ExtractedFactResponse(StrictSchema):
    field: str
    value: str | None
    source_reference: str | None
    status: FactStatus


class UnresolvedQuestionResponse(StrictSchema):
    code: str
    question: str
    reason: str
    blocking: bool


class ContradictionResponse(StrictSchema):
    code: str
    description: str
    source_references: list[str]
    blocking: bool


class ModelRunResponse(StrictSchema):
    id: UUID
    provider: str
    model: str
    prompt_version: str
    status: ModelRunStatus
    started_at: datetime
    completed_at: datetime
    request_id: str | None


class IntakeAnalysisResponse(StrictSchema):
    id: UUID
    case_id: UUID
    procedure_type: ProcedureType
    procedure_reason: str
    facts: list[ExtractedFactResponse]
    assumptions: list[str]
    unresolved_questions: list[UnresolvedQuestionResponse]
    contradictions: list[ContradictionResponse]
    requested_output_language: OutputLanguage
    prompt_version: str
    model_run_id: UUID
    created_at: datetime

    @classmethod
    def from_domain(cls, analysis: IntakeAnalysis) -> "IntakeAnalysisResponse":
        return cls(
            id=analysis.id,
            case_id=analysis.case_id,
            procedure_type=analysis.procedure_type,
            procedure_reason=analysis.procedure_reason,
            facts=[
                ExtractedFactResponse(
                    field=fact.field,
                    value=fact.value,
                    source_reference=fact.source_reference,
                    status=fact.status,
                )
                for fact in analysis.facts
            ],
            assumptions=list(analysis.assumptions),
            unresolved_questions=[
                UnresolvedQuestionResponse(
                    code=question.code,
                    question=question.question,
                    reason=question.reason,
                    blocking=question.blocking,
                )
                for question in analysis.unresolved_questions
            ],
            contradictions=[
                ContradictionResponse(
                    code=contradiction.code,
                    description=contradiction.description,
                    source_references=list(contradiction.source_references),
                    blocking=contradiction.blocking,
                )
                for contradiction in analysis.contradictions
            ],
            requested_output_language=analysis.requested_output_language,
            prompt_version=analysis.prompt_version,
            model_run_id=analysis.model_run_id,
            created_at=analysis.created_at,
        )


class AnalysisAttemptResponse(StrictSchema):
    case_status: CaseStatus
    analysis: IntakeAnalysisResponse
    model_run: ModelRunResponse

    @classmethod
    def from_attempt(cls, attempt: AnalysisAttempt) -> "AnalysisAttemptResponse":
        analysis = attempt.analysis
        run = attempt.model_run
        if run.completed_at is None:
            raise ValueError("completed analysis attempts require completed_at")
        return cls(
            case_status=attempt.case.status,
            analysis=IntakeAnalysisResponse.from_domain(analysis),
            model_run=ModelRunResponse(
                id=run.id,
                provider=run.provider,
                model=run.model,
                prompt_version=run.prompt_version,
                status=run.status,
                started_at=run.started_at,
                completed_at=run.completed_at,
                request_id=run.request_id,
            ),
        )


class ChecklistResultResponse(StrictSchema):
    id: UUID
    item_code: str
    label: str
    required: bool
    status: ChecklistStatus
    evidence_reference: str | None


class ValidationFindingResponse(StrictSchema):
    id: UUID
    code: str
    severity: FindingSeverity
    message: str
    field_reference: str | None
    created_at: datetime


class ValidationAttemptResponse(StrictSchema):
    case_status: CaseStatus
    template_version: str
    validation_completed_at: datetime
    missing_fields: list[str]
    has_blocking_findings: bool
    checklist_results: list[ChecklistResultResponse]
    findings: list[ValidationFindingResponse]

    @classmethod
    def from_attempt(cls, attempt: ValidationAttempt) -> "ValidationAttemptResponse":
        computation = attempt.computation
        return cls(
            case_status=attempt.case.status,
            template_version=computation.template_version,
            validation_completed_at=computation.completed_at,
            missing_fields=list(computation.missing_fields),
            has_blocking_findings=computation.has_blocking_findings,
            checklist_results=[
                ChecklistResultResponse(
                    id=item.id,
                    item_code=item.item_code,
                    label=item.label,
                    required=item.required,
                    status=item.status,
                    evidence_reference=item.evidence_reference,
                )
                for item in computation.checklist_results
            ],
            findings=[
                ValidationFindingResponse(
                    id=item.id,
                    code=item.code,
                    severity=item.severity,
                    message=item.message,
                    field_reference=item.field_reference,
                    created_at=item.created_at,
                )
                for item in computation.findings
            ],
        )


class ValidationResultResponse(StrictSchema):
    template_version: str
    validation_completed_at: datetime
    has_blocking_findings: bool
    checklist_results: list[ChecklistResultResponse]
    findings: list[ValidationFindingResponse]

    @classmethod
    def from_persisted(cls, result: PersistedValidation) -> "ValidationResultResponse":
        return cls(
            template_version=result.template_version,
            validation_completed_at=result.completed_at,
            has_blocking_findings=result.has_blocking_findings,
            checklist_results=[
                ChecklistResultResponse(
                    id=item.id,
                    item_code=item.item_code,
                    label=item.label,
                    required=item.required,
                    status=item.status,
                    evidence_reference=item.evidence_reference,
                )
                for item in result.checklist_results
            ],
            findings=[
                ValidationFindingResponse(
                    id=item.id,
                    code=item.code,
                    severity=item.severity,
                    message=item.message,
                    field_reference=item.field_reference,
                    created_at=item.created_at,
                )
                for item in result.findings
            ],
        )


class ValidationIssue(StrictSchema):
    location: list[str | int]
    message: str
    type: str


class ErrorDetail(StrictSchema):
    code: str
    message: str
    issues: list[ValidationIssue] = Field(default_factory=list)


class ErrorEnvelope(StrictSchema):
    error: ErrorDetail


ReviewedText = Annotated[str, Field(max_length=4_000)]
ReviewerLabel = Annotated[str, Field(min_length=1, max_length=128)]
ReviewReason = Annotated[str, Field(max_length=2_000)]


class FollowUpDraftUpdateRequest(StrictSchema):
    reviewed_text: ReviewedText
    expected_version: Annotated[int, Field(ge=1)]


class FollowUpDraftResponse(StrictSchema):
    id: UUID
    case_id: UUID
    language: OutputLanguage
    model_text: str
    reviewed_text: str
    prompt_version: str
    model_run_id: UUID
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, draft: FollowUpDraft) -> "FollowUpDraftResponse":
        return cls(**{name: getattr(draft, name) for name in cls.model_fields})


class HumanActor(StrictSchema):
    label: ReviewerLabel


class ReviewDecisionRequest(StrictSchema):
    decision: ReviewDecisionType
    reason: ReviewReason | None = None
    actor: HumanActor


class ReviewDecisionResponse(StrictSchema):
    id: UUID
    case_id: UUID
    decision: ReviewDecisionType
    reason: str | None
    actor: HumanActor
    created_at: datetime

    @classmethod
    def from_domain(cls, decision: ReviewDecision) -> "ReviewDecisionResponse":
        return cls(
            id=decision.id,
            case_id=decision.case_id,
            decision=decision.decision,
            reason=decision.reason,
            actor=HumanActor(label=decision.reviewer_label),
            created_at=decision.created_at,
        )


class AuditEventResponse(StrictSchema):
    id: UUID
    event_type: str
    actor_type: str
    actor_label: str
    recorded_at: datetime
    metadata: dict[str, str]

    @classmethod
    def from_domain(cls, event: AuditEvent) -> "AuditEventResponse":
        return cls(
            id=event.id,
            event_type=event.event_type.value,
            actor_type=event.actor_type.value,
            actor_label=event.actor_label,
            recorded_at=event.recorded_at,
            metadata=dict(event.sanitized_metadata),
        )


class TimelineResponse(StrictSchema):
    case_id: UUID
    events: list[AuditEventResponse]
