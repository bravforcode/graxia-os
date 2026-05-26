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
| `4941393` | add runtime contract compatibility layer |

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

## Phase 4 — Runtime Adapter Layer

### Verdict
PASS

### Commits
| Commit | Purpose |
|---|---|
| pending phase 4 commit | add runtime adapter layer for existing Graxia systems |

### Files Changed
| Path | Type | Reason |
|---|---|---|
| `backend/app/runtime/adapters/__init__.py` | runtime | export adapter entrypoints |
| `backend/app/runtime/adapters/approval_adapter.py` | runtime | map `ApprovalRequest` into `ApprovalContract` |
| `backend/app/runtime/adapters/mcp_adapter.py` | runtime | map MCP responses into `ToolCallResult` |
| `backend/app/runtime/adapters/workflow_adapter.py` | runtime | map workflow runs into `WorkflowRunRef` |
| `backend/app/runtime/adapters/context_adapter.py` | runtime | map context packs into `ContextPacketRef` |
| `backend/app/runtime/adapters/funnel_event_adapter.py` | runtime | build canonical `BusinessEvent` values from funnel actions |
| `backend/app/runtime/adapters/audit_adapter.py` | runtime | map audit/readiness payloads into runtime contracts with redaction |
| `backend/tests/test_runtime_adapters.py` | test | verify adapter mappings across approval, MCP, workflow, context, funnel, audit, and readiness |
| `docs/PHASE4_RUNTIME_ADAPTER_REPORT.md` | docs | phase closeout |

### Tests Run
| Command | Result | Notes |
|---|---|---|
| `python -m compileall backend/app` | PASS | adapter modules compile cleanly |
| `pytest backend/tests/test_runtime_adapters.py -q` | PASS | `7 passed` |
| `pytest backend/tests/test_funnel_v5.py -q` | PASS | `26 passed` |
| `pytest backend/tests/test_mcp_workflow_tools.py -q` | PASS | `8 passed` |

### Auto-Fixes
| Issue | Fix | Evidence |
|---|---|---|
| optional datetime/id fields causing invalid explicit `None` writes | adapters omit `createdAt`/`expiresAt` when source values are absent and rely on contract defaults | compile + adapter tests pass |
| MCP approval metadata shape varies by tool | added approval id extraction for `approval_request_id`, `approvalRequestId`, `approval_id`, `approvalId` | `test_mcp_response_to_tool_result_maps_meta_and_error_state` passes |
| audit payloads may contain secret-like keys | added `_safe_payload` redaction and risk derivation fallback | `test_audit_log_to_event_redacts_sensitive_metadata` passes |

### Safety
- `.env` read: no
- secrets printed: no
- `git add .` used: no
- destructive command used: no
- live provider called: no
- agent-stack root copied: no

### Readiness Gained

- `ADAPTER_READY` achieved
- existing Graxia approval, MCP, workflow, context, funnel, audit, and readiness shapes now map into runtime contracts
- adapter layer remains additive and does not replace Graxia primary systems

### Remaining Blockers

- context correctness hardening not implemented yet
- canonical event persistence/emission not implemented yet
- gateway/orchestration/worker runtime boundaries not implemented yet

### Next Phase Decision

- continue to `Phase 5 — Context/Token Correctness Hardening`
