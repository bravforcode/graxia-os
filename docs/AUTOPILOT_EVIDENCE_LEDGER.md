# Autopilot Evidence Ledger

## Phase 2.6 — Baseline Finalization

### Verdict
PASS

### Commits
| Commit | Purpose |
|---|---|
| `0d483e2` | park local-only site experiments outside integration scope |
| `9965735` | repair API integration test compatibility |

### Files Changed
| Path | Type | Reason |
|---|---|---|
| `.gitignore` | config | park `extraterrestrial-escape/` and `sites/` outside integration scope |
| `docs/PHASE2_6_UNTRACKED_OWNERSHIP_DECISION.md` | docs | record ownership decision for untracked Astro subprojects |
| `pytest.ini` | test config | provide repo-root `pythonpath = backend` and stable pytest defaults |
| `tests/test_api_integration.py` | test | replace broken `TestClient` path with `httpx.ASGITransport` harness and disable Sentry during tests |
| `docs/PHASE2_6_API_TEST_COMPATIBILITY.md` | docs | record compatibility root cause and verification |

### Tests Run
| Command | Result | Notes |
|---|---|---|
| `python -m compileall backend/app` | PASS | root verification |
| `pytest backend/tests/test_funnel_foundation.py -q` | PASS | `10 passed` |
| `pytest backend/tests/unit/test_workflow_service.py -q` | PASS | `4 passed` |
| `pytest backend/tests/test_config_validation.py -q` | PASS | `30 passed` |
| `pytest backend/tests/test_security_features.py -q` | PASS | `11 passed` |
| `pytest backend/tests/test_health_readiness.py -q` | PASS | `7 passed` |
| `pytest backend/tests/test_audit_query.py -q` | PASS | `8 passed` |
| `pytest backend/tests/test_env_example_safety.py -q` | PASS | `6 passed` |
| `pytest tests/test_api_integration.py -q` | PASS | `3 passed, 1 skipped` |
| `cd frontend && bun run build` | PASS | production build success |
| `cd backend && alembic -c alembic.ini heads` | PASS | `021_add_funnel_v5_models (head)` |

### Auto-Fixes
| Issue | Fix | Evidence |
|---|---|---|
| repo-root import failure for `from app.main import app` | added root `pytest.ini` with `pythonpath = backend` | `pytest tests/test_api_integration.py -q` now imports successfully |
| `TestClient` incompatibility on `fastapi=0.110.0`, `starlette=0.36.3`, `httpx=0.28.1` | replaced with `httpx.ASGITransport` + `httpx.AsyncClient` harness | test now passes |
| noisy Sentry network retries during tests | set `TESTING=true` before importing `app.main` in test file | retry/logging noise removed from rerun |
| unrelated untracked Astro subprojects blocking clean baseline | parked via `.gitignore` after ownership scan | `git status --short` no longer shows `extraterrestrial-escape/` or `sites/` |

### Safety
- `.env` read: no
- secrets printed: no
- `git add .` used: no
- destructive command used: no
- live provider called: no
- agent-stack root copied: no

### Readiness Gained

- `BASELINE_CLEAN` achieved after final docs commit
- repo-root pytest can import backend app consistently
- Phase 2 baseline is now attributable and testable
- Alembic invocation is proven and documented

### Remaining Blockers

- no Phase 2.6 hard blocker remains
- Phase 3 shared-contract work has not started yet

### Next Phase Decision

- continue to `Phase 3 — Shared Contract Compatibility`

## Phase 3 — Shared Contract Compatibility

### Verdict
PASS

### Commits
| Commit | Purpose |
|---|---|
| current phase feat commit | add runtime contract compatibility layer |

### Files Changed
| Path | Type | Reason |
|---|---|---|
| `backend/app/runtime/__init__.py` | runtime | create runtime package boundary |
| `backend/app/runtime/contracts/__init__.py` | runtime | export compatibility DTOs |
| `backend/app/runtime/contracts/base.py` | runtime | shared schema version, enums, base fields |
| `backend/app/runtime/contracts/business_event.py` | runtime | canonical business event contract |
| `backend/app/runtime/contracts/task_envelope.py` | runtime | runtime task envelope contract |
| `backend/app/runtime/contracts/approval.py` | runtime | approval compatibility contract |
| `backend/app/runtime/contracts/context_packet.py` | runtime | context packet reference contract |
| `backend/app/runtime/contracts/tool_result.py` | runtime | MCP/runtime tool result contract |
| `backend/app/runtime/contracts/workflow.py` | runtime | workflow run reference contract |
| `backend/app/runtime/contracts/readiness.py` | runtime | readiness DTOs |
| `backend/app/runtime/contracts/audit_event.py` | runtime | audit event compatibility contract |
| `backend/tests/test_runtime_contracts.py` | test | verify aliases, defaults, enums, and model compatibility |
| `docs/PHASE3_SHARED_CONTRACT_COMPATIBILITY_REPORT.md` | docs | phase closeout |

### Tests Run
| Command | Result | Notes |
|---|---|---|
| `pytest backend/tests/test_runtime_contracts.py -q` | PASS | `8 passed` |
| `pytest backend/tests/test_mcp_foundation.py -q` | PASS | `33 passed` |
| `pytest backend/tests/test_approval_org_scope.py -q` | PASS | `5 passed` |
| `python -m compileall backend/app` | PASS | runtime contracts compile cleanly |

### Auto-Fixes
| Issue | Fix | Evidence |
|---|---|---|
| donor/graxia naming mismatch risk | added explicit camelCase aliases with snake_case Python fields | contract tests pass with `model_validate` and `model_dump(by_alias=True)` |
| schema-version drift risk | aligned `CURRENT_RUNTIME_SCHEMA_VERSION` to donor `agent-stack` `CURRENT_SCHEMA_VERSION = '2026-04-21'` | read-only donor inspection at `agent-stack/packages/shared-contracts/src/index.ts` |
| approval model default-id assumption in test | made test provide explicit `approvalRequestId` | contract suite rerun passed |

### Safety
- `.env` read: no
- secrets printed: no
- `git add .` used: no
- destructive command used: no
- live provider called: no
- agent-stack root copied: no

### Readiness Gained

- `CONTRACT_READY` achieved
- Graxia now has a Python-native compatibility contract layer
- donor contract shape is referenced without replacing Graxia DB/API/MCP/UI

### Remaining Blockers

- runtime adapters not implemented yet
- no gateway/orchestration/worker bridge yet

### Next Phase Decision

- continue to `Phase 4 — Runtime Adapter Layer`
