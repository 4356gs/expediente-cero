"""Block 6 domain and configuration invariants."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.core.config import Settings
from app.domain import (
    DomainInvariantError,
    FollowUpDraft,
    ModelRun,
    ModelRunPurpose,
    ModelRunStatus,
    OutputLanguage,
    ReviewDecision,
    ReviewDecisionType,
)
from pydantic import ValidationError

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


def run(status: ModelRunStatus, completed_at: datetime | None) -> ModelRun:
    return ModelRun(
        id=uuid4(),
        case_id=uuid4(),
        purpose=ModelRunPurpose.FOLLOW_UP_DRAFT,
        provider="openai",
        model="gpt-5.6",
        prompt_version="follow-up-draft-v1",
        started_at=NOW,
        status=status,
        completed_at=completed_at,
    )


def test_model_run_completion_matches_lifecycle() -> None:
    assert run(ModelRunStatus.IN_PROGRESS, None).completed_at is None
    for status in (
        ModelRunStatus.SUCCEEDED,
        ModelRunStatus.FAILED,
        ModelRunStatus.REFUSED,
    ):
        assert run(status, NOW).completed_at == NOW
    with pytest.raises(DomainInvariantError, match="in-progress"):
        run(ModelRunStatus.IN_PROGRESS, NOW)
    with pytest.raises(DomainInvariantError, match="terminal"):
        run(ModelRunStatus.FAILED, None)


def test_review_decision_normalizes_and_restricts_reason() -> None:
    approved = ReviewDecision(
        id=uuid4(),
        case_id=uuid4(),
        decision=ReviewDecisionType.APPROVED,
        reviewer_label="  Ana  ",
        reason="   ",
        created_at=NOW,
    )
    assert approved.reviewer_label == "Ana"
    assert approved.reason is None
    with pytest.raises(DomainInvariantError, match="approval cannot"):
        ReviewDecision(
            id=uuid4(),
            case_id=uuid4(),
            decision=ReviewDecisionType.APPROVED,
            reviewer_label="Ana",
            reason="because",
            created_at=NOW,
        )
    with pytest.raises(DomainInvariantError, match="rejection requires"):
        ReviewDecision(
            id=uuid4(),
            case_id=uuid4(),
            decision=ReviewDecisionType.REJECTED,
            reviewer_label="Ana",
            reason=" ",
            created_at=NOW,
        )


def test_follow_up_lease_must_exceed_openai_timeout() -> None:
    settings = Settings(
        environment="test", openai_timeout_seconds=30, follow_up_attempt_lease_seconds=31
    )
    assert settings.follow_up_attempt_lease_seconds == 31
    with pytest.raises(ValidationError, match="lease must exceed"):
        Settings(
            environment="test",
            openai_timeout_seconds=30,
            follow_up_attempt_lease_seconds=30,
        )


def test_follow_up_draft_rejects_text_over_4000_characters() -> None:
    with pytest.raises(DomainInvariantError, match="4000"):
        FollowUpDraft(
            id=uuid4(),
            case_id=uuid4(),
            language=OutputLanguage.SPANISH,
            model_text="x" * 4_001,
            reviewed_text="x",
            prompt_version="follow-up-draft-v1",
            model_run_id=uuid4(),
            created_at=NOW,
            updated_at=NOW,
        )
