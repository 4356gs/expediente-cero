"""Integration coverage for the complete Block 6 workflow."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.api.routes.cases import follow_up_service
from app.application.follow_up import (
    FollowUpGenerationInProgress,
    FollowUpPersistenceError,
    FollowUpService,
    ReviewPersistenceError,
)
from app.application.ports import (
    DrafterErrorCode,
    DraftingRefusal,
    DraftingSuccess,
    FakeFollowUpDrafter,
    FollowUpCaseNotFoundError,
    FollowUpDrafterError,
    FollowUpDraftExistsError,
    FollowUpStateChangedError,
)
from app.core.config import Settings
from app.domain import (
    CaseStatus,
    ModelRun,
    ModelRunPurpose,
    ModelRunStatus,
    ReviewDecisionType,
)
from app.infrastructure.persistence import (
    SqliteAnalysisRepository,
    SqliteAuditEventRepository,
    SqliteCaseRepository,
    SqliteDocumentMetadataRepository,
    SqliteFollowUpRepository,
    SqliteSourceMessageRepository,
    SqliteValidationRepository,
)
from app.infrastructure.persistence import repositories as persistence_repositories
from app.infrastructure.persistence.fixtures import FIXTURE_TIME
from app.infrastructure.persistence.models import ModelRunModel, ValidationFindingModel
from app.main import create_app
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from tests.integration.test_validation_api import persist_analyzed_case


async def request(
    app: FastAPI, method: str, path: str, *, json: dict[str, Any] | None = None
) -> Response:
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, json=json)


def prepared_case(factory: sessionmaker[Session], index: int = 0) -> UUID:
    case_id = persist_analyzed_case(factory, index)
    app = create_app(Settings(environment="test"), session_factory=factory)
    response = asyncio.run(request(app, "POST", f"/cases/{case_id}/validation"))
    assert response.status_code == 200
    return case_id


def service(
    factory: sessionmaker[Session], *, drafter: Any | None = None, clock: Any | None = None
) -> FollowUpService:
    return FollowUpService(
        SqliteCaseRepository(factory),
        SqliteSourceMessageRepository(factory),
        SqliteDocumentMetadataRepository(factory),
        SqliteAnalysisRepository(factory),
        SqliteValidationRepository(factory),
        SqliteFollowUpRepository(factory),
        SqliteAuditEventRepository(factory),
        drafter or FakeFollowUpDrafter(),
        lease_seconds=300,
        clock=clock,
    )


def app_with_service(factory: sessionmaker[Session], value: FollowUpService) -> FastAPI:
    app = create_app(Settings(environment="test"), session_factory=factory)

    async def override() -> FollowUpService:
        return value

    app.dependency_overrides[follow_up_service] = override
    return app


@pytest.mark.parametrize("index", [0, 1, 2])
def test_generate_is_typed_and_idempotent_for_three_procedures(
    session_factory: sessionmaker[Session], index: int
) -> None:
    case_id = prepared_case(session_factory, index)
    app = app_with_service(session_factory, service(session_factory))

    created = asyncio.run(request(app, "POST", f"/cases/{case_id}/follow-up-draft"))
    repeated = asyncio.run(request(app, "POST", f"/cases/{case_id}/follow-up-draft"))
    fetched = asyncio.run(request(app, "GET", f"/cases/{case_id}/follow-up-draft"))

    assert created.status_code == 201
    assert repeated.status_code == fetched.status_code == 200
    assert created.json() == repeated.json() == fetched.json()
    assert created.json()["language"] in {"es", "gl"}
    assert created.json()["model_text"] == created.json()["reviewed_text"]
    assert created.json()["version"] == 1


def test_edit_normalization_versioning_noop_and_conflict(
    session_factory: sessionmaker[Session],
) -> None:
    case_id = prepared_case(session_factory)
    app = app_with_service(session_factory, service(session_factory))
    generated = asyncio.run(request(app, "POST", f"/cases/{case_id}/follow-up-draft"))

    changed = asyncio.run(
        request(
            app,
            "PATCH",
            f"/cases/{case_id}/follow-up-draft",
            json={"reviewed_text": "  Texto humano  ", "expected_version": 1},
        )
    )
    noop = asyncio.run(
        request(
            app,
            "PATCH",
            f"/cases/{case_id}/follow-up-draft",
            json={"reviewed_text": "Texto humano", "expected_version": 2},
        )
    )
    stale = asyncio.run(
        request(
            app,
            "PATCH",
            f"/cases/{case_id}/follow-up-draft",
            json={"reviewed_text": "Otro", "expected_version": 1},
        )
    )
    blank = asyncio.run(
        request(
            app,
            "PATCH",
            f"/cases/{case_id}/follow-up-draft",
            json={"reviewed_text": "   ", "expected_version": 2},
        )
    )
    assert changed.json()["reviewed_text"] == "Texto humano"
    assert changed.json()["version"] == noop.json()["version"] == 2
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "follow_up_version_conflict"
    assert blank.status_code == 422
    assert blank.json()["error"]["code"] == "invalid_reviewed_text"
    stored = SqliteFollowUpRepository(session_factory).get_draft(case_id)
    assert stored is not None
    assert stored.model_text == generated.json()["model_text"]


def test_rejection_idempotency_and_terminal_timeline(
    session_factory: sessionmaker[Session],
) -> None:
    case_id = prepared_case(session_factory)
    app = app_with_service(session_factory, service(session_factory))
    asyncio.run(request(app, "POST", f"/cases/{case_id}/follow-up-draft"))
    payload = {"decision": "rejected", "reason": "  Falta revisar  ", "actor": {"label": " Ana "}}

    missing_reason = asyncio.run(
        request(
            app,
            "POST",
            f"/cases/{case_id}/review-decision",
            json={"decision": "rejected", "reason": " ", "actor": {"label": "Ana"}},
        )
    )
    created = asyncio.run(request(app, "POST", f"/cases/{case_id}/review-decision", json=payload))
    repeated = asyncio.run(request(app, "POST", f"/cases/{case_id}/review-decision", json=payload))
    conflict = asyncio.run(
        request(
            app,
            "POST",
            f"/cases/{case_id}/review-decision",
            json={"decision": "rejected", "reason": "Otra", "actor": {"label": "Ana"}},
        )
    )
    timeline = asyncio.run(request(app, "GET", f"/cases/{case_id}/timeline"))

    assert missing_reason.status_code == 422
    assert missing_reason.json()["error"]["code"] == "rejection_reason_required"
    assert created.status_code == 201
    assert repeated.status_code == 200
    assert created.json() == repeated.json()
    assert created.json()["reason"] == "Falta revisar"
    assert created.json()["actor"]["label"] == "Ana"
    assert conflict.status_code == 409
    event_types = [item["event_type"] for item in timeline.json()["events"]]
    assert "review_rejected" in event_types
    assert event_types.count("case_status_changed") >= 4
    terminal = [
        item
        for item in timeline.json()["events"]
        if item["event_type"] in {"review_rejected", "case_status_changed"}
    ][-2:]
    assert terminal[0]["recorded_at"] == terminal[1]["recorded_at"]
    assert all(item["actor_label"] for item in timeline.json()["events"])
    assert "Falta revisar" not in timeline.text


def test_approval_validation_and_blockers(session_factory: sessionmaker[Session]) -> None:
    case_id = prepared_case(session_factory)
    app = app_with_service(session_factory, service(session_factory))
    asyncio.run(request(app, "POST", f"/cases/{case_id}/follow-up-draft"))
    with_reason = asyncio.run(
        request(
            app,
            "POST",
            f"/cases/{case_id}/review-decision",
            json={"decision": "approved", "reason": "why", "actor": {"label": "Ana"}},
        )
    )
    blocked = asyncio.run(
        request(
            app,
            "POST",
            f"/cases/{case_id}/review-decision",
            json={"decision": "approved", "actor": {"label": "Ana"}},
        )
    )
    assert with_reason.status_code == 422
    assert with_reason.json()["error"]["code"] == "request_validation_error"
    assert with_reason.json()["error"]["issues"] == []
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "approval_blocked_by_findings"

    with session_factory.begin() as session:
        session.query(ValidationFindingModel).filter_by(case_id=case_id).delete()
    approved = asyncio.run(
        request(
            app,
            "POST",
            f"/cases/{case_id}/review-decision",
            json={"decision": "approved", "reason": " ", "actor": {"label": "Ana"}},
        )
    )
    assert approved.status_code == 201
    assert approved.json()["reason"] is None


@pytest.mark.parametrize(
    ("drafter", "code", "status"),
    [
        (DraftingRefusal(request_id="refused"), "follow_up_refused", 502),
        (FollowUpDrafterError(DrafterErrorCode.TIMEOUT), "follow_up_timeout", 504),
        (
            FollowUpDrafterError(DrafterErrorCode.PROVIDER),
            "follow_up_provider_error",
            502,
        ),
        (
            FollowUpDrafterError(DrafterErrorCode.NO_STRUCTURED_OUTPUT),
            "follow_up_provider_error",
            502,
        ),
        (DraftingSuccess(text="   ", request_id="empty"), "follow_up_provider_error", 502),
        (DraftingSuccess(text="x" * 4_001, request_id="too-long"), "follow_up_provider_error", 502),
    ],
)
def test_generation_failures_are_audited_and_retryable(
    session_factory: sessionmaker[Session], drafter: Any, code: str, status: int
) -> None:
    case_id = prepared_case(session_factory)

    class ResultDrafter(FakeFollowUpDrafter):
        def draft(self, *args: Any) -> Any:
            if isinstance(drafter, Exception):
                raise drafter
            return drafter

    app = app_with_service(session_factory, service(session_factory, drafter=ResultDrafter()))
    response = asyncio.run(request(app, "POST", f"/cases/{case_id}/follow-up-draft"))
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert SqliteFollowUpRepository(session_factory).get_draft(case_id) is None
    events = SqliteAuditEventRepository(session_factory).list_for_case(case_id)
    assert {event.event_type.value for event in events} & {
        "follow_up_generation_failed",
        "follow_up_generation_refused",
    }

    retry = app_with_service(session_factory, service(session_factory))
    assert (
        asyncio.run(request(retry, "POST", f"/cases/{case_id}/follow-up-draft")).status_code == 201
    )


def test_active_attempt_and_exact_expiry_recovery(session_factory: sessionmaker[Session]) -> None:
    case_id = prepared_case(session_factory)
    repo = SqliteFollowUpRepository(session_factory)
    started = FIXTURE_TIME + timedelta(hours=2)
    old = ModelRun(
        id=uuid4(),
        case_id=case_id,
        purpose=ModelRunPurpose.FOLLOW_UP_DRAFT,
        provider="openai",
        model="gpt-5.6",
        prompt_version="follow-up-draft-v1",
        started_at=started,
        status=ModelRunStatus.IN_PROGRESS,
    )
    repo.begin_generation(case_id, old, now=started, lease_seconds=300)

    before = started + timedelta(seconds=299)
    active_app = app_with_service(session_factory, service(session_factory, clock=lambda: before))
    active = asyncio.run(request(active_app, "POST", f"/cases/{case_id}/follow-up-draft"))
    assert active.status_code == 409
    assert active.json()["error"]["code"] == "follow_up_generation_in_progress"

    boundary = started + timedelta(seconds=300)
    recovery_app = app_with_service(
        session_factory, service(session_factory, clock=lambda: boundary)
    )
    recovered = asyncio.run(request(recovery_app, "POST", f"/cases/{case_id}/follow-up-draft"))
    assert recovered.status_code == 201
    with session_factory() as session:
        abandoned = session.get(ModelRunModel, old.id)
        assert abandoned is not None
        assert abandoned.status == "failed"
        assert abandoned.sanitized_error_code == "follow_up_attempt_abandoned"
        runs = session.scalars(
            select(ModelRunModel).where(
                ModelRunModel.case_id == case_id,
                ModelRunModel.purpose == "follow_up_draft",
            )
        ).all()
        assert len(runs) == 2


def test_missing_state_and_required_record_errors(session_factory: sessionmaker[Session]) -> None:
    app = app_with_service(session_factory, service(session_factory))
    missing_id = uuid4()
    for method, suffix in (
        ("POST", "follow-up-draft"),
        ("GET", "follow-up-draft"),
        ("GET", "timeline"),
    ):
        response = asyncio.run(request(app, method, f"/cases/{missing_id}/{suffix}"))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "case_not_found"

    draft_case = prepared_case(session_factory)
    no_draft = asyncio.run(request(app, "GET", f"/cases/{draft_case}/follow-up-draft"))
    assert no_draft.status_code == 404
    assert no_draft.json()["error"]["code"] == "follow_up_draft_not_found"
    edit_missing = asyncio.run(
        request(
            app,
            "PATCH",
            f"/cases/{draft_case}/follow-up-draft",
            json={"reviewed_text": "valid", "expected_version": 1},
        )
    )
    assert edit_missing.status_code == 404
    decision_missing = asyncio.run(
        request(
            app,
            "POST",
            f"/cases/{draft_case}/review-decision",
            json={"decision": "rejected", "reason": "reason", "actor": {"label": "Ana"}},
        )
    )
    assert decision_missing.status_code == 409
    assert decision_missing.json()["error"]["code"] == "follow_up_draft_required"


def test_wrong_state_and_service_configuration_errors(
    session_factory: sessionmaker[Session],
) -> None:
    fixture_id = persist_analyzed_case(session_factory, 0)
    overridden = app_with_service(session_factory, service(session_factory))
    wrong_state = asyncio.run(request(overridden, "POST", f"/cases/{fixture_id}/follow-up-draft"))
    assert wrong_state.status_code == 409
    assert wrong_state.json()["error"]["code"] == "follow_up_state_conflict"

    unconfigured = create_app(Settings(environment="test"), session_factory=session_factory)
    still_wrong_state = asyncio.run(
        request(unconfigured, "POST", f"/cases/{fixture_id}/follow-up-draft")
    )
    assert still_wrong_state.status_code == 409
    assert still_wrong_state.json()["error"]["code"] == "follow_up_state_conflict"
    readable = asyncio.run(request(unconfigured, "GET", f"/cases/{fixture_id}/follow-up-draft"))
    assert readable.status_code == 404
    assert readable.json()["error"]["code"] == "follow_up_draft_not_found"

    missing = asyncio.run(request(unconfigured, "POST", f"/cases/{uuid4()}/follow-up-draft"))
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "case_not_found"

    ready_id = prepared_case(session_factory, 1)
    unavailable = asyncio.run(request(unconfigured, "POST", f"/cases/{ready_id}/follow-up-draft"))
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "follow_up_configuration_error"

    created = service(session_factory).generate(ready_id)
    idempotent = asyncio.run(request(unconfigured, "POST", f"/cases/{ready_id}/follow-up-draft"))
    assert idempotent.status_code == 200
    assert idempotent.json()["id"] == str(created.draft.id)

    active_id = prepared_case(session_factory, 2)
    now = datetime.now(UTC)
    active_run = ModelRun(
        id=uuid4(),
        case_id=active_id,
        purpose=ModelRunPurpose.FOLLOW_UP_DRAFT,
        provider="openai",
        model="gpt-5.6",
        prompt_version="follow-up-draft-v1",
        started_at=now,
        status=ModelRunStatus.IN_PROGRESS,
    )
    SqliteFollowUpRepository(session_factory).begin_generation(
        active_id, active_run, now=now, lease_seconds=300
    )
    active = asyncio.run(request(unconfigured, "POST", f"/cases/{active_id}/follow-up-draft"))
    assert active.status_code == 409
    assert active.json()["error"]["code"] == "follow_up_generation_in_progress"

    configured = create_app(
        Settings(environment="test", OPENAI_API_KEY="sk-synthetic"),
        session_factory=session_factory,
    )
    configured_missing = asyncio.run(
        request(configured, "GET", f"/cases/{uuid4()}/follow-up-draft")
    )
    assert configured_missing.status_code == 404


def test_only_one_concurrent_request_reclaims_expired_attempt(
    session_factory: sessionmaker[Session],
) -> None:
    case_id = prepared_case(session_factory)
    repo = SqliteFollowUpRepository(session_factory)
    started = FIXTURE_TIME + timedelta(hours=3)
    old = ModelRun(
        id=uuid4(),
        case_id=case_id,
        purpose=ModelRunPurpose.FOLLOW_UP_DRAFT,
        provider="openai",
        model="gpt-5.6",
        prompt_version="follow-up-draft-v1",
        started_at=started,
        status=ModelRunStatus.IN_PROGRESS,
    )
    repo.begin_generation(case_id, old, now=started, lease_seconds=300)
    entered = Event()
    release = Event()

    class BlockingDrafter(FakeFollowUpDrafter):
        def draft(self, *args: Any) -> Any:
            entered.set()
            assert release.wait(timeout=5)
            return super().draft(*args)

    boundary = started + timedelta(seconds=300)
    winner_service = service(session_factory, drafter=BlockingDrafter(), clock=lambda: boundary)
    loser_service = service(session_factory, clock=lambda: boundary)
    with ThreadPoolExecutor(max_workers=2) as executor:
        winner = executor.submit(winner_service.generate, case_id)
        assert entered.wait(timeout=5)
        loser = executor.submit(loser_service.generate, case_id)
        with pytest.raises(FollowUpGenerationInProgress):
            loser.result(timeout=5)
        release.set()
        assert winner.result(timeout=5).created is True


def test_repository_rechecks_generation_and_edit_preconditions(
    session_factory: sessionmaker[Session],
) -> None:
    repo = SqliteFollowUpRepository(session_factory)
    now = FIXTURE_TIME + timedelta(hours=7)

    def run(case_id: UUID) -> ModelRun:
        return ModelRun(
            id=uuid4(),
            case_id=case_id,
            purpose=ModelRunPurpose.FOLLOW_UP_DRAFT,
            provider="openai",
            model="gpt-5.6",
            prompt_version="follow-up-draft-v1",
            started_at=now,
            status=ModelRunStatus.IN_PROGRESS,
        )

    missing_id = uuid4()
    with pytest.raises(FollowUpCaseNotFoundError):
        repo.begin_generation(missing_id, run(missing_id), now=now, lease_seconds=300)
    with pytest.raises(FollowUpCaseNotFoundError):
        repo.edit_draft(missing_id, reviewed_text="edit", expected_version=1, edited_at=now)

    wrong_state_id = persist_analyzed_case(session_factory, 0)
    with pytest.raises(FollowUpStateChangedError):
        repo.begin_generation(wrong_state_id, run(wrong_state_id), now=now, lease_seconds=300)
    with pytest.raises(FollowUpStateChangedError):
        repo.edit_draft(wrong_state_id, reviewed_text="edit", expected_version=1, edited_at=now)

    drafted_id = prepared_case(session_factory, 1)
    service(session_factory, clock=lambda: now).generate(drafted_id)
    with pytest.raises(FollowUpDraftExistsError) as captured:
        repo.begin_generation(drafted_id, run(drafted_id), now=now, lease_seconds=300)
    assert captured.value.draft.case_id == drafted_id


def test_generation_start_rolls_back_when_audit_build_fails(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = prepared_case(session_factory)
    repo = SqliteFollowUpRepository(session_factory)
    now = FIXTURE_TIME + timedelta(hours=4)
    run = ModelRun(
        id=uuid4(),
        case_id=case_id,
        purpose=ModelRunPurpose.FOLLOW_UP_DRAFT,
        provider="openai",
        model="gpt-5.6",
        prompt_version="follow-up-draft-v1",
        started_at=now,
        status=ModelRunStatus.IN_PROGRESS,
    )

    def fail_audit(_event: Any) -> Any:
        raise RuntimeError("audit failure")

    monkeypatch.setattr("app.infrastructure.persistence.repositories._audit_to_model", fail_audit)
    with pytest.raises(RuntimeError, match="audit failure"):
        repo.begin_generation(case_id, run, now=now, lease_seconds=300)
    with session_factory() as session:
        assert session.get(ModelRunModel, run.id) is None


def test_expired_attempt_recovery_rolls_back_completely(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = prepared_case(session_factory)
    repo = SqliteFollowUpRepository(session_factory)
    started = FIXTURE_TIME + timedelta(hours=5)
    expired = ModelRun(
        id=uuid4(),
        case_id=case_id,
        purpose=ModelRunPurpose.FOLLOW_UP_DRAFT,
        provider="openai",
        model="gpt-5.6",
        prompt_version="follow-up-draft-v1",
        started_at=started,
        status=ModelRunStatus.IN_PROGRESS,
    )
    repo.begin_generation(case_id, expired, now=started, lease_seconds=300)
    events_before = SqliteAuditEventRepository(session_factory).list_for_case(case_id)
    replacement = replace(expired, id=uuid4(), started_at=started + timedelta(seconds=300))
    original_audit_to_model = persistence_repositories._audit_to_model
    calls = 0

    def fail_second_audit(event: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("recovery audit failure")
        return original_audit_to_model(event)

    monkeypatch.setattr(persistence_repositories, "_audit_to_model", fail_second_audit)
    with pytest.raises(RuntimeError, match="recovery audit failure"):
        repo.begin_generation(
            case_id,
            replacement,
            now=replacement.started_at,
            lease_seconds=300,
        )

    with session_factory() as session:
        original = session.get(ModelRunModel, expired.id)
        assert original is not None
        assert original.status == ModelRunStatus.IN_PROGRESS.value
        assert original.completed_at is None
        assert original.sanitized_error_code is None
        assert session.get(ModelRunModel, replacement.id) is None
    events_after = SqliteAuditEventRepository(session_factory).list_for_case(case_id)
    assert events_after == events_before


def test_edit_rolls_back_when_audit_fails(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = prepared_case(session_factory)
    workflow = service(session_factory)
    original = workflow.generate(case_id).draft

    def fail_audit(_event: Any) -> Any:
        raise RuntimeError("audit failure")

    monkeypatch.setattr("app.infrastructure.persistence.repositories._audit_to_model", fail_audit)
    with pytest.raises(FollowUpPersistenceError):
        workflow.edit_draft(case_id, reviewed_text="changed", expected_version=1)
    stored = SqliteFollowUpRepository(session_factory).get_draft(case_id)
    assert stored is not None
    assert stored.reviewed_text == original.reviewed_text
    assert stored.version == 1


def test_decision_rolls_back_when_audit_fails(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = prepared_case(session_factory)
    workflow = service(session_factory)
    workflow.generate(case_id)

    def fail_audit(_event: Any) -> Any:
        raise RuntimeError("audit failure")

    monkeypatch.setattr("app.infrastructure.persistence.repositories._audit_to_model", fail_audit)
    with pytest.raises(ReviewPersistenceError):
        workflow.decide(
            case_id,
            decision=ReviewDecisionType.REJECTED,
            reason="reason",
            reviewer_label="Ana",
        )
    after = SqliteCaseRepository(session_factory).get(case_id)
    assert after is not None
    assert after.status is CaseStatus.NEEDS_REVIEW
    assert after.review_decision is None
