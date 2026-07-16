.PHONY: install install-web format lint typecheck test check check-web check-all migrate run-api run-web test-web-e2e demo-seed demo-reset demo-status rehearse-demo

install:
	python -m pip install -e ".[dev]"

install-web:
	npm --prefix apps/web ci

format:
	python -m ruff format apps/api scripts
	python -m ruff check --fix apps/api scripts

lint:
	python -m ruff format --check apps/api scripts
	python -m ruff check apps/api scripts

typecheck:
	python -m mypy apps/api/app

test:
	python -m pytest apps/api/tests

check: lint typecheck test

check-web:
	npm --prefix apps/web run check

check-all: check check-web

migrate:
	python -m alembic -c apps/api/alembic.ini upgrade head

run-api:
	python -m uvicorn app.main:app --app-dir apps/api --reload

run-web:
	npm --prefix apps/web run dev

test-web-e2e:
	npm --prefix apps/web run test:e2e

demo-seed:
	python -m app.demo seed

demo-reset:
	python -m app.demo reset --confirm RESET-DEMO-DATA

demo-status:
	python -m app.demo status

rehearse-demo:
	python scripts/rehearse_demo.py
