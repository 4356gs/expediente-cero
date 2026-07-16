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
from app.application.follow_up import (
    ApprovalBlockedByFindings,
    ApprovalReasonNotAllowed,
    FollowUpAttemptFailed,
    FollowUpCaseNotFound,
    FollowUpConfigurationError,
    FollowUpDraftNotFound,
    FollowUpDraftRequired,
    FollowUpGenerationInProgress,
    FollowUpPersistenceError,
    FollowUpStateConflict,
    FollowUpVersionConflict,
    InvalidReviewedText,
    RejectionReasonRequired,
    ReviewDecisionConflict,
    ReviewPersistenceError,
)
from app.application.intake import IntakeCaseNotFoundError
from app.application.ports.repositories import CaseReferenceConflictError
from app.application.reviewer import (
    AnalysisResultNotFound,
    ReviewDecisionNotFound,
    ReviewerCaseNotFound,
    ValidationResultNotFound,
)
from app.application.validation import (
    ValidationCaseNotFoundError,
    ValidationPersistenceError,
    ValidationStateConflictError,
)
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


async def reviewer_artifact_not_found_handler(_request: Request, error: Exception) -> JSONResponse:
    mapping: dict[type[Exception], tuple[str, str]] = {
        AnalysisResultNotFound: ("analysis_not_found", "The analysis does not exist."),
        ValidationResultNotFound: (
            "validation_result_not_found",
            "The validation result does not exist.",
        ),
        ReviewDecisionNotFound: (
            "review_decision_not_found",
            "The review decision does not exist.",
        ),
    }
    code, message = mapping[type(error)]
    return _response(404, code=code, message=message)


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


async def validation_state_conflict_handler(_request: Request, error: Exception) -> JSONResponse:
    return _response(
        409,
        code="validation_state_conflict",
        message="The case state does not permit deterministic validation.",
    )


async def validation_persistence_handler(_request: Request, error: Exception) -> JSONResponse:
    return _response(
        500,
        code="validation_persistence_failed",
        message="The deterministic validation result could not be persisted.",
    )


async def follow_up_error_handler(_request: Request, error: Exception) -> JSONResponse:
    mapping: dict[type[Exception], tuple[int, str, str]] = {
        FollowUpDraftNotFound: (404, "follow_up_draft_not_found", "The draft does not exist."),
        FollowUpStateConflict: (409, "follow_up_state_conflict", "The case state conflicts."),
        FollowUpGenerationInProgress: (
            409,
            "follow_up_generation_in_progress",
            "A follow-up generation attempt is active.",
        ),
        FollowUpVersionConflict: (409, "follow_up_version_conflict", "The draft is stale."),
        ReviewDecisionConflict: (
            409,
            "review_decision_conflict",
            "A different review decision already exists.",
        ),
        ApprovalBlockedByFindings: (
            409,
            "approval_blocked_by_findings",
            "Blocking findings prevent approval.",
        ),
        FollowUpDraftRequired: (
            409,
            "follow_up_draft_required",
            "A follow-up draft is required.",
        ),
        InvalidReviewedText: (422, "invalid_reviewed_text", "Reviewed text is invalid."),
        RejectionReasonRequired: (
            422,
            "rejection_reason_required",
            "A rejection reason is required.",
        ),
        ApprovalReasonNotAllowed: (
            422,
            "request_validation_error",
            "The request payload or parameters are invalid.",
        ),
        FollowUpConfigurationError: (
            503,
            "follow_up_configuration_error",
            "The follow-up provider is not configured.",
        ),
        FollowUpPersistenceError: (
            500,
            "follow_up_persistence_error",
            "The follow-up operation could not be persisted.",
        ),
        ReviewPersistenceError: (
            500,
            "review_persistence_error",
            "The review decision could not be persisted.",
        ),
    }
    status_code, code, message = mapping[type(error)]
    return _response(status_code, code=code, message=message)


async def follow_up_attempt_handler(_request: Request, error: Exception) -> JSONResponse:
    failure = cast(FollowUpAttemptFailed, error)
    status_code = {
        "follow_up_timeout": 504,
        "follow_up_refused": 502,
        "follow_up_provider_error": 502,
    }[failure.code]
    return _response(status_code, code=failure.code, message="Follow-up generation failed.")


def register_error_handlers(application: FastAPI) -> None:
    """Install the API's consistent typed error envelope."""
    application.add_exception_handler(RequestValidationError, request_validation_error_handler)
    application.add_exception_handler(IntakeCaseNotFoundError, case_not_found_error_handler)
    application.add_exception_handler(AnalysisCaseNotFoundError, case_not_found_error_handler)
    application.add_exception_handler(AnalysisAttemptFailedError, analysis_failure_handler)
    application.add_exception_handler(AnalysisConfigurationError, analysis_configuration_handler)
    application.add_exception_handler(AnalysisStateConflictError, analysis_state_conflict_handler)
    application.add_exception_handler(ValidationCaseNotFoundError, case_not_found_error_handler)
    application.add_exception_handler(
        ValidationStateConflictError, validation_state_conflict_handler
    )
    application.add_exception_handler(ValidationPersistenceError, validation_persistence_handler)
    application.add_exception_handler(DomainError, domain_error_handler)
    application.add_exception_handler(CaseReferenceConflictError, persistence_conflict_handler)
    application.add_exception_handler(FollowUpCaseNotFound, case_not_found_error_handler)
    application.add_exception_handler(ReviewerCaseNotFound, case_not_found_error_handler)
    for reviewer_error_type in (
        AnalysisResultNotFound,
        ValidationResultNotFound,
        ReviewDecisionNotFound,
    ):
        application.add_exception_handler(reviewer_error_type, reviewer_artifact_not_found_handler)
    application.add_exception_handler(FollowUpAttemptFailed, follow_up_attempt_handler)
    for error_type in (
        FollowUpDraftNotFound,
        FollowUpStateConflict,
        FollowUpGenerationInProgress,
        FollowUpVersionConflict,
        ReviewDecisionConflict,
        ApprovalBlockedByFindings,
        FollowUpDraftRequired,
        InvalidReviewedText,
        RejectionReasonRequired,
        ApprovalReasonNotAllowed,
        FollowUpConfigurationError,
        FollowUpPersistenceError,
        ReviewPersistenceError,
    ):
        application.add_exception_handler(error_type, follow_up_error_handler)
