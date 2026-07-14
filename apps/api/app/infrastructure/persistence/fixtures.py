"""Deterministic synthetic fixtures for the three Build Week scenarios."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.domain import (
    Case,
    CaseStatus,
    DocumentMetadata,
    OutputLanguage,
    ProcedureType,
    SourceMessage,
)

FIXTURE_TIME = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class SyntheticCaseFixture:
    """One safe, repeatable intake scenario."""

    case: Case
    source_messages: tuple[SourceMessage, ...]
    documents: tuple[DocumentMetadata, ...]


def _fixture(
    sequence: int,
    *,
    procedure: ProcedureType,
    language: OutputLanguage,
    message: str,
    documents: tuple[tuple[str, str], ...],
) -> SyntheticCaseFixture:
    case_id = UUID(f"00000000-0000-0000-0000-{sequence:012d}")
    case = Case(
        id=case_id,
        reference=f"EC-DEMO-{sequence:03d}",
        procedure_type=procedure,
        output_language=language,
        status=CaseStatus.DRAFT,
        created_at=FIXTURE_TIME,
        updated_at=FIXTURE_TIME,
    )
    source = SourceMessage(
        id=UUID(f"10000000-0000-0000-0000-{sequence:012d}"),
        case_id=case_id,
        content=message,
        created_at=FIXTURE_TIME,
    )
    metadata = tuple(
        DocumentMetadata(
            id=UUID(f"20000000-0000-0000-{index:04d}-{sequence:012d}"),
            case_id=case_id,
            document_type=document_type,
            display_name=display_name,
            created_at=FIXTURE_TIME,
        )
        for index, (document_type, display_name) in enumerate(documents, start=1)
    )
    return SyntheticCaseFixture(case=case, source_messages=(source,), documents=metadata)


SYNTHETIC_CASE_FIXTURES: tuple[SyntheticCaseFixture, ...] = (
    _fixture(
        1,
        procedure=ProcedureType.SELF_EMPLOYED_REGISTRATION,
        language=OutputLanguage.SPANISH,
        message=(
            "Caso sintético: quiero darme de alta como profesional de diseño gráfico; "
            "todavía no he confirmado la fecha de inicio."
        ),
        documents=(("identity", "Identificación sintética - autónoma.pdf"),),
    ),
    _fixture(
        2,
        procedure=ProcedureType.EMPLOYEE_HIRING,
        language=OutputLanguage.GALICIAN,
        message=(
            "Caso sintético: queremos contratar unha persoa o 1 de setembro; "
            "o borrador do contrato indica o 15 de setembro."
        ),
        documents=(("employment_contract", "Contrato sintético - contratación.pdf"),),
    ),
    _fixture(
        3,
        procedure=ProcedureType.GRANT_APPLICATION,
        language=OutputLanguage.SPANISH,
        message=(
            "Caso sintético: pequeña empresa solicita preparar un expediente de ayuda; "
            "solo dispone de la memoria inicial y falta el presupuesto detallado."
        ),
        documents=(("project_memo", "Memoria sintética - subvención.pdf"),),
    ),
)
