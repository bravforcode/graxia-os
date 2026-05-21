# Graxia OS — Staging Runbook

## 1. Prerequisites

- **Docker & Docker Compose** installed on the target host
- **Git** checkout of the `staging` branch
- **Environment file** `.env.staging` created (see §2)
- **PostgreSQL** accessible (Supabase or local Docker container)
- **Redis** accessible (Docker container or external)
- Ports **8000** (backend) and **5173** (frontend) available

---

## 2. Required Environment Files

Create `.env.staging` in the project root with the following variables.
Do **NOT** commit this file. Do **NOT** share its contents.

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Min 32 chars, high entropy. Generate: `openssl rand -hex 32` |
| `ENCRYPTION_KEY` | Yes | Min 32 chars. Generate: `openssl rand -hex 32` |
| `POSTGRES_PASSWORD` | Yes | Min 16 chars. Generate: `openssl rand -base64 24` |
| `DATABASE_URL` | Yes | `postgresql+asyncpg://user:pass@host:5432/db` |
| `REDIS_URL` | Yes | `redis://:password@host:6379/0` |
| `CELERY_BROKER_URL` | Yes | `redis://:password@host:6379/1` |
| `CELERY_RESULT_BACKEND` | Yes | `redis://:password@host:6379/2` |
| `APP_ENV` | Yes | Set to `staging` |
| `APP_HOST` | Yes | Staging hostname (e.g. `staging.graxia.io`) |
| `APP_BASE_URL` | Yes | `https://staging.graxia.io` |
| `FRONTEND_URL` | Yes | `https://staging.graxia.io` |
| `ALLOWED_CORS_ORIGINS` | Yes | Comma-separated frontend origins |
| `ADMIN_DEFAULT_EMAIL` | Yes | Initial admin email |
| `ADMIN_DEFAULT_PASSWORD` | Yes | Initial admin password (change after first login) |

Optional but recommended:
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` — for notifications
- `SENTRY_DSN` — error tracking
- `RESEND_API_KEY` — email delivery
- `OPENCLAW_API_KEY` or `GEMINI_API_KEY` — AI features

---

## 3. Docker Staging Startup

No dedicated `config/docker-compose.staging.yml` exists. Use the existing dev or production compose file depending on deployment needs.

### Local Staging (dev config):

```bash
# 1. Start the full stack using dev compose
cd 'C:\Users\menum\graxia os'
docker compose --env-file .env.staging -f docker-compose.yml -f config/docker-compose.dev.yml up -d

# 2. Check service health
docker compose ps

# 3. View logs
docker compose logs -f backend
docker compose logs -f frontend
```

### Production-Close Staging (prod config):

```bash
docker compose --env-file .env.staging -f docker-compose.yml -f config/docker-compose.production.yml up -d
```

---

## 4. Database Migration

```bash
# Run migrations against staging database
docker compose exec backend python scripts/ops/alembic_safe.py upgrade head

# Verify migration state
docker compose exec backend python -c "from alembic.config import Config; from alembic import command; cfg = Config('alembic.ini'); command.current(cfg)"
```

---

## 5. Health Check Commands

```bash
# Backend health endpoint
curl -s http://localhost:8000/health | jq .

# System health (authenticated)
curl -s http://localhost:8000/api/v1/system/health | jq .

# API docs (verify FastAPI swagger)
curl -s http://localhost:8000/docs | head -5

# Frontend
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173
# Expected: 200

# Metrics endpoint
curl -s http://localhost:8000/metrics | head -20
```

---

## 6. Smoke Test Checklist

After deployment, verify each item:

- [ ] **Backend starts** — `docker compose logs backend` shows no startup errors
- [ ] **Health endpoint** — `GET /health` returns 200
- [ ] **Database reachable** — `GET /api/v1/system/health` shows DB connected
- [ ] **Redis reachable** — Celery worker registers and responds
- [ ] **Frontend renders** — Browser shows login page at `http://localhost:5173`
- [ ] **Authentication works** — Login with admin credentials returns JWT
- [ ] **API routes respond** — `GET /api/v1/opportunities` returns valid JSON (may be empty)
- [ ] **CORS configured** — Frontend can make API calls without CORS errors
- [ ] **Logging works** — Backend logs appear with proper level
- [ ] **Migrations complete** — `alembic current` matches expected revision

Run automated smoke tests:
```bash
bash scripts/ops/smoke_tests.sh
```

---

## 7. Rollback Steps

### Option A: Rollback Docker Compose

```bash
# Stop current stack
docker compose down

# Revert to previous tag
git checkout <previous-stable-tag>
docker compose --env-file .env.staging -f docker-compose.yml -f config/docker-compose.dev.yml up -d --build

# Downgrade database if needed
docker compose exec backend python scripts/ops/alembic_safe.py downgrade -1
```

### Option B: Rollback individual service

```bash
# Roll back backend only
docker compose stop backend
git checkout <previous-stable-tag> -- backend/
docker compose up -d --build backend

# Roll back frontend only
docker compose stop frontend
git checkout <previous-stable-tag> -- frontend/
docker compose up -d --build frontend
```

### Option C: Database-only rollback

```bash
# Check current revision
docker compose exec backend alembic current

# Downgrade one step
docker compose exec backend python scripts/ops/alembic_safe.py downgrade -1

# Check revision history
docker compose exec backend alembic history
```

---

## 8. Known Waivers

| Issue | Scope | Mitigation |
|---|---|---|
| **Obsidian/vault tests skipped on Windows** | 8 tests in `test_vault_reader.py`, `test_obsidian_contracts.py` | Marked `skipif(sys.platform == "win32")` due to Windows temp directory PermissionError (antivirus/locking). **Must verify on Linux CI.** |
| **Webhook HMAC timing test relaxed on Windows** | `test_constant_time_signature_comparison` in `test_webhook_hmac.py` | Uses 4σ threshold instead of 3σ on Windows due to lower `time.perf_counter()` resolution. Uses 3σ on Linux where timer is precise enough. |
| **Config validation requires real secrets** | `test_config_validation.py` (28 tests), `test_config_validation_contracts.py` (4 tests) | All non-testing modes require SECRET_KEY ≥32 chars, ENCRYPTION_KEY ≥32 chars, POSTGRES_PASSWORD ≥16 chars. Tests must run with `APP_ENV=testing` in env. |
| **No production readiness attestation** | Full system | This staging runbook validates staging readiness. Production requires additional hardening (see docs/DEPLOYMENT.md). |

---

## 9. Monitoring

```bash
# Check container resource usage
docker stats

# View recent errors
docker compose logs backend --tail=50 | grep -i error

# Check database connections
docker compose exec db psql -U graxia -c "SELECT count(*) FROM pg_stat_activity;"

# Verify Celery worker health
docker compose exec backend celery -A app.tasks.celery_app inspect ping
```
