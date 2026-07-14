.PHONY: install format lint typecheck test check migrate run-api

install:
	python -m pip install -e ".[dev]"

format:
	python -m ruff format apps/api
	python -m ruff check --fix apps/api

lint:
	python -m ruff format --check apps/api
	python -m ruff check apps/api

typecheck:
	python -m mypy apps/api/app

test:
	python -m pytest apps/api/tests

check: lint typecheck test

migrate:
	python -m alembic -c apps/api/alembic.ini upgrade head

run-api:
	python -m uvicorn app.main:app --app-dir apps/api --reload
