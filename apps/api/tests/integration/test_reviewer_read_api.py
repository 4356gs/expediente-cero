"""Integration coverage for reloadable, provider-free reviewer reads."""

import asyncio
from uuid import uuid4

import pytest
from app.core.config import Settings
from app.infrastructure.persistence import SqliteCaseRepository
from app.infrastructure.persistence.fixtures import SYNTHETIC_CASE_FIXTURES
from app.infrastructure.persistence.models import ValidationFindingModel
from app.main import create_app
from sqlalchemy.orm import Session, sessionmaker

from tests.integration.test_follow_up_api import (
    app_with_service,
    prepared_case,
    request,
    service,
)
from tests.integration.test_validation_api import persist_analyzed_case


def test_analysis_read_round_trips_persisted_model_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    case_id = persist_analyzed_case(session_factory, 2)
    app = create_app(Settings(environment="test"), session_factory=session_factory)

    response = asyncio.run(request(app, "GET", f"/cases/{case_id}/analysis"))

    assert response.status_code == 200
    body = response.json()
    assert body["case_id"] == str(case_id)
    assert body["procedure_type"] == "grant_application"
    assert body["requested_output_language"] in {"es", "gl"}
    assert body["prompt_version"] == "intake-analysis-test-v2"
    assert [item["field"] for item in body["facts"]] == [
        "applicant_name",
        "grant_program",
        "project_summary",
    ]


@pytest.mark.parametrize("index", [0, 1, 2])
def test_validation_read_reconstructs_all_three_procedures_without_provider(
    session_factory: sessionmaker[Session], index: int
) -> None:
    case_id = prepared_case(session_factory, index)
    app = create_app(Settings(environment="test"), session_factory=session_factory)

    response = asyncio.run(request(app, "GET", f"/cases/{case_id}/validation-result"))

    assert response.status_code == 200
    body = response.json()
    assert body["template_version"] == "deterministic-validation-v1"
    assert body["validation_completed_at"]
    assert body["checklist_results"]
    assert body["findings"]
    assert body["has_blocking_findings"] is True


def test_validation_read_reports_non_blocking_snapshot(
    session_factory: sessionmaker[Session],
) -> None:
    case_id = prepared_case(session_factory, 0)
    with session_factory.begin() as session:
        session.query(ValidationFindingModel).filter_by(case_id=case_id).delete()
    app = create_app(Settings(environment="test"), session_factory=session_factory)

    response = asyncio.run(request(app, "GET", f"/cases/{case_id}/validation-result"))

    assert response.status_code == 200
    assert response.json()["has_blocking_findings"] is False
    assert response.json()["findings"] == []


def test_decision_read_returns_immutable_human_record(
    session_factory: sessionmaker[Session],
) -> None:
    case_id = prepared_case(session_factory, 0)
    app = app_with_service(session_factory, service(session_factory))
    assert asyncio.run(request(app, "POST", f"/cases/{case_id}/follow-up-draft")).status_code == 201
    payload = {
        "decision": "rejected",
        "reason": "Revisión sintética incompleta",
        "actor": {"label": "Ana"},
    }
    assert (
        asyncio.run(
            request(app, "POST", f"/cases/{case_id}/review-decision", json=payload)
        ).status_code
        == 201
    )

    response = asyncio.run(request(app, "GET", f"/cases/{case_id}/review-decision"))

    assert response.status_code == 200
    assert response.json()["decision"] == "rejected"
    assert response.json()["reason"] == "Revisión sintética incompleta"
    assert response.json()["actor"] == {"label": "Ana"}


def test_read_endpoints_distinguish_absent_case_and_absent_artifacts(
    session_factory: sessionmaker[Session],
) -> None:
    app = create_app(Settings(environment="test"), session_factory=session_factory)
    missing_id = uuid4()
    for suffix in ("analysis", "validation-result", "review-decision"):
        response = asyncio.run(request(app, "GET", f"/cases/{missing_id}/{suffix}"))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "case_not_found"

    fixture = SYNTHETIC_CASE_FIXTURES[0]
    SqliteCaseRepository(session_factory).add_intake(
        fixture.case, fixture.source_messages, fixture.documents
    )
    expected_codes = {
        "analysis": "analysis_not_found",
        "validation-result": "validation_result_not_found",
        "review-decision": "review_decision_not_found",
    }
    for suffix, code in expected_codes.items():
        response = asyncio.run(request(app, "GET", f"/cases/{fixture.case.id}/{suffix}"))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == code
