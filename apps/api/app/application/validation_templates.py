"""Versioned deterministic intake templates for the three synthetic procedures."""

from dataclasses import dataclass

from app.domain import ProcedureType

VALIDATION_TEMPLATE_VERSION = "deterministic-validation-v1"


@dataclass(frozen=True, slots=True)
class RequiredFact:
    code: str
    label: str
    is_date: bool = False


@dataclass(frozen=True, slots=True)
class RequiredDocument:
    document_type: str
    label: str


@dataclass(frozen=True, slots=True)
class ProcedureTemplate:
    procedure_type: ProcedureType
    facts: tuple[RequiredFact, ...]
    documents: tuple[RequiredDocument, ...]

    @property
    def supported_fields(self) -> frozenset[str]:
        return frozenset(item.code for item in self.facts)


PROCEDURE_TEMPLATES: dict[ProcedureType, ProcedureTemplate] = {
    ProcedureType.SELF_EMPLOYED_REGISTRATION: ProcedureTemplate(
        procedure_type=ProcedureType.SELF_EMPLOYED_REGISTRATION,
        facts=(
            RequiredFact("activity", "Actividad declarada"),
            RequiredFact("start_date", "Fecha prevista de inicio", is_date=True),
        ),
        documents=(RequiredDocument("identity", "Identificación sintética"),),
    ),
    ProcedureType.EMPLOYEE_HIRING: ProcedureTemplate(
        procedure_type=ProcedureType.EMPLOYEE_HIRING,
        facts=(
            RequiredFact("employee_name", "Nombre de la persona candidata"),
            RequiredFact("requested_start_date", "Fecha de inicio solicitada", is_date=True),
            RequiredFact("contract_start_date", "Fecha de inicio del contrato", is_date=True),
        ),
        documents=(RequiredDocument("employment_contract", "Borrador de contrato sintético"),),
    ),
    ProcedureType.GRANT_APPLICATION: ProcedureTemplate(
        procedure_type=ProcedureType.GRANT_APPLICATION,
        facts=(
            RequiredFact("applicant_name", "Nombre de la entidad solicitante"),
            RequiredFact("grant_program", "Programa de ayuda"),
            RequiredFact("project_summary", "Resumen del proyecto"),
        ),
        documents=(
            RequiredDocument("project_memo", "Memoria sintética del proyecto"),
            RequiredDocument("detailed_budget", "Presupuesto sintético detallado"),
        ),
    ),
}


def template_for(procedure_type: ProcedureType) -> ProcedureTemplate:
    """Return the closed template for one supported procedure."""
    return PROCEDURE_TEMPLATES[procedure_type]
