"""Protected, deterministic data lifecycle for the synthetic demonstration."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Never

from alembic import command
from alembic.config import Config

from app.core.config import Settings, get_settings
from app.infrastructure.persistence import (
    SqliteCaseRepository,
    create_session_factory,
    create_sqlite_engine,
)
from app.infrastructure.persistence.fixtures import SYNTHETIC_CASE_FIXTURES

RESET_CONFIRMATION = "RESET-DEMO-DATA"


class DemoSafetyError(RuntimeError):
    """A demo data operation failed a safety boundary."""


@dataclass(frozen=True, slots=True)
class DemoSeedResult:
    """Machine-readable summary of an idempotent seed."""

    seeded: int
    existing: int
    total: int


@dataclass(frozen=True, slots=True)
class DemoCaseStatus:
    """Stable status for one canonical demonstration case."""

    reference: str
    case_id: str
    procedure: str
    language: str
    status: str


def _require_demo(settings: Settings) -> None:
    if settings.environment != "demo":
        raise DemoSafetyError("demo data commands require EXPEDIENTE_CERO_ENVIRONMENT=demo")


def _alembic_config(database_url: str) -> Config:
    installed_api_root = Path(__file__).resolve().parents[1]
    checkout_api_root = Path.cwd() / "apps" / "api"
    api_root = next(
        (
            candidate
            for candidate in (installed_api_root, checkout_api_root)
            if (candidate / "alembic.ini").is_file() and (candidate / "alembic").is_dir()
        ),
        None,
    )
    if api_root is None:
        raise DemoSafetyError("cannot locate the Alembic configuration and migrations")
    config = Config(api_root / "alembic.ini")
    config.set_main_option("script_location", str(api_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _seed_migrated(settings: Settings) -> DemoSeedResult:
    engine = create_sqlite_engine(settings.database_url)
    repository = SqliteCaseRepository(create_session_factory(engine))
    seeded = 0
    existing = 0
    try:
        for fixture in SYNTHETIC_CASE_FIXTURES:
            persisted = repository.get(fixture.case.id)
            if persisted is not None:
                if (
                    persisted.reference != fixture.case.reference
                    or persisted.procedure_type != fixture.case.procedure_type
                    or persisted.output_language != fixture.case.output_language
                ):
                    raise DemoSafetyError(f"fixture identity collision for {fixture.case.id}")
                existing += 1
                continue
            repository.add_intake(
                fixture.case,
                fixture.source_messages,
                fixture.documents,
            )
            seeded += 1
    finally:
        engine.dispose()
    return DemoSeedResult(
        seeded=seeded,
        existing=existing,
        total=len(SYNTHETIC_CASE_FIXTURES),
    )


def seed_demo(settings: Settings) -> DemoSeedResult:
    """Migrate and idempotently add the three canonical synthetic intakes."""
    _require_demo(settings)
    command.upgrade(_alembic_config(settings.database_url), "head")
    return _seed_migrated(settings)


def reset_demo(settings: Settings, confirmation: str) -> DemoSeedResult:
    """Rebuild only a database explicitly configured as a demo database."""
    _require_demo(settings)
    if confirmation != RESET_CONFIRMATION:
        raise DemoSafetyError(f"reset requires --confirm {RESET_CONFIRMATION}")
    config = _alembic_config(settings.database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    return _seed_migrated(settings)


def demo_status(settings: Settings) -> tuple[DemoCaseStatus, ...]:
    """Return the persisted state of canonical demo cases without model calls."""
    _require_demo(settings)
    command.upgrade(_alembic_config(settings.database_url), "head")
    engine = create_sqlite_engine(settings.database_url)
    repository = SqliteCaseRepository(create_session_factory(engine))
    try:
        statuses = []
        for fixture in SYNTHETIC_CASE_FIXTURES:
            persisted = repository.get(fixture.case.id)
            if persisted is not None:
                statuses.append(
                    DemoCaseStatus(
                        reference=persisted.reference,
                        case_id=str(persisted.id),
                        procedure=persisted.procedure_type.value,
                        language=persisted.output_language.value,
                        status=persisted.status.value,
                    )
                )
        return tuple(statuses)
    finally:
        engine.dispose()


def _exit(parser: argparse.ArgumentParser, message: str) -> Never:
    parser.exit(2, f"error: {message}\n")


def main(argv: Sequence[str] | None = None) -> None:
    """Run the protected demo-data command line interface."""
    parser = argparse.ArgumentParser(prog="expediente-cero-demo")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("seed", help="migrate and seed missing demo cases")
    reset_parser = subcommands.add_parser("reset", help="rebuild and reseed the demo database")
    reset_parser.add_argument("--confirm", default="")
    subcommands.add_parser("status", help="show canonical demo case states")
    args = parser.parse_args(argv)
    settings = get_settings()
    try:
        if args.command == "seed":
            payload: object = asdict(seed_demo(settings))
        elif args.command == "reset":
            payload = asdict(reset_demo(settings, args.confirm))
        else:
            payload = [asdict(item) for item in demo_status(settings)]
    except DemoSafetyError as error:
        _exit(parser, str(error))
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
