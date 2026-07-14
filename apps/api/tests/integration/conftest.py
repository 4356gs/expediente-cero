"""Database fixtures for repository integration tests."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.infrastructure.persistence import create_session_factory, create_sqlite_engine
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker


def alembic_config(database_url: str) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(root / "alembic.ini")
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'integration.sqlite3'}"


@pytest.fixture
def migrated_engine(database_url: str) -> Iterator[Engine]:
    command.upgrade(alembic_config(database_url), "head")
    engine = create_sqlite_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(migrated_engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(migrated_engine)
