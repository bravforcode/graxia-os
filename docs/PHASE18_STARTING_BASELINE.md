# Phase 18 — Starting Baseline

> Frozen from Phase 17 PASS. Do not modify after Phase 18 begins.

## Commit State

| Item | Value |
|------|-------|
| Last Phase 17 commit | `233ecea` |
| Message | docs: close phase17 staging runtime gate |
| Git status | Clean |
| Branch | staging |

## Phase 17 Final Verification

| Check | Result |
|-------|--------|
| `git status --short` | Clean |
| `python -m compileall backend/app` | Exit 0 |
| `cd frontend && bun run build` | Exit 0 (12.00s) |
| `alembic heads` | `021_add_funnel_v5_models` |
| Phase 17 tests | 50/50 PASS |
| Phase 16 regression tests | 39/39 PASS |

## Phase 17 Deliverables

| Lane | Status |
|------|--------|
| 1 — Evidence Freeze | `docs/PHASE17_STARTING_BASELINE.md` |
| 2 — Env Contract | `docs/PHASE17_STAGING_ENV_CONTRACT.md` |
| 3 — Runtime Boot | Backend compile ✅, frontend build ✅, Alembic ✅ |
| 4 — API Smoke | `scripts/staging_smoke.sh` + `.ps1` |
| 5 — MCP Smoke | 30/30 tests PASS |
| 6 — Workflow Smoke | All workflow tests PASS |
| 7 — Security Gate | All Phase 16 tests PASS |
| 8 — Correlation | `test_request_correlation.py` — 11 tests PASS |
| 9 — Backup/Rollback | `docs/PHASE17_BACKUP_ROLLBACK_DRY_RUN.md` |
| 10 — Closeout | `docs/PHASE17_STAGING_RUNTIME_GATE_REPORT.md` |

## Production Readiness (Frozen)

| Setting | Current Value |
|---------|---------------|
| `productionReady` | **false** (locked) |
| `goNoGoRequired` | **true** |
| `ALLOW_LIVE_STRIPE` | **false** |
| `ALLOW_REAL_EMAIL_SEND` | **false** |
| `ALLOW_REAL_GOOGLE_MUTATION` | **false** |
| `ALLOW_REAL_LLM_CALLS` | **false** |

## Known Disabled Live Providers

- Stripe live mode (sk_live_*) — blocked by `ALLOW_LIVE_STRIPE=false`
- Real email sending (Resend) — blocked by `ALLOW_REAL_EMAIL_SEND=false`
- Google Workspace write scopes — blocked by `GOOGLE_ENABLE_WRITE_SCOPES=false`
- Real LLM calls — blocked by `ALLOW_REAL_LLM_CALLS=false`
- Production database — no live Supabase URL configured

## Phase 18 Target

PROD_DRY_RUN_READY = true
PRODUCTION_READY = false
