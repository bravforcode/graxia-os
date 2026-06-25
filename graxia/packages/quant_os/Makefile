.PHONY: test lint format clean coverage install-precommit install

test:
	python -m pytest graxia/packages/quant_os/tests/ --tb=short -q

test-one:
	python -m pytest $(file) --tb=short -q

lint:
	ruff check graxia/packages/quant_os/

format:
	ruff format graxia/packages/quant_os/

coverage:
	python -m pytest graxia/packages/quant_os/tests/ --cov=graxia/packages/quant_os --cov-report=term --cov-report=html -q

clean:
	find graxia/packages/quant_os -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find graxia/packages/quant_os -type f -name '*.pyc' -delete

install-precommit:
	pip install pre-commit && pre-commit install

install:
	pip install -e graxia/packages/quant_os/
