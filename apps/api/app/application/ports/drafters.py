"""Provider-neutral contract for bounded follow-up drafting."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.domain import (
    Case,
    ChecklistResult,
    DocumentMetadata,
    IntakeAnalysis,
    SourceMessage,
    ValidationFinding,
)


@dataclass(frozen=True, slots=True)
class DraftingSuccess:
    text: str
    request_id: str | None


@dataclass(frozen=True, slots=True)
class DraftingRefusal:
    request_id: str | None


DraftingResult = DraftingSuccess | DraftingRefusal


class DrafterErrorCode(StrEnum):
    TIMEOUT = "timeout"
    PROVIDER = "provider_error"
    NO_STRUCTURED_OUTPUT = "no_structured_output"


class FollowUpDrafterError(RuntimeError):
    def __init__(self, code: DrafterErrorCode, *, request_id: str | None = None) -> None:
        super().__init__(code.value)
        self.code = code
        self.request_id = request_id


class FollowUpDrafter(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def prompt_version(self) -> str: ...

    def draft(
        self,
        case: Case,
        source_messages: tuple[SourceMessage, ...],
        documents: tuple[DocumentMetadata, ...],
        analysis: IntakeAnalysis,
        checklist: tuple[ChecklistResult, ...],
        findings: tuple[ValidationFinding, ...],
    ) -> DraftingResult: ...


class FakeFollowUpDrafter:
    """Deterministic fake used by offline application and HTTP tests."""

    model = "fake-follow-up"
    prompt_version = "follow-up-draft-v1"

    def draft(
        self,
        case: Case,
        source_messages: tuple[SourceMessage, ...],
        documents: tuple[DocumentMetadata, ...],
        analysis: IntakeAnalysis,
        checklist: tuple[ChecklistResult, ...],
        findings: tuple[ValidationFinding, ...],
    ) -> DraftingResult:
        del source_messages, documents, analysis
        missing = sum(item.status.value != "present" for item in checklist)
        blocking = sum(item.severity.value == "blocking" for item in findings)
        if case.output_language.value == "gl":
            text = f"Revise o expediente: {missing} elementos pendentes e {blocking} bloqueos."
        else:
            text = f"Revise el expediente: {missing} elementos pendientes y {blocking} bloqueos."
        return DraftingSuccess(text=text, request_id="fake-request")
