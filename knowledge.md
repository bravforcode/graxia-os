# Graxia OS — Project Knowledge

## What This Is

**Graxia OS** — a personal AI chief of staff / Revenue OS. Finds leads, drafts outreach, manages approvals, tracks pipeline, and runs multi-agent automation with human oversight. Backend is FastAPI (Python 3.11+), frontend is React 18/TypeScript/Vite.

## Quickstart

```bash
# Install all dependencies
cd frontend && bun install && cd ../backend && pip install -r requirements.txt

# Start local Postgres + Redis via Docker
make infra-up

# Run database migrations
make migrate-local

# Run backend (separate terminal)
make run-local              # uvicorn on :8000

# Run frontend (separate terminal)
make frontend-dev           # Vite on :5173

# Or run everything with Docker Compose
make up
```

## Key Commands

| Action | Command |
|---|---|
| Start full dev stack | `make up` |
| Backend tests | `make test-local` (or `cd backend && pytest -x`) |
| Frontend tests | `cd frontend && bun run test` |
| Frontend lint | `cd frontend && bun run lint` |
| Frontend build | `cd frontend && bun run build` |
| Export OpenAPI | `cd backend && python ../scripts/ops/export_openapi.py` |
| Smoke tests | `bash scripts/ops/smoke_tests.sh` |
| Full verify | `make verify` |
| Migrations (Docker) | `make migrate` |
| Migrations (local) | `make migrate-local` |
| Shell check scripts | `bash -n setup.sh` |
| Windows verify | `.\verify.ps1` |
| Preflight check | `python scripts/preflight.py` |

## Architecture

- **`backend/`** — FastAPI API, AI agents, SQLAlchemy async models, Celery workers, Alembic migrations
  - `app/api/` — REST route modules under `/api/v1`
  - `app/agents/` — AI agents (scoring, drafting, learning, sync)
  - `app/core/` — Auth, LLM router, event bus, security, monitoring
  - `app/models/` — SQLAlchemy domain models (User, Opportunity, Contact, Draft, etc.)
  - `app/tasks/` — Celery task definitions & beat schedule
  - `app/middleware/` — Auth, CSRF, rate limit, security headers
  - `tests/` — Canonical test suite
- **`frontend/`** — React 18 SPA with TypeScript, Vite, TanStack Query, Zustand, Tailwind
  - Routes: `/login`, `/opportunities`, `/drafts`, `/contacts`, `/metrics`, `/jobs`, `/emails`, `/tasks`, `/costs`, `/event-bus`, `/settings`
  - Proxies `/api` to backend at `http://127.0.0.1:8000`
- **`config/`** — Centralized Docker Compose, Dockerfiles, PM2, Redis, pytest configs
- **`scripts/`** — All operational/deployment/setup scripts
- **`deploy/`** — Caddy, monitoring, backup, smoke test scripts
- **`identity/`** — Operator profile, positioning, projects
- **`docs/`** — Runbooks, deployment guides, security notes, route manifest

## Data Flow

```
External sources → scrapers/Google Workspace/n8n/manual
  → FastAPI control plane → agents + model router + event bus
  → PostgreSQL/Supabase → Celery queues + beat schedule
  → React frontend, Telegram alerts, Obsidian second brain, metrics
```

## Tech Stack

**Backend:** FastAPI, SQLAlchemy async, Alembic, PostgreSQL/Supabase, Redis, Celery, JWT auth, Sentry, Prometheus

**Frontend:** React 18, TypeScript, Vite, Bun, TanStack Query, Zustand, Tailwind CSS, Radix UI, Recharts, Framer Motion, Storybook, Vitest, Playwright

**LLM:** OpenClaw (Claude proxy) as primary, Gemini as fallback, with model router for cost tiers

## Conventions & Gotchas

- **Canonical backend surface** is `backend/app/main.py` and `/api/v1` routes. Legacy `dashboard/` is NOT mounted.
- **Frontend dev port** must be **5173** (not 3000).
- **Backend tests** are in `backend/tests/`. `backend/tests_legacy/` is reference-only, not canonical.
- **Production DB** is PostgreSQL/Supabase. SQLite is only for local test harness.
- **Scheduler:** Use `CELERY_BEAT` in production, set `SCHEDULER_EMBEDDED=false`. Embedded scheduler is for dev only.
- **Environment:** Copy `.env.example` to `.env`. Production validates secrets strictly (rejects placeholders, short keys).
- **Secrets:** `SECRET_KEY` must be 32+ chars (64 in production). `ENCRYPTION_KEY` 32+ chars. `POSTGRES_PASSWORD` 16+ chars.
- **OpenAPI spec** must be regenerated after route/schema changes: `cd backend && python ../scripts/ops/export_openapi.py --output openapi.json`
- **Migrations:** Run via `alembic_safe.py` (not direct alembic). Review destructive operations with `scripts/ops/check_destructive_migrations.py`.
- **Redis** is optional for degraded local startup but required for full Celery/worker behavior.
- **No external calls** in import-time tooling — integrations initialize lazily.
- **Approval-first** for outward actions (sending messages, applying, mutating external systems).
- **Use `@/` path alias** in frontend imports (maps to `frontend/src/`).
- **Testing:** Async tests with `asyncio_mode = auto`. No mock DB — use real DB in tests.
- **Frontend proxy** for dev: Vite proxies `/api` to `http://127.0.0.1:8000`. Override via `VITE_DEV_PROXY_TARGET` env var.
