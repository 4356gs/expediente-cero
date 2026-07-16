"""Focused mapping tests for Block 6 application boundaries."""

from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from app.application.follow_up import (
    ApprovalBlockedByFindings,
    FollowUpCaseNotFound,
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
    FakeFollowUpDrafter,
    FollowUpActiveAttemptError,
    FollowUpApprovalBlockedError,
    FollowUpCaseNotFoundError,
    FollowUpDraftMissingError,
    FollowUpStateChangedError,
    FollowUpVersionChangedError,
)
from app.domain import CaseStatus, ReviewDecisionType
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
