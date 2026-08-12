# Phase 22.6 — Backend Runtime Boot Report

## Verdict: PARTIAL

Backend started successfully in degraded mode. Auth-protected readiness endpoints are blocked (no DB tables).

## Boot Result

| Check | Result | Notes |
|---|---|---|
| Start command | ✅ | `uvicorn app.main:app --host 127.0.0.1 --port 8000` |
| Env mode | inline | No `.env` read. All safety flags set via env vars. |
| Server listening | ✅ | Port 8000, 127.0.0.1 |
| Module import | ✅ | OK |
| Lifespan startup | ✅ | Degraded (DB tables missing) |

## Endpoint Verification

| Endpoint | Status | Response |
|---|---|---|
| `GET /` | ✅ 200 | `{"service":"Graxia OS API","docs":"/docs"}` |
| `GET /health` | ✅ 200 | `{"status":"degraded","readiness":{"is_ready":false,"mode":"blocked","issues":["(sqlite3.OperationalError) no such table: organizations"]}}` |
| `GET /api/v1/health` | ⚠️ 401 | `AUTH_INVALID` — no auth context (no DB) |
| `GET /api/v1/health/readiness` | ⚠️ 401 | `AUTH_INVALID` — no auth context |
| `GET /api/v1/health/readiness/production` | ⚠️ 401 | `AUTH_INVALID` — no auth context |
| `GET /api/v1/health/readiness/beta` | ⚠️ 401 | `AUTH_INVALID` — no auth context |
| `GET /unknown` | ⚠️ (not tested) | — |

## Safety Invariant Verification

| Invariant | How Verified | Status |
|---|---|---|
| PRODUCTION_READY=false | Config default + env override | ✅ |
| ALLOW_LIVE_STRIPE=false | Env override | ✅ |
| ALLOW_REAL_EMAIL_SEND=false | Env override | ✅ |
| ALLOW_REAL_GOOGLE_MUTATION=false | Env override | ✅ |
| ALLOW_REAL_LLM_CALLS=false | Env override | ✅ |
| ALLOW_PRODUCTION_DB=false | Env override | ✅ |
| NO_LIVE_PAYMENT_MODE=true | Env override | ✅ |
| KILL_SWITCH_ALL_EXTERNAL_BETA=true | Env override | ✅ |
| BETA_ENABLED=false | Env override | ✅ |
| APP_ENV=development | Env override | ✅ |
| No .env read | Not used | ✅ |

## Error Safety Check

| Check | Result |
|---|---|
| `AUTH_INVALID` uses safe JSON envelope | ✅ `{"error":{"code":"AUTH_INVALID","message":"Authentication required","request_id":"...","correlation_id":"..."}}` |
| No stack traces in error response | ✅ |
| No raw file paths | ✅ |
| No SQL leaks | ✅ |
| No tokens/secrets | ✅ |
| request_id present | ✅ |
| correlation_id present | ✅ |

## Blocker: Auth-Protected Readiness Endpoints

The `/api/v1/health/*` endpoints require `AuthContext` from auth middleware. In a local runtime with SQLite (no migrations run), there is no database to seed an admin user, so no auth token can be obtained.

**Fix**: Run `alembic upgrade head` against the SQLite database to create tables, allowing the admin seed and login flow.

## Evidence Artifacts

- Backend started: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Config: Safe runtime profile (inline env overrides)
- Health: `/health` returns degraded but functional
- Error: `/api/v1/health/readiness/*` returns safe `AUTH_INVALID` envelope
