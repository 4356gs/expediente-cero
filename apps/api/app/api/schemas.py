"""Strict HTTP schemas for synthetic case intake and typed errors."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.application.intake import CaseIntake, CasePage
from app.domain import CaseStatus, OutputLanguage, ProcedureType

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
