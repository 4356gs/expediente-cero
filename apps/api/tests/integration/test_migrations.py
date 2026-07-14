"""Integration tests for the complete Alembic lifecycle."""

import pytest
from alembic import command
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
        assert revision == "20260714_0002"
        constraints = {item["name"] for item in inspect(engine).get_check_constraints("cases")}
        assert "ck_cases_analyzed_requires_analysis" in constraints
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
