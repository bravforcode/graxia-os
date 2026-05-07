.PHONY: up down infra-up infra-down redis-up supabase-up supabase-down supabase-migrate supabase-env-audit supabase-preflight supabase-prod-up supabase-prod-down supabase-prod-migrate supabase-logs build restart logs shell-backend migrate migrate-local db-upgrade db-reset test test-local health health-local run-local frontend-dev frontend-build frontend-install openapi-export smoke verify

up:
	docker compose --profile default up -d

infra-up:
	docker compose up -d postgres redis

redis-up:
	docker compose up -d redis

supabase-up:
	docker compose up -d redis backend celery beat n8n frontend

supabase-down:
	docker compose stop backend celery beat n8n frontend redis

supabase-migrate:
	docker compose exec backend python scripts/alembic_safe.py upgrade head

supabase-env-audit:
	cd backend && python scripts/production_env_audit.py --env-file ../.env.production --compose-file ../docker-compose.supabase.yml --frontend-env-file ../frontend/.env.production

supabase-preflight:
	$(MAKE) supabase-env-audit
	ENV_FILE=.env.production docker compose --env-file .env.production -f docker-compose.supabase.yml run --rm backend python scripts/production_preflight.py

supabase-prod-up:
	$(MAKE) supabase-env-audit
	ENV_FILE=.env.production docker compose --env-file .env.production -f docker-compose.supabase.yml up -d --build

supabase-prod-down:
	ENV_FILE=.env.production docker compose --env-file .env.production -f docker-compose.supabase.yml down

supabase-prod-migrate:
	$(MAKE) supabase-env-audit
	ENV_FILE=.env.production docker compose --env-file .env.production -f docker-compose.supabase.yml run --rm backend python scripts/alembic_safe.py upgrade head

supabase-logs:
	ENV_FILE=.env.production docker compose --env-file .env.production -f docker-compose.supabase.yml logs -f backend worker-critical worker-default worker-background beat

down:
	docker compose down

infra-down:
	docker compose stop postgres redis

build:
	docker compose build --no-cache

restart:
	docker compose restart backend

logs:
	docker compose logs -f backend

shell-backend:
	docker compose exec backend bash

migrate:
	docker compose exec backend python scripts/alembic_safe.py upgrade head

migrate-local:
	cd backend && python scripts/alembic_safe.py upgrade head

db-upgrade:
	docker compose exec backend python scripts/alembic_safe.py upgrade head

db-reset:
	docker compose exec backend python scripts/alembic_safe.py downgrade base && docker compose exec backend python scripts/alembic_safe.py upgrade head

test:
	docker compose exec backend python -m pytest tests -q

test-local:
	cd backend && python -m pytest tests -q

health:
	curl -s http://localhost:8000/health | python -m json.tool

health-local:
	curl -s http://127.0.0.1:8000/api/v1/system/health | python -m json.tool

run-local:
	cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# ── Frontend (Bun + React) ─────────────────────────────────────────────────
frontend-install:
	cd frontend && bun install

frontend-dev:
	cd frontend && bun run dev

frontend-build:
	cd frontend && bun run build

openapi-export:
	cd backend && python scripts/export_openapi.py --output openapi.json

smoke:
	bash backend/scripts/smoke_tests.sh

verify:
	cd backend && python -m pytest tests -q
	cd backend && python scripts/export_openapi.py --output openapi.json
	cd frontend && bun run lint
	cd frontend && bun run build
	bash -n setup.sh
	bash -n backend/scripts/backup_database.sh
	bash -n backend/scripts/restore_database.sh
	bash -n backend/scripts/smoke_tests.sh

# ── Integration Tests ──────────────────────────────────────────────────
test-integration:
	cd backend && python -m pytest tests/integration -v

test-integration-coverage:
	cd backend && python -m pytest tests/integration --cov=app --cov-report=html

# ── Monitoring ─────────────────────────────────────────────────────────
setup-monitoring:
	bash scripts/setup_monitoring.sh

# ── Documentation ──────────────────────────────────────────────────────
docs:
	cd backend && python scripts/export_openapi.py --output openapi.json
	@echo "API documentation generated at backend/openapi.json"

.env:
	cp .env.example .env
	@echo "Created .env from .env.example - fill in your API keys"
