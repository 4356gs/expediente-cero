"""Integration coverage for the protected demo data lifecycle."""

import json
from pathlib import Path

import pytest
from app import demo
from app.core.config import Settings
from app.demo import DemoSafetyError, demo_status, reset_demo, seed_demo
from app.infrastructure.persistence import create_session_factory, create_sqlite_engine
from app.infrastructure.persistence.models import CaseModel
from sqlalchemy import func, select


def demo_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="demo",
        database_url=f"sqlite:///{tmp_path / 'demo.sqlite3'}",
    )


def case_count(settings: Settings) -> int:
    engine = create_sqlite_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        with factory() as session:
            return session.scalar(select(func.count()).select_from(CaseModel)) or 0
    finally:
        engine.dispose()


def test_seed_is_idempotent_and_status_is_stable(tmp_path: Path) -> None:
    settings = demo_settings(tmp_path)

    first = seed_demo(settings)
    second = seed_demo(settings)
    statuses = demo_status(settings)

    assert (first.seeded, first.existing, first.total) == (3, 0, 3)
    assert (second.seeded, second.existing, second.total) == (0, 3, 3)
    assert [item.reference for item in statuses] == [
        "EC-DEMO-001",
        "EC-DEMO-002",
        "EC-DEMO-003",
    ]
    assert {item.status for item in statuses} == {"draft"}


def test_reset_requires_demo_environment_and_exact_confirmation(tmp_path: Path) -> None:
    development = Settings(database_url=f"sqlite:///{tmp_path / 'development.sqlite3'}")
    demo = demo_settings(tmp_path)

    with pytest.raises(DemoSafetyError, match="ENVIRONMENT=demo"):
        seed_demo(development)
    with pytest.raises(DemoSafetyError, match="RESET-DEMO-DATA"):
        reset_demo(demo, "yes")


def test_reset_rebuilds_and_reseeds_the_demo_database(tmp_path: Path) -> None:
    settings = demo_settings(tmp_path)
    seed_demo(settings)
    assert case_count(settings) == 3

    result = reset_demo(settings, "RESET-DEMO-DATA")

    assert (result.seeded, result.existing, result.total) == (3, 0, 3)
    assert case_count(settings) == 3


def test_cli_emits_machine_readable_seed_status_and_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = demo_settings(tmp_path)
    monkeypatch.setattr(demo, "get_settings", lambda: settings)

    demo.main(["seed"])
    assert json.loads(capsys.readouterr().out) == {"existing": 0, "seeded": 3, "total": 3}

    demo.main(["status"])
    status = json.loads(capsys.readouterr().out)
    assert [item["reference"] for item in status] == [
        "EC-DEMO-001",
        "EC-DEMO-002",
        "EC-DEMO-003",
    ]

    demo.main(["reset", "--confirm", "RESET-DEMO-DATA"])
    assert json.loads(capsys.readouterr().out) == {"existing": 0, "seeded": 3, "total": 3}


def test_cli_rejects_an_unsafe_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'unsafe.sqlite3'}")
    monkeypatch.setattr(demo, "get_settings", lambda: settings)

    with pytest.raises(SystemExit, match="2"):
        demo.main(["seed"])

    assert "ENVIRONMENT=demo" in capsys.readouterr().err


def test_alembic_config_finds_checkout_for_an_installed_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api_root = tmp_path / "apps" / "api"
    (api_root / "alembic").mkdir(parents=True)
    (api_root / "alembic.ini").write_text(
        "[alembic]\nscript_location = unused\n",
        encoding="utf-8",
    )
    installed_module = tmp_path / ".venv" / "site-packages" / "app" / "demo.py"
    monkeypatch.setattr(demo, "__file__", str(installed_module))
    monkeypatch.chdir(tmp_path)

    config = demo._alembic_config("sqlite:///demo.sqlite3")

    assert config.config_file_name == str(api_root / "alembic.ini")
    assert config.get_main_option("script_location") == str(api_root / "alembic")
    assert config.get_main_option("sqlalchemy.url") == "sqlite:///demo.sqlite3"
