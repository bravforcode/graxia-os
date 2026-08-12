# Phase 20 — Starting Baseline

> Frozen at the start of Phase 20. Records Phase 19 evidence.

## Commit

- Latest commit: `ea70f70` — `feat: implement controlled beta readiness gate with in-memory registry`
- Git status: clean

## Phase 19 Test Results

| Test Suite | Tests | Result |
|-----------|-------|--------|
| test_beta_readiness_gate.py | 6 | PASS |
| test_beta_cohort_allowlist.py | 21 | PASS |
| test_beta_kill_switch.py | 8 | PASS |
| test_human_approval_drill.py | 7 | PASS |
| test_beta_feedback_triage.py | 13 | PASS |
| test_beta_metrics.py | 7 | PASS |
| **Phase 19 total** | **62** | **ALL PASS** |

## Phase 16/17/18 Regression Tests

| Test Suite | Tests | Result |
|-----------|-------|--------|
| Phase 16 security tests | 39 | PASS |
| Phase 17 staging tests | 50 | PASS |
| Phase 18 production gate tests | 63 | PASS |
| **Combined regression** | **152** | **ALL PASS** |

## Verification Status

| Check | Status |
|-------|--------|
| Compileall | ✅ pass |
| Frontend build | ✅ pass |
| Alembic head | `021_add_funnel_v5_models` |
| Production readiness | `false` (locked) |
| BETA_ENABLED | `false` |
| KILL_SWITCH_ALL_EXTERNAL_BETA | `true` (locked) |
| ALLOW_LIVE_STRIPE | `false` |
| ALLOW_REAL_EMAIL_SEND | `false` |
| ALLOW_REAL_GOOGLE_MUTATION | `false` |
| ALLOW_REAL_LLM_CALLS | `false` |
| ALLOW_PRODUCTION_DB | `false` |
| PRODUCTION_READY | `false` |

## Existing Beta Assets

### Runbooks
- `docs/BETA_OPERATOR_RUNBOOK.md` ✅
- `docs/BETA_SUPPORT_TRIAGE_RUNBOOK.md` ✅
- `docs/BETA_SUCCESS_METRICS.md` ✅

### Code
- `backend/app/beta/registry.py` — In-memory BetaRegistry (tester mgmt, feedback, limits)
- `backend/app/api/health.py` — `_build_beta_readiness()` with 11 checks, `/readiness/beta`

### Smoke Scripts
- `scripts/beta_smoke.sh` ✅
- `scripts/beta_smoke.ps1` ✅

### Human Approval Drill
- `backend/tests/test_human_approval_drill.py` — 7 tests for 5 drill scenarios

## Phase 19 PASS Criteria

✅ git clean | ✅ compileall pass | ✅ frontend build pass | ✅ Alembic head verified
✅ beta readiness endpoint exists | ✅ beta kill switch works | ✅ beta allowlist works
✅ beta smoke scripts exist | ✅ operator runbook exists | ✅ support triage runbook exists
✅ human approval drill passes | ✅ no auto-send / no auto-publish / no real charge
✅ production readiness remains false | ✅ live provider guards still pass
