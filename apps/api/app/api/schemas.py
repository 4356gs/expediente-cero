"""Strict HTTP schemas for synthetic case intake and typed errors."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.application.analysis import AnalysisAttempt
from app.application.intake import CaseIntake, CasePage
from app.domain import CaseStatus, FactStatus, ModelRunStatus, OutputLanguage, ProcedureType

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
            analysis=IntakeAnalysisResponse(
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
            ),
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
