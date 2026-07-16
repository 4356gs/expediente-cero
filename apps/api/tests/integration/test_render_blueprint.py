"""Regression checks for the Render startup contract."""

from pathlib import Path


def test_render_startup_delegates_migrations_to_demo_seed() -> None:
    blueprint = Path("render.yaml").read_text(encoding="utf-8")

    assert "startCommand: python -m app.demo seed && python -m uvicorn" in blueprint
    assert "startCommand: python -m alembic" not in blueprint
