"""Integration tests for the complete Alembic lifecycle."""

import pytest
from alembic import command
from app.infrastructure.persistence.models import Base
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError

from tests.integration.conftest import alembic_config

EXPECTED_TABLES = {
    "alembic_version",
    "audit_events",
    "cases",
    "checklist_results",
    "document_metadata",
    "follow_up_drafts",
    "intake_analyses",
    "model_runs",
    "review_decisions",
    "source_messages",
    "validation_findings",
}


def test_initial_migration_upgrades_a_blank_database(database_url: str) -> None:
    config = alembic_config(database_url)
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES
        with engine.connect() as connection:
            revision = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar()
        assert revision == "20260715_0004"
        constraints = {item["name"] for item in inspect(engine).get_check_constraints("cases")}
        assert "ck_cases_analyzed_requires_analysis" in constraints
        assert "ck_cases_validation_pair" in constraints
        assert "ck_cases_review_requires_validation" in constraints
        draft_columns = {item["name"] for item in inspect(engine).get_columns("follow_up_drafts")}
        assert "version" in draft_columns
        model_indexes = {item["name"] for item in inspect(engine).get_indexes("model_runs")}
        assert "uq_model_runs_active_follow_up_case" in model_indexes
    finally:
        engine.dispose()


def test_initial_migration_can_downgrade_and_upgrade_again(database_url: str) -> None:
    config = alembic_config(database_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = create_engine(database_url)
    try:
        assert inspect(engine).get_table_names() == ["alembic_version"]
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES
    finally:
        engine.dispose()


def test_follow_up_migration_upgrades_previous_revision(database_url: str) -> None:
    config = alembic_config(database_url)
    command.upgrade(config, "20260714_0003")
    engine = create_engine(database_url)
    try:
        assert "version" not in {
            item["name"] for item in inspect(engine).get_columns("follow_up_drafts")
        }
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        assert "version" in {
            item["name"] for item in inspect(engine).get_columns("follow_up_drafts")
        }
        assert "uq_model_runs_active_follow_up_case" in {
            item["name"] for item in inspect(engine).get_indexes("model_runs")
        }
    finally:
        engine.dispose()


def test_follow_up_constraints_match_alembic_and_orm_metadata(database_url: str) -> None:
    config = alembic_config(database_url)
    command.upgrade(config, "head")
    alembic_engine = create_engine(database_url)
    metadata_engine = create_engine("sqlite://")
    try:
        Base.metadata.create_all(metadata_engine)
        alembic_inspector = inspect(alembic_engine)
        metadata_inspector = inspect(metadata_engine)
        for table, expected_check in (
            ("follow_up_drafts", "ck_follow_up_drafts_version_positive"),
            ("model_runs", "ck_model_runs_completion_by_status"),
        ):
            alembic_checks = {
                item["name"] for item in alembic_inspector.get_check_constraints(table)
            }
            metadata_checks = {
                item["name"] for item in metadata_inspector.get_check_constraints(table)
            }
            assert expected_check in alembic_checks == metadata_checks
        assert "uq_model_runs_active_follow_up_case" in {
            item["name"] for item in metadata_inspector.get_indexes("model_runs")
        }
        version = next(
            item
            for item in metadata_inspector.get_columns("follow_up_drafts")
            if item["name"] == "version"
        )
        assert version["default"] == "1"
    finally:
        alembic_engine.dispose()
        metadata_engine.dispose()


def test_follow_up_migration_preserves_populated_previous_revision(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    command.upgrade(config, "20260714_0003")
    engine = create_engine(database_url)
    case_id = "31000000000000000000000000000001"
    run_id = "32000000000000000000000000000001"
    draft_id = "33000000000000000000000000000001"
    event_id = "34000000000000000000000000000001"
    timestamp = "2026-07-15 10:00:00"
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO cases "
                "(id, reference, procedure_type, output_language, status, created_at, updated_at, "
                "intake_analysis_id, validation_completed_at, validation_template_version) "
                "VALUES (?, 'EC-B6-MIGRATION', 'grant_application', 'gl', 'needs_review', ?, ?, "
                "?, ?, 'validation-v1')",
                (case_id, timestamp, timestamp, "35000000000000000000000000000001", timestamp),
            )
            connection.exec_driver_sql(
                "INSERT INTO model_runs "
                "(id, case_id, purpose, provider, model, prompt_version, started_at, "
                "completed_at, status, request_id, sanitized_error_code) "
                "VALUES (?, ?, 'follow_up_draft', 'openai', 'gpt-5.6', "
                "'follow-up-draft-v1', ?, ?, 'succeeded', 'req-existing', NULL)",
                (run_id, case_id, timestamp, timestamp),
            )
            connection.exec_driver_sql(
                "INSERT INTO follow_up_drafts "
                "(id, case_id, language, model_text, reviewed_text, prompt_version, model_run_id, "
                "created_at, updated_at) VALUES (?, ?, 'gl', 'Modelo', 'Revisado', "
                "'follow-up-draft-v1', ?, ?, ?)",
                (draft_id, case_id, run_id, timestamp, timestamp),
            )
            connection.exec_driver_sql(
                "INSERT INTO audit_events "
                "(id, case_id, event_type, actor_type, actor_label, recorded_at, "
                "sanitized_metadata) VALUES (?, ?, 'case_status_changed', 'system', "
                "'migration-test', ?, '{}')",
                (event_id, case_id, timestamp),
            )
    finally:
        engine.dispose()

    command.upgrade(config, "20260715_0004")
    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        assert {
            "ck_follow_up_drafts_version_positive",
        } <= {item["name"] for item in inspector.get_check_constraints("follow_up_drafts")}
        assert "ck_model_runs_completion_by_status" in {
            item["name"] for item in inspector.get_check_constraints("model_runs")
        }
        assert "uq_model_runs_active_follow_up_case" in {
            item["name"] for item in inspector.get_indexes("model_runs")
        }
        with engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT model_text, reviewed_text, version FROM follow_up_drafts WHERE id = ?",
                (draft_id,),
            ).one() == ("Modelo", "Revisado", 1)
            assert (
                connection.exec_driver_sql(
                    "SELECT status FROM model_runs WHERE id = ?", (run_id,)
                ).scalar_one()
                == "succeeded"
            )
            assert (
                connection.exec_driver_sql(
                    "SELECT actor_label FROM audit_events WHERE id = ?", (event_id,)
                ).scalar_one()
                == "migration-test"
            )
    finally:
        engine.dispose()

    command.downgrade(config, "20260714_0003")
    engine = create_engine(database_url)
    try:
        assert "version" not in {
            item["name"] for item in inspect(engine).get_columns("follow_up_drafts")
        }
        with engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT model_text, reviewed_text FROM follow_up_drafts WHERE id = ?", (draft_id,)
            ).one() == ("Modelo", "Revisado")
            assert (
                connection.exec_driver_sql(
                    "SELECT status FROM model_runs WHERE id = ?", (run_id,)
                ).scalar_one()
                == "succeeded"
            )
            assert (
                connection.exec_driver_sql(
                    "SELECT actor_label FROM audit_events WHERE id = ?", (event_id,)
                ).scalar_one()
                == "migration-test"
            )
    finally:
        engine.dispose()


def test_analyzed_migration_upgrades_populated_block3_database(database_url: str) -> None:
    config = alembic_config(database_url)
    command.upgrade(config, "20260713_0001")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO cases "
                "(id, reference, procedure_type, output_language, status, created_at, updated_at) "
                "VALUES ('10000000000000000000000000000001', 'EC-MIGRATION', "
                "'grant_application', 'gl', 'draft', "
                "'2026-07-13 12:00:00', '2026-07-13 12:00:00')"
            )
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert (
                connection.exec_driver_sql(
                    "SELECT status FROM cases WHERE reference = 'EC-MIGRATION'"
                ).scalar()
                == "draft"
            )
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE cases SET status = 'analyzed', intake_analysis_id = NULL "
                "WHERE reference = 'EC-MIGRATION'"
            )
    finally:
        engine.dispose()

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE cases SET status = 'analyzed', "
                "intake_analysis_id = '20000000000000000000000000000001' "
                "WHERE reference = 'EC-MIGRATION'"
            )
    finally:
        engine.dispose()
    command.downgrade(config, "20260713_0001")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert (
                connection.exec_driver_sql(
                    "SELECT status FROM cases WHERE reference = 'EC-MIGRATION'"
                ).scalar()
                == "analysis_failed"
            )
    finally:
        engine.dispose()
    command.upgrade(config, "head")
