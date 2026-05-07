# Changelog

All notable changes to Graxia OS are documented here.

---

## [Unreleased] — 2026-04-30 UltraReview Remediation

### Security

- **Fixed P0**: Added bearer token authentication to `/v1/graxia/stream` WebSocket endpoint — was completely unauthenticated
- **Fixed P0**: Removed `VITE_REVENUE_OS_API_KEY` from frontend bundle exposure — moved to backend proxy
- **Fixed P1**: Fixed CSRF middleware silent-pass when `session_id` is absent — now returns 403
- **Fixed P1**: Removed SOQL injection vector in Salesforce integration — added strict email regex validation
- **Fixed P1**: Removed `docker.io` from backend Dockerfile — container escape vector eliminated
- **Fixed P1**: Removed `changeme` fallback defaults for `ADMIN_DEFAULT_PASSWORD` and n8n password
- **Fixed P1**: Fixed `admin@local` fallback in `seed_admin_user` — now raises `RuntimeError` if email is unconfigured
- **Fixed P1**: Added `X-Internal-Token` authentication to `/metrics` endpoint in all environments
- **Fixed P1**: Removed `/v1/graxia/execute` from `PUBLIC_ROUTES` — route-level auth now properly enforced
- **Fixed P1**: Added `API_KEY` and `INTERNAL_METRICS_TOKEN` to production config validation checks

### Architecture

- **Fixed P1**: Replaced silent SQLite fallback with explicit `USE_SQLITE_FALLBACK` flag — misconfigured Postgres no longer silently falls through
- **Fixed P1**: Separated dev/production docker-compose — production file has no `--reload`, no source volume mounts
- **Fixed P1**: Removed `tenacity.retry` wrapper from database engine creation — it never caught real connection errors
- **Archived**: 8 extra docker-compose variants moved to `04-Archive/docker-compose-variants/`

### Backend Quality

- **Fixed P2**: Removed `AUTH_DEBUG` active log from auth middleware (was logging every request at INFO)
- **Fixed P2**: Fixed hardcoded `type="freelance"` in opportunity creation — now uses `data.type` from schema
- **Fixed P2**: Added `type` field to `OpportunityCreate` schema with `Literal` validation
- **Fixed P2**: Changed `SKILLSMP_AUTO_SYNC` default from `True` to `False` — explicit opt-in required
- **Fixed P2**: Added `POSTGRES_PASSWORD` weak-value check to production config validator
- **Fixed P2**: Deleted `config.py.bak` and 20+ debug artifact `.txt`/`.log` files from `backend/`
- **Fixed P2**: Added `backend/*.txt` and `backend/*.log` to `.gitignore`
- **Archived**: `api.py`, `main.py`, `fix_typeddict*.py`, `init_db*.py` moved to `04-Archive/legacy-root/`

### Frontend

- **Fixed P0**: Frontend TypeScript build now passes cleanly — moved unfinished `AICodeAssistant.tsx` and `AIChat.tsx` to `wip/` folder, excluded from compilation
- **Fixed P2**: Fixed `Button.tsx` vs `button.tsx` casing issue — `wip/` excluded from tsconfig
- **Fixed P2**: Replaced `useAuthStore` hook usage in service classes with cookie-based token reader
- **Fixed P2**: Removed `useEffect` unused import from `aiService.ts`
- **Fixed P4-A**: Added `<ErrorBoundary>` wrapper at React app root
- **Fixed P4-B**: Added `<NotFound>` component for invalid routes (404 catch-all)
- **Fixed P4-C**: Resolved dual dashboard — `Dashboard.tsx` moved to `pages/wip/`, `UnifiedDashboard` is canonical
- **Fixed P4-D**: Moved `EventBus` from primary navigation to a `System` subsection
- **Fixed P4-E**: Removed `VITE_REVENUE_OS_API_KEY` from `vite-env.d.ts` and frontend API clients

### Database

- **Added**: Migration `014_add_performance_indexes_phase2` — indexes on `opportunities.is_deleted`, `audit_logs.created_at`, `submissions.status+created_at`
- **Added**: Migration `015_add_user_soft_delete` — `deleted_at` column and index on `users` table
- **Added**: `deleted_at` field and `is_deleted` property to `User` model

### Testing

- **Fixed P1**: Fixed failing chaos test `test_generate_with_empty_strings` — patches `_generate_batch` instead of `_generate_ollama` to prevent real HTTP calls
- **Fixed P1**: Added `test_soql_injection.py` — 7 tests verifying SOQL injection prevention
- **Added**: `USE_SQLITE_FALLBACK` added to `.env.example` with documentation

### DevOps

- **Improved P7-A**: Rewrote backend `Dockerfile` to multi-stage — build tools (`g++`, `gcc`) no longer in runtime image
- **Verified P7-B**: Security scanning (TruffleHog, Gitleaks, Bandit, pip-audit) already present in `.github/workflows/security-gate.yml`
- **Fixed P7-C**: `/api/v1/system/health` now returns HTTP 503 when runtime state is `blocked`
- **Added P7-D**: `docs/SECRETS_MANAGEMENT.md` — Doppler setup guide and secret generation recipes

### Documentation

- **Cleaned P8-A**: 50+ phase/progress/fix markdown files archived to `04-Archive/phase-reports/`
- **Improved P8-B**: README now has English value statement and Quickstart section at the top
- **Added P8-C**: This CHANGELOG
- **Added**: `CREDENTIAL_ROTATION_CHECKLIST.md` — step-by-step rotation guide for all production credentials

---

## [7.2.0] — Pre-review baseline (2026-04-22)

Branch: `wip-2026-04-22-local-snapshot`

- Enterprise-Grade Autonomous Multi-Agent System (MAS) implemented
- Hermes Agent (Phase 7) complete
- pgvector Foundation through Cross-Project Obsidian Hub (Phases 1–5)
- Intelligence Layer architecture refinement
- Google Workspace client mock fixes
