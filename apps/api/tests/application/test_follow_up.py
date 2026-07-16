"""Focused mapping tests for Block 6 application boundaries."""

from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from app.application.follow_up import (
    ApprovalBlockedByFindings,
    ApprovalReasonNotAllowed,
    FollowUpCaseNotFound,
    FollowUpConfigurationError,
    FollowUpDraftNotFound,
    FollowUpDraftRequired,
    FollowUpGenerationInProgress,
    FollowUpPersistenceError,
    FollowUpService,
    FollowUpStateConflict,
    FollowUpVersionConflict,
    InvalidReviewedText,
    ReviewPersistenceError,
)
from app.application.ports import (
    DrafterErrorCode,
    FakeFollowUpDrafter,
    FollowUpActiveAttemptError,
    FollowUpApprovalBlockedError,
    FollowUpCaseNotFoundError,
    FollowUpDecisionExistsError,
    FollowUpDrafterError,
    FollowUpDraftExistsError,
    FollowUpDraftMissingError,
    FollowUpStateChangedError,
    FollowUpVersionChangedError,
)
from app.domain import CaseStatus, ReviewDecision, ReviewDecisionType
from app.infrastructure.persistence.fixtures import FIXTURE_TIME, SYNTHETIC_CASE_FIXTURES


def harness() -> tuple[FollowUpService, dict[str, Mock]]:
    case = replace(
        SYNTHETIC_CASE_FIXTURES[0].case,
        status=CaseStatus.NEEDS_REVIEW,
        intake_analysis_id=uuid4(),
        validation_completed_at=FIXTURE_TIME + timedelta(minutes=2),
        validation_template_version="v1",
        updated_at=FIXTURE_TIME + timedelta(minutes=2),
    )
    mocks = {
        name: Mock()
        for name in (
            "cases",
            "messages",
            "documents",
            "analyses",
            "validations",
            "follow_ups",
            "audit",
        )
    }
    mocks["cases"].get.return_value = case
    mocks["analyses"].get_for_case.return_value = Mock()
    mocks["messages"].list_for_case.return_value = ()
    mocks["documents"].list_for_case.return_value = ()
    mocks["validations"].get_checklist.return_value = ()
    mocks["validations"].get_findings.return_value = ()
    mocks["follow_ups"].get_draft.return_value = None
    mocks["follow_ups"].get_decision.return_value = None
    mocks["follow_ups"].generation_is_active.return_value = False
    service = FollowUpService(
        mocks["cases"],
        mocks["messages"],
        mocks["documents"],
        mocks["analyses"],
        mocks["validations"],
        mocks["follow_ups"],
        mocks["audit"],
        FakeFollowUpDrafter(),
        lease_seconds=300,
        clock=lambda: FIXTURE_TIME + timedelta(minutes=3),
    )
    return service, mocks


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (FollowUpActiveAttemptError(), FollowUpGenerationInProgress),
        (FollowUpCaseNotFoundError(), FollowUpCaseNotFound),
        (FollowUpStateChangedError(), FollowUpStateConflict),
        (RuntimeError(), FollowUpPersistenceError),
    ],
)
def test_generation_start_errors_are_mapped(failure: Exception, expected: type[Exception]) -> None:
    service, mocks = harness()
    mocks["follow_ups"].begin_generation.side_effect = failure
    with pytest.raises(expected):
        service.generate(SYNTHETIC_CASE_FIXTURES[0].case.id)


def test_generation_requires_case_analysis_and_atomic_completion() -> None:
    service, mocks = harness()
    mocks["cases"].get.return_value = None
    with pytest.raises(FollowUpCaseNotFound):
        service.generate(uuid4())
    service, mocks = harness()
    mocks["analyses"].get_for_case.return_value = None
    with pytest.raises(FollowUpStateConflict):
        service.generate(SYNTHETIC_CASE_FIXTURES[0].case.id)
    service, mocks = harness()
    mocks["follow_ups"].complete_generation.side_effect = RuntimeError()
    with pytest.raises(FollowUpPersistenceError):
        service.generate(SYNTHETIC_CASE_FIXTURES[0].case.id)


def test_generation_returns_draft_created_by_a_concurrent_winner() -> None:
    service, mocks = harness()
    concurrent_draft = Mock()
    mocks["follow_ups"].begin_generation.side_effect = FollowUpDraftExistsError(concurrent_draft)

    result = service.generate(SYNTHETIC_CASE_FIXTURES[0].case.id)

    assert result.draft is concurrent_draft
    assert result.created is False


def test_generation_failure_persistence_error_is_not_hidden() -> None:
    _service, mocks = harness()

    drafter = Mock()
    drafter.model = "fake-follow-up"
    drafter.prompt_version = "follow-up-draft-v1"
    drafter.draft.side_effect = FollowUpDrafterError(DrafterErrorCode.TIMEOUT)

    service = FollowUpService(
        mocks["cases"],
        mocks["messages"],
        mocks["documents"],
        mocks["analyses"],
        mocks["validations"],
        mocks["follow_ups"],
        mocks["audit"],
        drafter,
        lease_seconds=300,
        clock=lambda: FIXTURE_TIME + timedelta(minutes=3),
    )
    mocks["follow_ups"].complete_generation.side_effect = RuntimeError("database unavailable")

    with pytest.raises(FollowUpPersistenceError):
        service.generate(SYNTHETIC_CASE_FIXTURES[0].case.id)


@pytest.mark.parametrize(
    ("resolver", "expected_cause"),
    [
        (None, None),
        (Mock(side_effect=RuntimeError("dependency unavailable")), RuntimeError),
        (Mock(side_effect=FollowUpConfigurationError()), FollowUpConfigurationError),
    ],
)
def test_late_drafter_resolution_maps_configuration_failures(
    resolver: Mock | None, expected_cause: type[Exception] | None
) -> None:
    _service, mocks = harness()
    service = FollowUpService(
        mocks["cases"],
        mocks["messages"],
        mocks["documents"],
        mocks["analyses"],
        mocks["validations"],
        mocks["follow_ups"],
        mocks["audit"],
        lease_seconds=300,
        drafter_resolver=resolver,
        clock=lambda: FIXTURE_TIME + timedelta(minutes=3),
    )

    with pytest.raises(FollowUpConfigurationError) as captured:
        service.generate(SYNTHETIC_CASE_FIXTURES[0].case.id)
    if expected_cause is None or expected_cause is FollowUpConfigurationError:
        assert captured.value.__cause__ is None
    else:
        assert isinstance(captured.value.__cause__, expected_cause)


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (FollowUpCaseNotFoundError(), FollowUpCaseNotFound),
        (FollowUpDraftMissingError(), FollowUpDraftNotFound),
        (FollowUpVersionChangedError(), FollowUpVersionConflict),
        (FollowUpStateChangedError(), FollowUpStateConflict),
        (RuntimeError(), FollowUpPersistenceError),
    ],
)
def test_edit_errors_are_mapped(failure: Exception, expected: type[Exception]) -> None:
    service, mocks = harness()
    mocks["follow_ups"].edit_draft.side_effect = failure
    with pytest.raises(expected):
        service.edit_draft(uuid4(), reviewed_text="valid", expected_version=1)


@pytest.mark.parametrize("reviewed_text", ["   ", "x" * 4_001])
def test_edit_rejects_text_outside_bounded_contract(reviewed_text: str) -> None:
    service, _mocks = harness()
    with pytest.raises(InvalidReviewedText):
        service.edit_draft(uuid4(), reviewed_text=reviewed_text, expected_version=1)


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (FollowUpApprovalBlockedError(), ApprovalBlockedByFindings),
        (FollowUpDraftMissingError(), FollowUpDraftRequired),
        (FollowUpStateChangedError(), FollowUpStateConflict),
        (RuntimeError(), ReviewPersistenceError),
    ],
)
def test_decision_errors_are_mapped(failure: Exception, expected: type[Exception]) -> None:
    service, mocks = harness()
    mocks["follow_ups"].get_draft.return_value = Mock()
    mocks["follow_ups"].decide.side_effect = failure
    with pytest.raises(expected):
        service.decide(
            SYNTHETIC_CASE_FIXTURES[0].case.id,
            decision=ReviewDecisionType.REJECTED,
            reason="reason",
            reviewer_label="Ana",
        )


def test_decision_validates_actor_case_and_state_before_persistence() -> None:
    service, mocks = harness()
    with pytest.raises(ApprovalReasonNotAllowed, match="reviewer label is required"):
        service.decide(
            uuid4(),
            decision=ReviewDecisionType.APPROVED,
            reason=None,
            reviewer_label="   ",
        )

    mocks["cases"].get.return_value = None
    with pytest.raises(FollowUpCaseNotFound):
        service.decide(
            uuid4(),
            decision=ReviewDecisionType.REJECTED,
            reason="reason",
            reviewer_label="Ana",
        )

    mocks["cases"].get.return_value = replace(
        SYNTHETIC_CASE_FIXTURES[0].case, status=CaseStatus.DRAFT
    )
    with pytest.raises(FollowUpStateConflict):
        service.decide(
            uuid4(),
            decision=ReviewDecisionType.REJECTED,
            reason="reason",
            reviewer_label="Ana",
        )


def test_decision_unique_race_reuses_semantically_identical_record() -> None:
    service, mocks = harness()
    case_id = SYNTHETIC_CASE_FIXTURES[0].case.id
    existing = ReviewDecision(
        id=uuid4(),
        case_id=case_id,
        decision=ReviewDecisionType.REJECTED,
        reason="reason",
        reviewer_label="Ana",
        created_at=FIXTURE_TIME + timedelta(minutes=3),
    )
    mocks["follow_ups"].get_draft.return_value = Mock()
    mocks["follow_ups"].decide.side_effect = FollowUpDecisionExistsError(existing)

    result = service.decide(
        case_id,
        decision=ReviewDecisionType.REJECTED,
        reason="reason",
        reviewer_label="Ana",
    )

    assert result.decision == existing
    assert result.created is False
