"""Operational health endpoints."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app import __version__

router = APIRouter(tags=["operations"])


class HealthResponse(BaseModel):
    """Stable response contract for liveness and readiness probes."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    service: Literal["expediente-cero-api"]
    version: str


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health() -> HealthResponse:
    """Report that the API process is alive."""
    return HealthResponse(status="ok", service="expediente-cero-api", version=__version__)


@router.get("/ready", response_model=HealthResponse, summary="Readiness probe")
async def ready() -> HealthResponse:
    """Report readiness for the bootstrap stage, which has no external dependencies."""
    return HealthResponse(status="ok", service="expediente-cero-api", version=__version__)
