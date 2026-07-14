"""Integration tests for the complete Alembic lifecycle."""

from alembic import command
from sqlalchemy import create_engine, inspect

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
        assert revision == "20260713_0001"
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
