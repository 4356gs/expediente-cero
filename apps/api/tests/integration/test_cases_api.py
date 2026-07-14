"""Integration coverage for the synthetic intake HTTP workflow."""

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.api.routes.cases import intake_service
from app.core.config import Settings
from app.domain.errors import DomainInvariantError
from app.infrastructure.persistence.fixtures import SYNTHETIC_CASE_FIXTURES
from app.infrastructure.persistence.models import (
    CaseModel,
    DocumentMetadataModel,
    SourceMessageModel,
)
from app.main import create_app
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker


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
