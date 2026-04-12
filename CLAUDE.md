# CLAUDE.md

Repository guidance for coding agents working in this workspace.

## Current Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React + TypeScript + Vite + Bun |
| Backend | FastAPI + SQLAlchemy async + Alembic |
| Database | PostgreSQL / Supabase |
| Cache / Queue | Redis + Celery |
| LLM primary | OpenClaw |
| LLM fallback | Google Gemini |
| Automation | n8n |
| Notifications | Telegram Bot API |

## Canonical Entry Points

- Backend app: `backend/app/main.py`
- Frontend app: `frontend/`
- Compose stack: `docker-compose.yml`
- Environment template: `.env.example`
- Runtime docs: `backend/API_DOCUMENTATION.md`
- Ops docs: `backend/OPERATIONAL_RUNBOOK.md`

## Local Development

### Frontend

```bash
cd frontend
bun install
bun run dev        # http://localhost:5173
bun run build
bun run lint
```

### Backend

```bash
cd backend
python -m pytest tests -q
python scripts/export_openapi.py --output openapi.json
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Repo-Level Verification

PowerShell:

```powershell
.\verify.ps1
```

Make-enabled shells:

```bash
make verify
```

## Docker / Compose

Preferred commands:

```bash
docker compose --profile default up -d
make migrate
bash backend/scripts/smoke_tests.sh
```

Notes:

- Frontend dev server is `http://localhost:5173`, not `3000`
- API docs are at `http://localhost:8000/docs`
- Root health is `GET /health`
- Application health is `GET /api/v1/system/health`

## Backend Runtime Model

### Startup

- `app.main` creates the FastAPI app and lifecycle hooks
- `setup_cqrs()` is called during import/startup
- `check_system_ready()` in `backend/app/core/bootstrap.py` determines `full`, `degraded`, or `blocked`
- `wire_event_handlers()` in `backend/app/core/bootstrap.py` registers the default event pipeline

### Event Flow

Canonical default flow:

```text
opportunity.found
  -> scorer
  -> opportunity.scored
  -> decision_engine
  -> opportunity.decided
  -> drafter + briefer

submission.won
  -> learning_engine + playbook_capture + compound_engine

submission.lost
  -> learning_engine + failure_analysis
```

### LLM Routing

- `backend/app/core/llm.py` is the runtime LLM client
- OpenClaw is primary when `OPENCLAW_API_KEY` is real
- Gemini is fallback when OpenClaw is unavailable or not configured
- Routing decisions come from `backend/app/core/model_router.py`
- Redis is used for cache and request tracking when available
- Cost/routing alerts emit events such as `ai.cost_limit_reached`

## API Surface

Mounted route groups include:

- `auth`
- `approvals`
- `calendar`
- `commands`
- `contacts`
- `cognitive`
- `costs`
- `drafts`
- `email-threads`
- `events`
- `inbox`
- `integrations`
- `jobs`
- `metrics`
- `opportunities`
- `runs`
- `scrapers`
- `skills`
- `submissions`
- `system`
- `tasks`

Do not assume legacy `/dashboard` behavior. The old static dashboard is not the canonical runtime surface.

## Testing Policy

- `backend/tests/` is the canonical backend suite
- `backend/tests_legacy/` is not the default acceptance suite
- When changing tooling, deployment, or docs, add small regression tests when practical
- Keep verification aligned with `verify.ps1` and `make verify`

## Known Reality

- The repo is still in active stabilization, not fully production-complete
- Live Docker stack verification requires a running Docker engine
- Real Google Workspace integration depends on valid OAuth credentials in `.env`
- Remaining project scope still includes live integration verification, deployment rollout validation, and the larger Phase 2 frontend scope
