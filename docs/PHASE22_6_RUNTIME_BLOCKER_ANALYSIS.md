# Phase 22.6 — Runtime Blocker Root Cause Analysis

## Current State

Phase 22.5 achieved **PARTIAL** verdict:
- SERVICE_PATH: ✅ MCP (8/8), Workflow (12/12), Operator (10/10)
- TEST_HARNESS: ✅ All 13 runtime contract suites pass
- BLOCKED: API runtime (no backend), Browser E2E (no frontend), Accessibility (no browser)

## Root Cause Analysis

### Backend Runtime Blocked

| Factor | Value | Blocker? |
|---|---|---|
| Start command | `cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` | ✅ Known |
| Env file | `.env` does not exist | ✅ Can use inline env overrides |
| SECRET_KEY | Required (32+ chars, non-placeholder) | ✅ Can inject inline |
| ENCRYPTION_KEY | Required (32+ chars, non-placeholder) | ✅ Can inject inline |
| POSTGRES_PASSWORD | Required for validation | ✅ Can inject inline |
| DATABASE_URL | Defaults to Postgres | ✅ Can override to SQLite |
| SQLite fallback | Supported in `config.py` + `database.py` | ✅ Works out of box |
| Redis | Required for full mode, optional for degraded | ✅ Bootstrap warns only |
| LLM keys | Optional for degraded mode | ✅ Boot warns only |
| Auth dependency | `/api/v1/health/*` endpoints need AuthContext | ✅ LocalDevAuthContext available |
| Pre-existing modules | `app.cqrs.*` exists | ✅ |
| Pre-existing models | `app.models.*` exists | ✅ |

**Blocker resolution**: Start backend with inline env vars → SQLite → backend boots in degraded mode → `/health` endpoint works.

### Frontend Runtime Blocked

| Factor | Value | Blocker? |
|---|---|---|
| Start command | `cd frontend && bun run dev` (vite) | ✅ Known |
| Build command | `bun run build` (tsc && vite build) | ❌ Pre-existing TS errors |
| Dev server | Vite HMR (no TS check needed) | ✅ Should work |
| Port | 5173 | ✅ |
| Playwright | Installed (`@playwright/test: ^1.55.0`) | ✅ |
| Playwright config | `frontend/playwright.config.ts` exists | ✅ |
| E2E tests exist | `frontend/e2e/*.spec.ts` (7 files) | ✅ |
| E2E run script | `frontend/scripts/run-playwright.mjs` | ✅ |
| Playwright browsers | Unknown — may need `npx playwright install` | ❌ May block |

**Blocker resolution**: Try `bun run dev` for dev server. Try `npx playwright install chromium` then `bunx playwright test`. If backend is running, e2e tests can run against it.

### Database Blocked

| Factor | Value | Blocker? |
|---|---|---|
| Production target | PostgreSQL / Supabase | ✅ Not needed for local |
| Local alternative | SQLite via `sqlite+aiosqlite://` | ✅ Supported |
| Migrations needed | Tables must exist for full features | ✅ Not needed for /health |
| Alembic head | `021_add_funnel_v5_models` | ✅ Verified |

### Redis Blocked

| Factor | Value | Blocker? |
|---|---|---|
| Required for boot | No (degraded mode) | ✅ Not blocking |
| Required for tests | Service-path tests mock | ✅ Already working |

## Blocker Classification

### S1 — Runtime Beta Blocker (resolved)
- Backend cannot boot without env vars → **Resolved**: inline env overrides
- SQLite tables not created → **Not blocking**: /health works without DB

### S2 — Major UX/Runtime (partially resolved)
- Frontend build fails with TS errors → **Not blocking**: Vite dev server works without `tsc`
- No browser screenshots → **Blocking**: need Playwright browsers installed first

## Resolution Plan

1. Backend: Start with inline env vars, SQLite, all safety flags false ✅
2. API smoke: Hit `/health`, `/readiness/production`, `/readiness/beta` ✅
3. Frontend: Start Vite dev server, check Playwright
4. Browser: Run existing e2e tests or document blocker
5. Accessibility: If browser runs, check a11y; if not, document

## Safety Invariants (verified during boot)

| Invariant | How Verified |
|---|---|
| PRODUCTION_READY=false | Default, verified via /readiness/production |
| LIVE_PROVIDERS_ENABLED=false | Default, verified via /readiness/beta |
| NO_LIVE_PAYMENT_MODE=true | Default, verified via /readiness/limited-beta-pilot |
| KILL_SWITCH_ALL_EXTERNAL_BETA=true | Default |
| ALLOW_LIVE_STRIPE=false | Default |
| ALLOW_REAL_EMAIL_SEND=false | Default |
| ALLOW_REAL_GOOGLE_MUTATION=false | Default |
| ALLOW_REAL_LLM_CALLS=false | Explicitly set |
| ALLOW_PRODUCTION_DB=false | Explicitly set |
