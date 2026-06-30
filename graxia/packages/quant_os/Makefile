.PHONY: test test-chaos lint format typecheck coverage api release migrate migrate-down

test:
	python -m pytest graxia/packages/quant_os/tests/ -q --tb=short

test-chaos:
	python -m pytest graxia/packages/quant_os/tests/chaos/ -q --tb=short

lint:
	python -m ruff check graxia/packages/quant_os

format:
	python -m ruff format graxia/packages/quant_os

typecheck:
	python -m mypy graxia/packages/quant_os

coverage:
	python -m pytest graxia/packages/quant_os/tests/ --cov=graxia/packages/quant_os -q

api:
	python graxia/packages/quant_os/api/main.py

release:
	python scripts/run_release_gate.py

migrate:
	python -m alembic upgrade head

migrate-down:
	python -m alembic downgrade base
