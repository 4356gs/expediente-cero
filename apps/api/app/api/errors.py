"""Typed HTTP error mapping shared by all API routes."""

from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.schemas import ErrorDetail, ErrorEnvelope, ValidationIssue
from app.application.analysis import (
    AnalysisAttemptFailedError,
    AnalysisCaseNotFoundError,
    AnalysisConfigurationError,
    AnalysisStateConflictError,
)
from app.application.intake import IntakeCaseNotFoundError
from app.application.ports.repositories import CaseReferenceConflictError
from app.domain.errors import DomainError


def _response(status_code: int, *, code: str, message: str) -> JSONResponse:
    envelope = ErrorEnvelope(error=ErrorDetail(code=code, message=message))
    return JSONResponse(status_code=status_code, content=envelope.model_dump(mode="json"))


async def request_validation_error_handler(_request: Request, error: Exception) -> JSONResponse:
    validation_error = cast(RequestValidationError, error)
    issues = [
        ValidationIssue(
            location=list(item["loc"]),
            message=str(item["msg"]),
            type=str(item["type"]),
        )
        for item in validation_error.errors()
    ]
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code="request_validation_error",
            message="The request payload or parameters are invalid.",
            issues=issues,
        )
    )
    return JSONResponse(status_code=422, content=envelope.model_dump(mode="json"))


async def case_not_found_error_handler(_request: Request, error: Exception) -> JSONResponse:
    return _response(404, code="case_not_found", message="The requested case does not exist.")


async def domain_error_handler(_request: Request, error: Exception) -> JSONResponse:
    domain_error = cast(DomainError, error)
    return _response(422, code="domain_error", message=str(domain_error))


async def persistence_conflict_handler(_request: Request, error: Exception) -> JSONResponse:
    return _response(
        409,
        code="persistence_conflict",
        message="The case conflicts with an existing persisted record.",
    )


async def analysis_failure_handler(_request: Request, error: Exception) -> JSONResponse:
    failure = cast(AnalysisAttemptFailedError, error)
    status_code = {
        "timeout": 504,
        "rate_limit": 503,
        "connection_error": 503,
        "synthetic_intake_required": 422,
    }.get(failure.code, 502)
    return _response(
        status_code,
        code=failure.code,
        message="The intake analysis attempt could not be completed.",
    )


async def analysis_configuration_handler(_request: Request, error: Exception) -> JSONResponse:
    return _response(
        503,
        code="analysis_provider_unavailable",
        message="The intake analysis provider is not configured.",
    )


async def analysis_state_conflict_handler(_request: Request, error: Exception) -> JSONResponse:
    return _response(
        409,
        code="analysis_state_conflict",
        message="The case state does not permit a new analysis attempt.",
    )


def register_error_handlers(application: FastAPI) -> None:
    """Install the API's consistent typed error envelope."""
    application.add_exception_handler(RequestValidationError, request_validation_error_handler)
    application.add_exception_handler(IntakeCaseNotFoundError, case_not_found_error_handler)
    application.add_exception_handler(AnalysisCaseNotFoundError, case_not_found_error_handler)
    application.add_exception_handler(AnalysisAttemptFailedError, analysis_failure_handler)
    application.add_exception_handler(AnalysisConfigurationError, analysis_configuration_handler)
    application.add_exception_handler(AnalysisStateConflictError, analysis_state_conflict_handler)
    application.add_exception_handler(DomainError, domain_error_handler)
    application.add_exception_handler(CaseReferenceConflictError, persistence_conflict_handler)
