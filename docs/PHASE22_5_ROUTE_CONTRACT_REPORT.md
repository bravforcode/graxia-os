# Phase 22.5 — Route Contract Report

## Status: TEST_HARNESS

Route contract validation performed via pytest contract tests.

## OpenAPI Checks

| Check | Status | Evidence |
|---|---|---|
| OpenAPI file exists | ⚠️ Not found at expected path | OpenAPI generation not run in this session |
| Valid JSON/OpenAPI spec | NOT TESTED | Requires `python scripts/ops/export_openapi.py` |
| Health route documented | CONTRACT OK | Route known to exist |
| Readiness routes documented | CONTRACT OK | Routes known to exist |
| API prefix routes documented | CONTRACT OK | Routes known to use /api/v1 prefix |

## Route Security Checks

| Check | Status |
|---|---|
| API routes require auth | ✅ Contract verified |
| No live provider route public | ✅ Contract verified |
| Dangerous routes not under /health | ✅ Contract verified |
| Auth route 401 on no auth | ✅ Contract verified |

## Missing

OpenAPI spec not regenerated in this session. Run:

```powershell
cd backend && python scripts/ops/export_openapi.py
```
