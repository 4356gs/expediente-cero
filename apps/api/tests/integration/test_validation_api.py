"""Integration coverage for deterministic validation, persistence, audit, and HTTP."""

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.api.routes.cases import validation_service
from app.core.config import Settings
from app.domain import (
    ActorType,
    CaseStatus,
    ExtractedFact,
    FactStatus,
    IntakeAnalysis,
    ModelRun,
    ModelRunPurpose,
    ModelRunStatus,
    ProcedureType,
)
from app.infrastructure.persistence import (
    SqliteAnalysisRepository,
    SqliteAuditEventRepository,
    SqliteCaseRepository,
)
from app.infrastructure.persistence.fixtures import FIXTURE_TIME, SYNTHETIC_CASE_FIXTURES
from app.infrastructure.persistence.models import (
    CaseModel,
    ChecklistResultModel,
    ValidationFindingModel,
)
from app.main import create_app
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker


async def request(app: FastAPI, method: str, path: str) -> Response:
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path)


def facts_for(index: int, source_reference: str) -> tuple[ExtractedFact, ...]:
    values: tuple[tuple[str, str], ...] = (
        (("activity", "Diseño sintético"),),
        (
            ("employee_name", "Persona sintética"),
            ("requested_start_date", "2026-09-01"),
            ("contract_start_date", "2026-09-15"),
        ),
        (
            ("applicant_name", "Empresa sintética"),
            ("grant_program", "Programa sintético"),
            ("project_summary", "Proyecto sintético"),
        ),
    )[index]
    return tuple(
        ExtractedFact(
            field=field,
            value=value,
            source_reference=source_reference,
            status=FactStatus.STATED,
        )
        for field, value in values
    )


def persist_analyzed_case(factory: sessionmaker[Session], index: int) -> UUID:
    fixture = SYNTHETIC_CASE_FIXTURES[index]
    cases = SqliteCaseRepository(factory)
    cases.add_intake(fixture.case, fixture.source_messages, fixture.documents)
    started_at = FIXTURE_TIME + timedelta(minutes=1)
    completed_at = started_at + timedelta(seconds=1)
    cases.transition(
        fixture.case.id,
        CaseStatus.ANALYZING,
        actor_type=ActorType.SYSTEM,
        actor_label="test-analysis",
        occurred_at=started_at,
    )
    run = ModelRun(
        id=uuid4(),
        case_id=fixture.case.id,
        purpose=ModelRunPurpose.INTAKE_ANALYSIS,
        provider="fake",
        model="gpt-5.6-test",
        prompt_version="intake-analysis-test-v2",
        started_at=started_at,
        completed_at=completed_at,
        status=ModelRunStatus.SUCCEEDED,
    )
    analysis = IntakeAnalysis(
        id=uuid4(),
        case_id=fixture.case.id,
        procedure_type=fixture.case.procedure_type,
        procedure_reason="Análisis sintético persistido",
        facts=facts_for(index, f"message:{fixture.source_messages[0].id}"),
        assumptions=(),
        unresolved_questions=(),
        contradictions=(),
        requested_output_language=fixture.case.output_language,
        prompt_version=run.prompt_version,
        model_run_id=run.id,
        created_at=completed_at,
    )
    SqliteAnalysisRepository(factory).complete_success(run, analysis)
    return fixture.case.id


@pytest.mark.parametrize(
    ("index", "missing_fields", "required_code"),
    [
        (0, ["start_date"], "required_field_missing"),
        (1, [], "employment_start_date_mismatch"),
        (2, [], "required_document_missing"),
    ],
)
def test_validation_endpoint_completes_all_three_synthetic_scenarios(
    session_factory: sessionmaker[Session],
    index: int,
    missing_fields: list[str],
    required_code: str,
) -> None:
    case_id = persist_analyzed_case(session_factory, index)
    app = create_app(Settings(environment="test"), session_factory=session_factory)

    response = asyncio.run(request(app, "POST", f"/cases/{case_id}/validation"))

    assert response.status_code == 200
    body = response.json()
    assert body["case_status"] == "needs_review"
    assert body["template_version"] == "deterministic-validation-v1"
    assert body["missing_fields"] == missing_fields
    assert body["has_blocking_findings"] is True
    assert required_code in {item["code"] for item in body["findings"]}
    with session_factory() as session:
        stored = session.get(CaseModel, case_id)
        assert stored is not None
        assert stored.status == "needs_review"
        assert stored.validation_completed_at is not None
        assert stored.validation_template_version == "deterministic-validation-v1"
        assert session.scalar(
            select(func.count())
            .select_from(ChecklistResultModel)
            .where(ChecklistResultModel.case_id == case_id)
        ) == len(body["checklist_results"])
        assert session.scalar(
            select(func.count())
            .select_from(ValidationFindingModel)
            .where(ValidationFindingModel.case_id == case_id)
        ) == len(body["findings"])

    events = SqliteAuditEventRepository(session_factory).list_for_case(case_id)
    validation_event = events[-1]
    assert validation_event.actor_label == "deterministic-validation-workflow"
    assert validation_event.sanitized_metadata["template_version"] == (
        "deterministic-validation-v1"
    )
    assert int(validation_event.sanitized_metadata["blocking_count"]) >= 1


def test_validation_endpoint_rejects_absent_wrong_state_and_repeat(
    session_factory: sessionmaker[Session],
) -> None:
    app = create_app(Settings(environment="test"), session_factory=session_factory)
    missing = asyncio.run(request(app, "POST", f"/cases/{uuid4()}/validation"))
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "case_not_found"

    fixture = SYNTHETIC_CASE_FIXTURES[0]
    SqliteCaseRepository(session_factory).add_intake(
        fixture.case, fixture.source_messages, fixture.documents
    )
    wrong_state = asyncio.run(request(app, "POST", f"/cases/{fixture.case.id}/validation"))
    assert wrong_state.status_code == 409
    assert wrong_state.json()["error"]["code"] == "validation_state_conflict"

    case_id = persist_analyzed_case(session_factory, 1)
    first = asyncio.run(request(app, "POST", f"/cases/{case_id}/validation"))
    repeated = asyncio.run(request(app, "POST", f"/cases/{case_id}/validation"))
    assert first.status_code == 200
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "validation_state_conflict"


def test_validation_persistence_failure_uses_sanitized_typed_error(
    session_factory: sessionmaker[Session],
) -> None:
    from app.application.validation import ValidationPersistenceError

    app = create_app(Settings(environment="test"), session_factory=session_factory)

    class FailingService:
        def validate(self, _case_id: UUID) -> Any:
            raise ValidationPersistenceError("secret database detail")

    async def override() -> FailingService:
        return FailingService()

    app.dependency_overrides[validation_service] = override
    response = asyncio.run(request(app, "POST", f"/cases/{uuid4()}/validation"))

    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "validation_persistence_failed",
        "message": "The deterministic validation result could not be persisted.",
        "issues": [],
    }
    assert "secret" not in response.text


def test_validation_analysis_lookup_round_trips_structured_json(
    session_factory: sessionmaker[Session],
) -> None:
    case_id = persist_analyzed_case(session_factory, 2)
    stored = SqliteAnalysisRepository(session_factory).get_for_case(case_id)
    assert stored is not None
    assert stored.procedure_type is ProcedureType.GRANT_APPLICATION
    assert [fact.field for fact in stored.facts] == [
        "applicant_name",
        "grant_program",
        "project_summary",
    ]


def test_validation_write_conflict_rolls_back_state_findings_and_audit(
    session_factory: sessionmaker[Session],
) -> None:
    case_id = persist_analyzed_case(session_factory, 0)
    with session_factory.begin() as session:
        session.add(
            ChecklistResultModel(
                id=uuid4(),
                case_id=case_id,
                item_code="self_employed_registration.field.activity",
                label="Preexisting conflict",
                required=True,
                status="missing",
                evidence_reference=None,
            )
        )
    app = create_app(Settings(environment="test"), session_factory=session_factory)

    response = asyncio.run(request(app, "POST", f"/cases/{case_id}/validation"))

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "validation_persistence_failed"
    stored = SqliteCaseRepository(session_factory).get(case_id)
    assert stored is not None
    assert stored.status is CaseStatus.ANALYZED
    assert stored.validation_completed_at is None
    assert stored.validation_template_version is None
    assert stored.validation_findings == ()
    assert len(SqliteAuditEventRepository(session_factory).list_for_case(case_id)) == 2
