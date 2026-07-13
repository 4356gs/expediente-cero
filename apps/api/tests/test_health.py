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

    assert set(paths) == {"/health", "/ready"}
