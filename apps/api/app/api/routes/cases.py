"""HTTP workflow for synthetic case intake."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from openai import OpenAI
from sqlalchemy.orm import Session, sessionmaker

from app.api.schemas import (
    AnalysisAttemptResponse,
    CaseCreateRequest,
    CaseListResponse,
    CaseResponse,
    ErrorEnvelope,
)
from app.application.analysis import AnalysisConfigurationError, IntakeAnalysisService
from app.application.intake import IntakeService, NewDocument
from app.infrastructure.persistence import (
    SqliteAnalysisRepository,
    SqliteCaseRepository,
    SqliteDocumentMetadataRepository,
    SqliteSourceMessageRepository,
    create_session_factory,
    create_sqlite_engine,
)
from app.integrations.openai import OpenAIIntakeAnalyzer

router = APIRouter(prefix="/cases", tags=["cases"])

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
}


def _session_factory(request: Request) -> sessionmaker[Session]:
    factory: sessionmaker[Session] | None = request.app.state.session_factory
    if factory is None:
        engine = create_sqlite_engine(request.app.state.settings.database_url)
        factory = create_session_factory(engine)
        request.app.state.database_engine = engine
        request.app.state.session_factory = factory
    return factory


async def intake_service(request: Request) -> IntakeService:
    """Build the intake service from the application's existing SQLite adapters."""
    factory = _session_factory(request)
    return IntakeService(
        SqliteCaseRepository(factory),
        SqliteSourceMessageRepository(factory),
        SqliteDocumentMetadataRepository(factory),
    )


IntakeServiceDependency = Annotated[IntakeService, Depends(intake_service)]


async def analysis_service(request: Request) -> IntakeAnalysisService:
    """Build the synchronous analysis use case without making an external call."""
    factory = _session_factory(request)
    settings = request.app.state.settings
    if settings.openai_api_key is None:
        raise AnalysisConfigurationError
    client = OpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=settings.openai_timeout_seconds,
        max_retries=0,
    )
    return IntakeAnalysisService(
        SqliteCaseRepository(factory),
        SqliteSourceMessageRepository(factory),
        SqliteDocumentMetadataRepository(factory),
        SqliteAnalysisRepository(factory),
        OpenAIIntakeAnalyzer(client, model=settings.openai_model),
    )


AnalysisServiceDependency = Annotated[IntakeAnalysisService, Depends(analysis_service)]


@router.post(
    "",
    response_model=CaseResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
async def create_case(payload: CaseCreateRequest, service: IntakeServiceDependency) -> CaseResponse:
    intake = service.create_case(
        reference=payload.reference,
        procedure_type=payload.procedure_type,
        output_language=payload.output_language,
        is_synthetic=payload.is_synthetic,
        source_messages=tuple(
            (message.content, message.is_synthetic) for message in payload.source_messages
        ),
        documents=tuple(
            NewDocument(
                document_type=document.document_type,
                display_name=document.display_name,
                is_synthetic=document.is_synthetic,
            )
            for document in payload.documents
        ),
    )
    return CaseResponse.from_intake(intake)


@router.post(
    "/{case_id}/analysis",
    response_model=AnalysisAttemptResponse,
    responses={
        **ERROR_RESPONSES,
        502: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
        504: {"model": ErrorEnvelope},
    },
)
async def analyze_case(
    case_id: UUID, service: AnalysisServiceDependency
) -> AnalysisAttemptResponse:
    return AnalysisAttemptResponse.from_attempt(service.analyze(case_id))


@router.get("/{case_id}", response_model=CaseResponse, responses=ERROR_RESPONSES)
async def get_case(case_id: UUID, service: IntakeServiceDependency) -> CaseResponse:
    return CaseResponse.from_intake(service.get_case(case_id))


@router.get("", response_model=CaseListResponse, responses=ERROR_RESPONSES)
async def list_cases(
    service: IntakeServiceDependency,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CaseListResponse:
    return CaseListResponse.from_page(service.list_cases(offset=offset, limit=limit))
