"""Tests for the backend bootstrap and operational endpoints."""

import asyncio

from app.core.config import Settings
from app.main import create_app
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response


async def request(app: FastAPI, path: str) -> Response:
    """Send one isolated request through HTTPX's in-process ASGI transport."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        return await client.get(path)


def test_health_returns_typed_service_metadata() -> None:
    app = create_app(Settings(environment="test"))

    response = asyncio.run(request(app, "/health"))

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "expediente-cero-api",
        "version": "0.1.0",
    }


def test_ready_returns_ok_without_external_dependencies() -> None:
    app = create_app(Settings(environment="test"))

    response = asyncio.run(request(app, "/ready"))

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_docs_can_be_disabled() -> None:
    app = create_app(Settings(environment="test", api_docs_enabled=False))

    assert asyncio.run(request(app, "/docs")).status_code == 404
    assert asyncio.run(request(app, "/openapi.json")).status_code == 404


def test_openapi_contract_contains_operational_routes() -> None:
    app = create_app(Settings(environment="test"))

    paths = asyncio.run(request(app, "/openapi.json")).json()["paths"]

    assert set(paths) == {
        "/health",
        "/ready",
        "/cases",
        "/cases/{case_id}",
        "/cases/{case_id}/analysis",
        "/cases/{case_id}/follow-up-draft",
        "/cases/{case_id}/review-decision",
        "/cases/{case_id}/timeline",
        "/cases/{case_id}/validation",
    }


def test_openapi_registers_unique_operations_and_case_schemas() -> None:
    app = create_app(Settings(environment="test"))

    document = asyncio.run(request(app, "/openapi.json")).json()
    operations = [
        operation
        for path in document["paths"].values()
        for method, operation in path.items()
        if method in {"get", "post"}
    ]
    operation_ids = [operation["operationId"] for operation in operations]
    schemas = document["components"]["schemas"]

    assert len(operation_ids) == len(set(operation_ids))
    assert {
        "AnalysisAttemptResponse",
        "CaseCreateRequest",
        "CaseResponse",
        "CaseListResponse",
        "ErrorEnvelope",
        "ValidationAttemptResponse",
    } <= set(schemas)
    assert document["paths"]["/cases"]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]["$ref"].endswith("/CaseCreateRequest")
    assert document["paths"]["/cases"]["post"]["responses"]["201"]["content"]["application/json"][
        "schema"
    ]["$ref"].endswith("/CaseResponse")
    for path, schema in (
        ("/cases/{case_id}/follow-up-draft", "FollowUpDraftResponse"),
        ("/cases/{case_id}/review-decision", "ReviewDecisionResponse"),
    ):
        for status_code in ("200", "201"):
            assert document["paths"][path]["post"]["responses"][status_code]["content"][
                "application/json"
            ]["schema"]["$ref"].endswith(f"/{schema}")
    for status_code in ("404", "409", "422"):
        assert document["paths"]["/cases/{case_id}"]["get"]["responses"][status_code]["content"][
            "application/json"
        ]["schema"]["$ref"].endswith("/ErrorEnvelope")
