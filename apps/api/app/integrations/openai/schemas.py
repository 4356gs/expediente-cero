"""Strict Pydantic Structured Output schema for synthetic intake analysis."""

from pydantic import BaseModel, ConfigDict

from app.domain import FactStatus, OutputLanguage, ProcedureType


class StrictModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ExtractedFactOutput(StrictModelOutput):
    field: str
    value: str | None
    source_reference: str | None
    status: FactStatus


class UnresolvedQuestionOutput(StrictModelOutput):
    code: str
    question: str
    reason: str
    blocking: bool


class ContradictionOutput(StrictModelOutput):
    code: str
    description: str
    source_references: list[str]
    blocking: bool


class IntakeAnalysisOutput(StrictModelOutput):
    procedure_type: ProcedureType
    procedure_reason: str
    facts: list[ExtractedFactOutput]
    assumptions: list[str]
    unresolved_questions: list[UnresolvedQuestionOutput]
    contradictions: list[ContradictionOutput]
    requested_output_language: OutputLanguage
