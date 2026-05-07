.PHONY: setup dev test lint clean

# Initial setup for development
setup:
	@echo "Setting up BravOS v3 development environment..."
	npm install
	python -m venv venv
	./venv/Scripts/pip install -r requirements.txt
	cp .env.example .env
	npx husky install

# Start core infrastructure
infra-up:
	docker-compose up -d

# Start development servers
dev:
	@echo "Starting development servers..."
	# Placeholder for multi-service start logic

# Run all tests
test:
	@echo "Running tests..."
	npm test
	./venv/Scripts/pytest

# Lint all code
lint:
	@echo "Linting code..."
	npm run lint
	./venv/Scripts/black .
	./venv/Scripts/flake8 .

# Check Hard Rules compliance
check-hr:
	python tools/check-hr-rules.py

# Clean up environment
clean:
	@echo "Cleaning up..."
	rm -rf node_modules venv
	docker-compose down -v
