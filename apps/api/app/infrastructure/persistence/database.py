"""Engine and session construction for SQLite persistence."""

from pathlib import Path
from sqlite3 import Connection as SQLiteConnection
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker


def _enable_sqlite_foreign_keys(
    dbapi_connection: Any,
    _connection_record: Any,
) -> None:
    if isinstance(dbapi_connection, SQLiteConnection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_sqlite_engine(database_url: str, *, echo: bool = False) -> Engine:
    """Create a SQLite engine with foreign-key enforcement enabled."""
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        raise ValueError("the MVP persistence adapter requires a SQLite URL")
    if url.database and url.database != ":memory:":
        Path(url.database).expanduser().parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(database_url, echo=echo)
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return sessions that never expire loaded values after commit."""
    return sessionmaker(bind=engine, expire_on_commit=False)
