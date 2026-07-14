"""Integration coverage for the synthetic intake HTTP workflow."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from app.api.routes.cases import analysis_service, intake_service
from app.application.analysis import IntakeAnalysisService
from app.application.ports import (
    AnalyzedFact,
    AnalyzerErrorCode,
    AnalyzerRefusal,
    AnalyzerSuccess,
    IntakeAnalyzerError,
    StructuredIntake,
)
from app.core.config import Settings
from app.domain import FactStatus, OutputLanguage, ProcedureType
from app.domain.errors import DomainInvariantError
from app.infrastructure.persistence.fixtures import SYNTHETIC_CASE_FIXTURES
from app.infrastructure.persistence.models import (
    AuditEventModel,
    CaseModel,
    DocumentMetadataModel,
    IntakeAnalysisModel,
    ModelRunModel,
    SourceMessageModel,
)
from app.infrastructure.persistence.repositories import (
    SqliteAnalysisRepository,
    SqliteCaseRepository,
    SqliteDocumentMetadataRepository,
    SqliteSourceMessageRepository,
)
from app.main import create_app
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker


class FakeAnalyzer:
    model = "gpt-5.6-test"
    prompt_version = "intake-analysis-test-v1"

    def __init__(self, result: object) -> None:
        self.result = result

    def analyze(self, case: object, messages: object, documents: object) -> object:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def analysis_output() -> StructuredIntake:
    return StructuredIntake(
        procedure_type=ProcedureType.SELF_EMPLOYED_REGISTRATION,
        procedure_reason="El mensaje sintético solicita preparar un alta.",
        facts=(
            AnalyzedFact(
                field="activity",
                value="Actividad sintética",
                source_reference="message:synthetic",
                status=FactStatus.STATED,
            ),
        ),
        assumptions=(),
        unresolved_questions=(),
        contradictions=(),
        requested_output_language=OutputLanguage.SPANISH,
    )


def analysis_use_case(factory: sessionmaker[Session], result: object) -> IntakeAnalysisService:
    moments = iter(
        [
            datetime(2099, 7, 14, 12, 0, tzinfo=UTC),
            datetime(2099, 7, 14, 12, 0, 1, tzinfo=UTC),
        ]
    )
    return IntakeAnalysisService(
        SqliteCaseRepository(factory),
        SqliteSourceMessageRepository(factory),
        SqliteDocumentMetadataRepository(factory),
        SqliteAnalysisRepository(factory),
        FakeAnalyzer(result),  # type: ignore[arg-type]
        clock=lambda: next(moments),
    )


async def request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    raise_app_exceptions: bool = True,
) -> Response:
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions),
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, json=json)


@pytest.fixture
def api_app(session_factory: sessionmaker[Session]) -> FastAPI:
    return create_app(Settings(environment="test"), session_factory=session_factory)


def fixture_payload(index: int) -> dict[str, Any]:
    fixture = SYNTHETIC_CASE_FIXTURES[index]
    return {
        "reference": fixture.case.reference,
        "procedure_type": fixture.case.procedure_type.value,
        "output_language": fixture.case.output_language.value,
        "is_synthetic": True,
        "source_messages": [
            {"content": message.content, "is_synthetic": True}
            for message in fixture.source_messages
        ],
        "documents": [
            {
                "document_type": document.document_type,
                "display_name": document.display_name,
                "is_synthetic": True,
            }
            for document in fixture.documents
        ],
    }


@pytest.mark.parametrize("fixture_index", range(3))
def test_create_and_retrieve_each_synthetic_procedure(api_app: FastAPI, fixture_index: int) -> None:
    payload = fixture_payload(fixture_index)

    created = asyncio.run(request(api_app, "POST", "/cases", json=payload))

    assert created.status_code == 201
    body = created.json()
    assert body["reference"] == payload["reference"]
    assert body["procedure_type"] == payload["procedure_type"]
    assert body["output_language"] == payload["output_language"]
    assert body["status"] == "draft"
    UUID(body["id"])
    retrieved = asyncio.run(request(api_app, "GET", f"/cases/{body['id']}"))
    assert retrieved.status_code == 200
    assert retrieved.json() == body


def test_creation_persists_messages_and_document_metadata(api_app: FastAPI) -> None:
    payload = fixture_payload(0)
    payload["reference"] = "EC-API-NESTED"
    payload["source_messages"].append(
        {"content": "Segundo mensaje claramente sintético.", "is_synthetic": True}
    )
    payload["documents"].append(
        {
            "document_type": "activity_note",
            "display_name": "Nota de actividad sintética.txt",
            "is_synthetic": True,
        }
    )

    response = asyncio.run(request(api_app, "POST", "/cases", json=payload))

    assert response.status_code == 201
    body = response.json()
    assert [item["content"] for item in body["source_messages"]] == [
        item["content"] for item in payload["source_messages"]
    ]
    assert [item["document_type"] for item in body["documents"]] == [
        item["document_type"] for item in payload["documents"]
    ]
    assert all(item["case_id"] == body["id"] for item in body["source_messages"])
    assert all(item["is_synthetic"] is True for item in body["documents"])


def test_creation_accepts_zero_document_metadata(api_app: FastAPI) -> None:
    payload = fixture_payload(2)
    payload.pop("documents")

    response = asyncio.run(request(api_app, "POST", "/cases", json=payload))

    assert response.status_code == 201
    assert response.json()["documents"] == []


def test_list_cases_returns_bounded_stable_pages(api_app: FastAPI) -> None:
    for index in range(3):
        response = asyncio.run(request(api_app, "POST", "/cases", json=fixture_payload(index)))
        assert response.status_code == 201

    first_page = asyncio.run(request(api_app, "GET", "/cases?offset=0&limit=2"))
    second_page = asyncio.run(request(api_app, "GET", "/cases?offset=2&limit=2"))

    assert first_page.status_code == second_page.status_code == 200
    assert first_page.json()["total"] == second_page.json()["total"] == 3
    assert [item["reference"] for item in first_page.json()["items"]] == [
        "EC-DEMO-001",
        "EC-DEMO-002",
    ]
    assert [item["reference"] for item in second_page.json()["items"]] == ["EC-DEMO-003"]
    assert "source_messages" not in first_page.json()["items"][0]


def test_missing_case_uses_typed_error_envelope(api_app: FastAPI) -> None:
    response = asyncio.run(request(api_app, "GET", f"/cases/{uuid4()}"))

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "case_not_found",
            "message": "The requested case does not exist.",
            "issues": [],
        }
    }


@pytest.mark.parametrize(
    ("field_path", "value"),
    [
        (("is_synthetic",), False),
        (("source_messages", 0, "is_synthetic"), False),
        (("documents", 0, "is_synthetic"), False),
    ],
)
def test_non_synthetic_payload_is_rejected(
    api_app: FastAPI, field_path: tuple[str | int, ...], value: bool
) -> None:
    payload = fixture_payload(0)
    target: Any = payload
    for part in field_path[:-1]:
        target = target[part]
    target[field_path[-1]] = value

    response = asyncio.run(request(api_app, "POST", "/cases", json=payload))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"
    assert response.json()["error"]["issues"]


@pytest.mark.parametrize(
    "payload_update",
    [
        {"reference": "X" * 33},
        {"source_messages": []},
        {
            "source_messages": [
                {"content": f"Mensaje sintético {index}", "is_synthetic": True}
                for index in range(21)
            ]
        },
        {
            "documents": [
                {
                    "document_type": "synthetic_note",
                    "display_name": f"Documento sintético {index}.txt",
                    "is_synthetic": True,
                }
                for index in range(21)
            ]
        },
        {"unexpected": "rejected"},
    ],
)
def test_payload_limits_and_unknown_fields_use_validation_envelope(
    api_app: FastAPI, payload_update: dict[str, Any]
) -> None:
    payload = fixture_payload(0)
    payload.update(payload_update)

    response = asyncio.run(request(api_app, "POST", "/cases", json=payload))

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "request_validation_error"
    assert error["message"] == "The request payload or parameters are invalid."


def test_pagination_limits_are_validated(api_app: FastAPI) -> None:
    response = asyncio.run(request(api_app, "GET", "/cases?offset=-1&limit=101"))

    assert response.status_code == 422
    locations = {tuple(issue["location"]) for issue in response.json()["error"]["issues"]}
    assert locations == {("query", "offset"), ("query", "limit")}


def test_duplicate_reference_is_conflict_and_rolls_back_intake(
    api_app: FastAPI, session_factory: sessionmaker[Session]
) -> None:
    payload = fixture_payload(0)
    first = asyncio.run(request(api_app, "POST", "/cases", json=payload))
    duplicate = asyncio.run(request(api_app, "POST", "/cases", json=payload))

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "error": {
            "code": "persistence_conflict",
            "message": "The case conflicts with an existing persisted record.",
            "issues": [],
        }
    }
    listed = asyncio.run(request(api_app, "GET", "/cases"))
    assert listed.json()["total"] == 1
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(CaseModel)) == 1
        assert session.scalar(select(func.count()).select_from(SourceMessageModel)) == 1
        assert session.scalar(select(func.count()).select_from(DocumentMetadataModel)) == 1


def test_unexpected_integrity_error_is_not_mapped_to_conflict(api_app: FastAPI) -> None:
    async def broken_service() -> Any:
        raise IntegrityError("synthetic statement", {}, RuntimeError("unexpected failure"))

    api_app.dependency_overrides[intake_service] = broken_service
    try:
        response = asyncio.run(
            request(
                api_app,
                "POST",
                "/cases",
                json=fixture_payload(0),
                raise_app_exceptions=False,
            )
        )
    finally:
        api_app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.text == "Internal Server Error"


def test_domain_failure_uses_typed_error_envelope(api_app: FastAPI) -> None:
    async def rejected_service() -> Any:
        raise DomainInvariantError("synthetic domain rejection")

    api_app.dependency_overrides[intake_service] = rejected_service
    try:
        response = asyncio.run(request(api_app, "POST", "/cases", json=fixture_payload(0)))
    finally:
        api_app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "domain_error",
            "message": "synthetic domain rejection",
            "issues": [],
        }
    }


def test_analysis_endpoint_persists_valid_attempt_and_returns_typed_output(
    api_app: FastAPI, session_factory: sessionmaker[Session]
) -> None:
    created = asyncio.run(request(api_app, "POST", "/cases", json=fixture_payload(0)))
    case_id = created.json()["id"]
    service = analysis_use_case(
        session_factory,
        AnalyzerSuccess(output=analysis_output(), request_id="req_success"),
    )

    async def overridden_analysis_service() -> IntakeAnalysisService:
        return service

    api_app.dependency_overrides[analysis_service] = overridden_analysis_service
    try:
        response = asyncio.run(request(api_app, "POST", f"/cases/{case_id}/analysis"))
    finally:
        api_app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["case_status"] == "analyzed"
    assert body["analysis"]["facts"][0]["status"] == "stated"
    assert body["model_run"] == {
        **body["model_run"],
        "provider": "openai",
        "model": "gpt-5.6-test",
        "prompt_version": "intake-analysis-test-v1",
        "status": "succeeded",
        "request_id": "req_success",
    }
    with session_factory() as session:
        stored_case = session.get(CaseModel, UUID(case_id))
        assert stored_case is not None
        assert stored_case.status == "analyzed"
        assert stored_case.intake_analysis_id is not None
        assert session.scalar(select(func.count()).select_from(ModelRunModel)) == 1
        assert session.scalar(select(func.count()).select_from(IntakeAnalysisModel)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEventModel)) == 2


@pytest.mark.parametrize(
    ("result", "expected_status", "expected_code", "run_status", "stored_error"),
    [
        (
            AnalyzerRefusal(request_id="req_refused"),
            502,
            "analysis_refused",
            "refused",
            "refusal",
        ),
        (
            IntakeAnalyzerError(AnalyzerErrorCode.TIMEOUT),
            504,
            "timeout",
            "failed",
            "timeout",
        ),
        (
            IntakeAnalyzerError(AnalyzerErrorCode.RATE_LIMIT, request_id="req_rate"),
            503,
            "rate_limit",
            "failed",
            "rate_limit",
        ),
        (
            AnalyzerSuccess(
                output=replace(analysis_output(), procedure_reason=" "),
                request_id="req_invalid",
            ),
            502,
            "no_structured_output",
            "failed",
            "no_structured_output",
        ),
    ],
)
def test_analysis_failures_are_sanitized_persisted_and_move_case_to_failed(
    api_app: FastAPI,
    session_factory: sessionmaker[Session],
    result: object,
    expected_status: int,
    expected_code: str,
    run_status: str,
    stored_error: str,
) -> None:
    payload = fixture_payload(1)
    payload["reference"] = f"EC-{expected_code[:20]}"
    created = asyncio.run(request(api_app, "POST", "/cases", json=payload))
    case_id = created.json()["id"]
    service = analysis_use_case(session_factory, result)

    async def overridden_analysis_service() -> IntakeAnalysisService:
        return service

    api_app.dependency_overrides[analysis_service] = overridden_analysis_service
    try:
        response = asyncio.run(request(api_app, "POST", f"/cases/{case_id}/analysis"))
    finally:
        api_app.dependency_overrides.clear()

    assert response.status_code == expected_status
    assert response.json() == {
        "error": {
            "code": expected_code,
            "message": "The intake analysis attempt could not be completed.",
            "issues": [],
        }
    }
    with session_factory() as session:
        stored_case = session.get(CaseModel, UUID(case_id))
        run = session.scalar(select(ModelRunModel).where(ModelRunModel.case_id == UUID(case_id)))
        assert stored_case is not None and stored_case.status == "analysis_failed"
        assert run is not None and run.status == run_status
        assert run.sanitized_error_code == stored_error
        assert session.scalar(select(func.count()).select_from(IntakeAnalysisModel)) == 0


def test_analysis_endpoint_without_api_key_has_sanitized_configuration_error(
    api_app: FastAPI,
) -> None:
    response = asyncio.run(request(api_app, "POST", f"/cases/{uuid4()}/analysis"))

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "analysis_provider_unavailable",
        "message": "The intake analysis provider is not configured.",
        "issues": [],
    }


def test_repeated_analysis_is_rejected_without_overwriting_current_evidence(
    api_app: FastAPI, session_factory: sessionmaker[Session]
) -> None:
    created = asyncio.run(request(api_app, "POST", "/cases", json=fixture_payload(0)))
    case_id = created.json()["id"]
    first_service = analysis_use_case(
        session_factory,
        AnalyzerSuccess(output=analysis_output(), request_id="req_first"),
    )

    async def first_override() -> IntakeAnalysisService:
        return first_service

    api_app.dependency_overrides[analysis_service] = first_override
    first = asyncio.run(request(api_app, "POST", f"/cases/{case_id}/analysis"))
    first_analysis_id = first.json()["analysis"]["id"]

    second_service = analysis_use_case(
        session_factory,
        AnalyzerSuccess(output=analysis_output(), request_id="req_second"),
    )

    async def second_override() -> IntakeAnalysisService:
        return second_service

    api_app.dependency_overrides[analysis_service] = second_override
    try:
        second = asyncio.run(request(api_app, "POST", f"/cases/{case_id}/analysis"))
    finally:
        api_app.dependency_overrides.clear()

    assert second.status_code == 409
    assert second.json()["error"] == {
        "code": "analysis_state_conflict",
        "message": "The case state does not permit a new analysis attempt.",
        "issues": [],
    }
    with session_factory() as session:
        analysis = session.scalar(
            select(IntakeAnalysisModel).where(IntakeAnalysisModel.case_id == UUID(case_id))
        )
        assert analysis is not None and str(analysis.id) == first_analysis_id
        assert session.scalar(select(func.count()).select_from(IntakeAnalysisModel)) == 1
        assert session.scalar(select(func.count()).select_from(ModelRunModel)) == 1


def test_provider_configuration_reaches_official_client_constructor(
    session_factory: sessionmaker[Session],
) -> None:
    settings = Settings(
        environment="test",
        OPENAI_API_KEY="sk-synthetic-test",
        openai_model="gpt-configured",
        openai_timeout_seconds=17.5,
    )
    app = create_app(settings, session_factory=session_factory)

    with (
        patch("app.api.routes.cases.OpenAI") as client_class,
        patch("app.api.routes.cases.OpenAIIntakeAnalyzer") as analyzer_class,
    ):
        response = asyncio.run(request(app, "POST", f"/cases/{uuid4()}/analysis"))

    assert response.status_code == 404
    client_class.assert_called_once_with(
        api_key="sk-synthetic-test",
        timeout=17.5,
        max_retries=0,
    )
    analyzer_class.assert_called_once_with(client_class.return_value, model="gpt-configured")
