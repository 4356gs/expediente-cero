"""Provider-neutral contract for bounded synthetic intake analysis."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.domain import (
    Case,
    DocumentMetadata,
    FactStatus,
    OutputLanguage,
    ProcedureType,
    SourceMessage,
)


@dataclass(frozen=True, slots=True)
class AnalyzedFact:
    field: str
    value: str | None
    source_reference: str | None
    status: FactStatus


@dataclass(frozen=True, slots=True)
class AnalyzedQuestion:
    code: str
    question: str
    reason: str
    blocking: bool


@dataclass(frozen=True, slots=True)
class AnalyzedContradiction:
    code: str
    description: str
    source_references: tuple[str, ...]
    blocking: bool


@dataclass(frozen=True, slots=True)
class StructuredIntake:
    procedure_type: ProcedureType
    procedure_reason: str
    facts: tuple[AnalyzedFact, ...]
    assumptions: tuple[str, ...]
    unresolved_questions: tuple[AnalyzedQuestion, ...]
    contradictions: tuple[AnalyzedContradiction, ...]
    requested_output_language: OutputLanguage


@dataclass(frozen=True, slots=True)
class AnalyzerSuccess:
    output: StructuredIntake
    request_id: str | None


@dataclass(frozen=True, slots=True)
class AnalyzerRefusal:
    request_id: str | None


AnalyzerResult = AnalyzerSuccess | AnalyzerRefusal


class AnalyzerErrorCode(StrEnum):
    NO_STRUCTURED_OUTPUT = "no_structured_output"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    CONNECTION = "connection_error"
    PROVIDER = "provider_error"


class IntakeAnalyzerError(RuntimeError):
    """Sanitized provider failure exposed to the application layer."""

    def __init__(self, code: AnalyzerErrorCode, *, request_id: str | None = None) -> None:
        super().__init__(code.value)
        self.code = code
        self.request_id = request_id


class IntakeAnalyzer(Protocol):
    """Analyze only the persisted synthetic text and document metadata supplied."""

    @property
    def model(self) -> str: ...

    @property
    def prompt_version(self) -> str: ...

    def analyze(
        self,
        case: Case,
        source_messages: tuple[SourceMessage, ...],
        documents: tuple[DocumentMetadata, ...],
    ) -> AnalyzerResult: ...
