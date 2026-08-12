# Phase 22.6 — Safe Local Runtime Profile

## Runtime Startup Profile

### Backend

| Parameter | Value | Source |
|---|---|---|
| Command | `cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` | Makefile |
| Port | 8000 | Makefile |
| Health endpoint | `GET /health` | `app/main.py` |
| Env vars (inline, no .env) | See below | — |
| Database | SQLite (auto-created) | Inline override |
| Redis | Not required (degraded mode) | Bootstrap |
| Auth | LocalDevAuthContext (mock) | Default |

### Frontend

| Parameter | Value | Source |
|---|---|---|
| Command | `cd frontend && bun run dev` | `frontend/package.json` |
| Port | 5173 | Vite default |
| Proxy | `/api -> http://localhost:8000` | `vite.config.ts` |
| Build | `bun run build` (pre-existing TS errors) | Known issue |

### Required Env Vars (Names Only, Set Inline)

```
SECRET_KEY=auto-generated-64-char-test-key-for-local-runtime-boot-only
ENCRYPTION_KEY=auto-generated-32-char-test-encryption-key
POSTGRES_PASSWORD=auto-gen-16-char-pw-for-validation
DATABASE_URL=sqlite+aiosqlite:///./test_runtime.db
APP_ENV=development
```

### Safety Flags (All Must Be False)

```
PRODUCTION_READY=false
ALLOW_LIVE_STRIPE=false
ALLOW_REAL_EMAIL_SEND=false
ALLOW_REAL_GOOGLE_MUTATION=false
ALLOW_REAL_LLM_CALLS=false
ALLOW_PRODUCTION_DB=false
NO_LIVE_PAYMENT_MODE=true
KILL_SWITCH_ALL_EXTERNAL_BETA=true
BETA_ENABLED=false
```

## Boot Sequence

1. Set env vars inline (no .env involved)
2. Start backend (uvicorn) — boots in degraded mode
3. Verify `/health` returns 200
4. Verify `/readiness/production` returns productionReady=false
5. Verify `/readiness/beta` returns liveProvidersEnabled=false
6. Start frontend (Vite dev server)
7. Run API smoke tests
8. Run browser tests if possible
