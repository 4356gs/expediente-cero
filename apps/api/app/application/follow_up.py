"""Block 6 follow-up drafting, editing, review, and timeline use cases."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.application.ports import (
    AnalysisRepository,
    AuditEventRepository,
    CaseRepository,
    DocumentMetadataRepository,
    DrafterErrorCode,
    DraftingRefusal,
    FollowUpActiveAttemptError,
    FollowUpApprovalBlockedError,
    FollowUpCaseNotFoundError,
    FollowUpDecisionExistsError,
    FollowUpDrafter,
    FollowUpDrafterError,
    FollowUpDraftExistsError,
    FollowUpDraftMissingError,
    FollowUpRepository,
    FollowUpStateChangedError,
    FollowUpVersionChangedError,
    SourceMessageRepository,
    ValidationRepository,
)
from app.domain import (
    AuditEvent,
    CaseStatus,
    FollowUpDraft,
    ModelRun,
    ModelRunPurpose,
    ModelRunStatus,
    ReviewDecision,
    ReviewDecisionType,
)


class FollowUpCaseNotFound(LookupError): ...


class FollowUpDraftNotFound(LookupError): ...


class FollowUpStateConflict(RuntimeError): ...


class FollowUpGenerationInProgress(RuntimeError): ...


class FollowUpVersionConflict(RuntimeError): ...


class ReviewDecisionConflict(RuntimeError): ...


class ApprovalBlockedByFindings(RuntimeError): ...


class FollowUpDraftRequired(RuntimeError): ...


class InvalidReviewedText(ValueError): ...


class RejectionReasonRequired(ValueError): ...


class ApprovalReasonNotAllowed(ValueError): ...


class FollowUpConfigurationError(RuntimeError): ...


class FollowUpPersistenceError(RuntimeError): ...


class ReviewPersistenceError(RuntimeError): ...


class FollowUpAttemptFailed(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class DraftResult:
    draft: FollowUpDraft
    created: bool


@dataclass(frozen=True, slots=True)
class DecisionResult:
    decision: ReviewDecision
    created: bool


class FollowUpService:
    def __init__(
        self,
        cases: CaseRepository,
        messages: SourceMessageRepository,
        documents: DocumentMetadataRepository,
        analyses: AnalysisRepository,
        validations: ValidationRepository,
        follow_ups: FollowUpRepository,
        audit: AuditEventRepository,
        drafter: FollowUpDrafter | None = None,
        *,
        lease_seconds: int,
        drafter_resolver: Callable[[], FollowUpDrafter] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._cases = cases
        self._messages = messages
        self._documents = documents
        self._analyses = analyses
        self._validations = validations
        self._follow_ups = follow_ups
        self._audit = audit
        self._drafter = drafter
        self._drafter_resolver = drafter_resolver
        self._lease_seconds = lease_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

    def generate(self, case_id: UUID) -> DraftResult:
        case = self._cases.get(case_id)
        if case is None:
            raise FollowUpCaseNotFound
        existing = self._follow_ups.get_draft(case_id)
        if existing is not None:
            return DraftResult(existing, created=False)
        if case.status is not CaseStatus.NEEDS_REVIEW or case.validation_completed_at is None:
            raise FollowUpStateConflict
        analysis = self._analyses.get_for_case(case_id)
        if analysis is None:
            raise FollowUpStateConflict
        messages = self._messages.list_for_case(case_id)
        documents = self._documents.list_for_case(case_id)
        checklist = self._validations.get_checklist(case_id)
        findings = self._validations.get_findings(case_id)
        started_at = self._clock()
        if self._follow_ups.generation_is_active(
            case_id, now=started_at, lease_seconds=self._lease_seconds
        ):
            raise FollowUpGenerationInProgress
        drafter = self._resolve_drafter()
        model = drafter.model
        prompt_version = drafter.prompt_version
        run = ModelRun(
            id=uuid4(),
            case_id=case_id,
            purpose=ModelRunPurpose.FOLLOW_UP_DRAFT,
            provider="openai",
            model=model,
            prompt_version=prompt_version,
            started_at=started_at,
            status=ModelRunStatus.IN_PROGRESS,
        )
        try:
            self._follow_ups.begin_generation(
                case_id, run, now=started_at, lease_seconds=self._lease_seconds
            )
        except FollowUpDraftExistsError as error:
            return DraftResult(error.draft, created=False)
        except FollowUpActiveAttemptError as error:
            raise FollowUpGenerationInProgress from error
        except FollowUpCaseNotFoundError as error:
            raise FollowUpCaseNotFound from error
        except FollowUpStateChangedError as error:
            raise FollowUpStateConflict from error
        except Exception as error:
            raise FollowUpPersistenceError from error

        try:
            result = drafter.draft(case, messages, documents, analysis, checklist, findings)
        except FollowUpDrafterError as error:
            code = (
                "follow_up_timeout"
                if error.code is DrafterErrorCode.TIMEOUT
                else "follow_up_provider_error"
            )
            failed = replace(
                run,
                status=ModelRunStatus.FAILED,
                completed_at=self._clock(),
                request_id=error.request_id,
                sanitized_error_code=error.code.value,
            )
            self._complete_failure(failed)
            raise FollowUpAttemptFailed(code) from error

        completed_at = self._clock()
        if isinstance(result, DraftingRefusal):
            refused = replace(
                run,
                status=ModelRunStatus.REFUSED,
                completed_at=completed_at,
                request_id=result.request_id,
                sanitized_error_code="refused",
            )
            self._complete_failure(refused, refused=True)
            raise FollowUpAttemptFailed("follow_up_refused")
        text = result.text.strip()
        if not text or len(text) > 4_000:
            invalid = replace(
                run,
                status=ModelRunStatus.FAILED,
                completed_at=completed_at,
                request_id=result.request_id,
                sanitized_error_code=DrafterErrorCode.NO_STRUCTURED_OUTPUT.value,
            )
            self._complete_failure(invalid)
            raise FollowUpAttemptFailed("follow_up_provider_error")
        draft = FollowUpDraft(
            id=uuid4(),
            case_id=case_id,
            language=case.output_language,
            model_text=text,
            reviewed_text=text,
            prompt_version=prompt_version,
            model_run_id=run.id,
            version=1,
            created_at=completed_at,
            updated_at=completed_at,
        )
        succeeded = replace(
            run,
            status=ModelRunStatus.SUCCEEDED,
            completed_at=completed_at,
            request_id=result.request_id,
        )
        try:
            self._follow_ups.complete_generation(succeeded, draft)
        except Exception as error:
            raise FollowUpPersistenceError from error
        return DraftResult(draft, created=True)

    def _resolve_drafter(self) -> FollowUpDrafter:
        if self._drafter is not None:
            return self._drafter
        if self._drafter_resolver is None:
            raise FollowUpConfigurationError
        try:
            return self._drafter_resolver()
        except FollowUpConfigurationError:
            raise
        except Exception as error:
            raise FollowUpConfigurationError from error

    def _complete_failure(self, run: ModelRun, *, refused: bool = False) -> None:
        try:
            self._follow_ups.complete_generation(run, None, refused=refused)
        except Exception as error:
            raise FollowUpPersistenceError from error

    def get_draft(self, case_id: UUID) -> FollowUpDraft:
        case = self._cases.get(case_id)
        if case is None:
            raise FollowUpCaseNotFound
        draft = self._follow_ups.get_draft(case_id)
        if draft is None:
            raise FollowUpDraftNotFound
        return draft

    def edit_draft(
        self, case_id: UUID, *, reviewed_text: str, expected_version: int
    ) -> FollowUpDraft:
        normalized = reviewed_text.strip()
        if not normalized or len(normalized) > 4_000:
            raise InvalidReviewedText
        try:
            return self._follow_ups.edit_draft(
                case_id,
                reviewed_text=normalized,
                expected_version=expected_version,
                edited_at=self._clock(),
            )
        except FollowUpCaseNotFoundError as error:
            raise FollowUpCaseNotFound from error
        except FollowUpDraftMissingError as error:
            raise FollowUpDraftNotFound from error
        except FollowUpVersionChangedError as error:
            raise FollowUpVersionConflict from error
        except FollowUpStateChangedError as error:
            raise FollowUpStateConflict from error
        except Exception as error:
            raise FollowUpPersistenceError from error

    def decide(
        self,
        case_id: UUID,
        *,
        decision: ReviewDecisionType,
        reason: str | None,
        reviewer_label: str,
    ) -> DecisionResult:
        label = reviewer_label.strip()
        if not label:
            raise ApprovalReasonNotAllowed("reviewer label is required")
        normalized_reason = reason.strip() if reason is not None else None
        normalized_reason = normalized_reason or None
        if decision is ReviewDecisionType.REJECTED and normalized_reason is None:
            raise RejectionReasonRequired
        if decision is ReviewDecisionType.APPROVED and normalized_reason is not None:
            raise ApprovalReasonNotAllowed
        existing = self._follow_ups.get_decision(case_id)
        if existing is not None:
            return self._resolve_existing(existing, decision, normalized_reason, label)
        case = self._cases.get(case_id)
        if case is None:
            raise FollowUpCaseNotFound
        if case.status is not CaseStatus.NEEDS_REVIEW:
            raise FollowUpStateConflict
        if self._follow_ups.get_draft(case_id) is None:
            raise FollowUpDraftRequired
        if decision is ReviewDecisionType.APPROVED and case.has_blocking_findings:
            raise ApprovalBlockedByFindings
        record = ReviewDecision(
            id=uuid4(),
            case_id=case_id,
            decision=decision,
            reason=normalized_reason,
            reviewer_label=label,
            created_at=self._clock(),
        )
        try:
            self._follow_ups.decide(case_id, decision=record, expected_updated_at=case.updated_at)
        except FollowUpDecisionExistsError as error:
            return self._resolve_existing(error.decision, decision, normalized_reason, label)
        except FollowUpApprovalBlockedError as error:
            raise ApprovalBlockedByFindings from error
        except FollowUpDraftMissingError as error:
            raise FollowUpDraftRequired from error
        except FollowUpStateChangedError as error:
            raise FollowUpStateConflict from error
        except Exception as error:
            raise ReviewPersistenceError from error
        return DecisionResult(record, created=True)

    @staticmethod
    def _resolve_existing(
        existing: ReviewDecision,
        decision: ReviewDecisionType,
        reason: str | None,
        label: str,
    ) -> DecisionResult:
        if (
            existing.decision is decision
            and existing.reason == reason
            and existing.reviewer_label == label
        ):
            return DecisionResult(existing, created=False)
        raise ReviewDecisionConflict

    def timeline(self, case_id: UUID) -> tuple[AuditEvent, ...]:
        if self._cases.get(case_id) is None:
            raise FollowUpCaseNotFound
        return self._audit.list_for_case(case_id)
