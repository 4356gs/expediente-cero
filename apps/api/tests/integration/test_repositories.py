"""Integration tests for SQLite repository behavior and transactionality."""

from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest
from app.domain import ActorType, CaseStatus, ProcedureType
from app.infrastructure.persistence import (
    SqliteAuditEventRepository,
    SqliteCaseRepository,
    SqliteDocumentMetadataRepository,
    SqliteSourceMessageRepository,
)
from app.infrastructure.persistence.fixtures import FIXTURE_TIME, SYNTHETIC_CASE_FIXTURES
from app.infrastructure.persistence.models import AuditEventModel
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker


def _repositories(
    session_factory: sessionmaker[Session],
) -> tuple[
    SqliteCaseRepository,
    SqliteAuditEventRepository,
    SqliteSourceMessageRepository,
    SqliteDocumentMetadataRepository,
]:
    return (
        SqliteCaseRepository(session_factory),
        SqliteAuditEventRepository(session_factory),
        SqliteSourceMessageRepository(session_factory),
        SqliteDocumentMetadataRepository(session_factory),
    )


def test_three_synthetic_fixtures_round_trip_through_repositories(
    session_factory: sessionmaker[Session],
) -> None:
    cases, _audit, messages, documents = _repositories(session_factory)

    for fixture in SYNTHETIC_CASE_FIXTURES:
        cases.add(fixture.case)
        for message in fixture.source_messages:
            messages.add(message)
        for document in fixture.documents:
            documents.add(document)

    stored_cases = cases.list()
    assert tuple(case.procedure_type for case in stored_cases) == tuple(ProcedureType)
    for fixture in SYNTHETIC_CASE_FIXTURES:
        assert cases.get(fixture.case.id) == fixture.case
        assert messages.list_for_case(fixture.case.id) == fixture.source_messages
        assert documents.list_for_case(fixture.case.id) == fixture.documents
        assert all(message.is_synthetic for message in fixture.source_messages)
        assert all(document.is_synthetic for document in fixture.documents)


def test_add_intake_rolls_back_every_record_on_unexpected_child_conflict(
    session_factory: sessionmaker[Session],
) -> None:
    cases, _audit, messages, documents = _repositories(session_factory)
    first = SYNTHETIC_CASE_FIXTURES[0]
    second = SYNTHETIC_CASE_FIXTURES[1]
    cases.add_intake(first.case, first.source_messages, first.documents)
    conflicting_message = replace(
        second.source_messages[0],
        id=first.source_messages[0].id,
    )

    with pytest.raises(IntegrityError):
        cases.add_intake(second.case, (conflicting_message,), second.documents)

    assert cases.get(second.case.id) is None
    assert messages.list_for_case(second.case.id) == ()
    assert documents.list_for_case(second.case.id) == ()


def test_transition_and_audit_event_are_persisted_together(
    session_factory: sessionmaker[Session],
) -> None:
    cases, audit, _messages, _documents = _repositories(session_factory)
    case = SYNTHETIC_CASE_FIXTURES[0].case
    cases.add(case)
    occurred_at = FIXTURE_TIME + timedelta(minutes=1)

    outcome = cases.transition(
        case.id,
        CaseStatus.ANALYZING,
        actor_type=ActorType.SYSTEM,
        actor_label="workflow",
        occurred_at=occurred_at,
    )

    stored = cases.get(case.id)
    assert stored is not None
    assert stored.status is CaseStatus.ANALYZING
    assert stored.updated_at == occurred_at
    assert audit.list_for_case(case.id) == (outcome.audit_event,)


def test_audit_failure_rolls_back_the_state_transition(
    session_factory: sessionmaker[Session],
) -> None:
    cases, audit, _messages, _documents = _repositories(session_factory)
    case = SYNTHETIC_CASE_FIXTURES[0].case
    duplicate_event_id = UUID("30000000-0000-0000-0000-000000000001")
    cases.add(case)
    cases.transition(
        case.id,
        CaseStatus.ANALYZING,
        actor_type=ActorType.SYSTEM,
        actor_label="workflow",
        occurred_at=FIXTURE_TIME + timedelta(minutes=1),
        audit_event_id=duplicate_event_id,
    )

    with pytest.raises(IntegrityError):
        cases.transition(
            case.id,
            CaseStatus.ANALYSIS_FAILED,
            actor_type=ActorType.SYSTEM,
            actor_label="workflow",
            occurred_at=FIXTURE_TIME + timedelta(minutes=2),
            audit_event_id=duplicate_event_id,
        )

    stored = cases.get(case.id)
    assert stored is not None
    assert stored.status is CaseStatus.ANALYZING
    assert len(audit.list_for_case(case.id)) == 1


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_audit_rows_are_database_enforced_append_only(
    session_factory: sessionmaker[Session], operation: str
) -> None:
    cases, audit, _messages, _documents = _repositories(session_factory)
    case = SYNTHETIC_CASE_FIXTURES[0].case
    cases.add(case)
    outcome = cases.transition(
        case.id,
        CaseStatus.ANALYZING,
        actor_type=ActorType.SYSTEM,
        actor_label="workflow",
        occurred_at=FIXTURE_TIME + timedelta(minutes=1),
    )

    with pytest.raises(IntegrityError, match="append-only"), session_factory.begin() as session:
        statement = (
            update(AuditEventModel)
            .where(AuditEventModel.id == outcome.audit_event.id)
            .values(actor_label="changed")
            if operation == "update"
            else delete(AuditEventModel).where(AuditEventModel.id == outcome.audit_event.id)
        )
        session.execute(statement)

    assert audit.list_for_case(case.id) == (outcome.audit_event,)
