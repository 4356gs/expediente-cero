"""Application service for the bounded synthetic intake workflow."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.application.ports.repositories import (
    CaseRepository,
    DocumentMetadataRepository,
    SourceMessageRepository,
)
from app.domain import (
    Case,
    CaseStatus,
    DocumentMetadata,
    OutputLanguage,
    ProcedureType,
    SourceMessage,
)


class IntakeCaseNotFoundError(LookupError):
    """Requested case is absent from the intake store."""


@dataclass(frozen=True, slots=True)
class NewDocument:
    """Validated document metadata used to create a domain entity."""

    document_type: str
    display_name: str
    is_synthetic: bool


@dataclass(frozen=True, slots=True)
class CaseIntake:
    """Case aggregate and the synthetic intake records returned by the API."""

    case: Case
    source_messages: tuple[SourceMessage, ...]
    documents: tuple[DocumentMetadata, ...]


@dataclass(frozen=True, slots=True)
class CasePage:
    """Bounded page of case summaries."""

    items: tuple[Case, ...]
    total: int
    offset: int
    limit: int


class IntakeService:
    """Coordinate intake entities through the existing persistence ports."""

    def __init__(
        self,
        cases: CaseRepository,
        messages: SourceMessageRepository,
        documents: DocumentMetadataRepository,
    ) -> None:
        self._cases = cases
        self._messages = messages
        self._documents = documents

    def create_case(
        self,
        *,
        reference: str,
        procedure_type: ProcedureType,
        output_language: OutputLanguage,
        is_synthetic: bool,
        source_messages: tuple[tuple[str, bool], ...],
        documents: tuple[NewDocument, ...],
    ) -> CaseIntake:
        now = datetime.now(UTC)
        case_id = uuid4()
        case = Case(
            id=case_id,
            reference=reference,
            procedure_type=procedure_type,
            output_language=output_language,
            status=CaseStatus.DRAFT,
            created_at=now,
            updated_at=now,
        )
        messages = tuple(
            SourceMessage(
                id=uuid4(),
                case_id=case_id,
                content=content,
                is_synthetic=message_is_synthetic and is_synthetic,
                created_at=now,
            )
            for content, message_is_synthetic in source_messages
        )
        document_entities = tuple(
            DocumentMetadata(
                id=uuid4(),
                case_id=case_id,
                document_type=document.document_type,
                display_name=document.display_name,
                is_synthetic=document.is_synthetic and is_synthetic,
                created_at=now,
            )
            for document in documents
        )
        self._cases.add_intake(case, messages, document_entities)
        return CaseIntake(case=case, source_messages=messages, documents=document_entities)

    def get_case(self, case_id: UUID) -> CaseIntake:
        case = self._cases.get(case_id)
        if case is None:
            raise IntakeCaseNotFoundError(str(case_id))
        return CaseIntake(
            case=case,
            source_messages=self._messages.list_for_case(case_id),
            documents=self._documents.list_for_case(case_id),
        )

    def list_cases(self, *, offset: int, limit: int) -> CasePage:
        cases = self._cases.list()
        return CasePage(
            items=cases[offset : offset + limit],
            total=len(cases),
            offset=offset,
            limit=limit,
        )
