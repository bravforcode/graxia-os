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
| `bddcd87` | add runtime adapter layer for existing Graxia systems |

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

## Phase 5 — Context/Token Correctness Hardening

### Verdict
PASS

### Commits
| Commit | Purpose |
|---|---|
| `0e27000` | harden context correctness and token ROI controls |

### Files Changed
| Path | Type | Reason |
|---|---|---|
| `backend/app/context_engine/critical_policy.py` | runtime | define critical path rules and aggressive compression policy |
| `backend/app/context_engine/cache_key.py` | runtime | add hash-aware cache keys with git/no-git support |
| `backend/app/context_engine/quality_gate.py` | runtime | validate packs for missing paths, missing errors, secret paths, and critical compression |
| `backend/app/context_engine/escalation.py` | runtime | bounded escalation decisions for failure-driven context expansion |
| `backend/app/context_engine/multi_agent_registry.py` | runtime | detect inconsistent context packs across agents |
| `backend/app/context_engine/token_roi.py` | runtime | compute retry-aware token ROI |
| `backend/app/context_engine/context_pack.py` | runtime | wire critical-policy decisions and final hash-aware cache keys |
| `backend/app/context_engine/service.py` | runtime | run quality gate after pack build and surface warnings |
| `backend/app/context_engine/exclusions.py` | runtime | exclude `.env.*` generically |
| `backend/app/context_engine/__init__.py` | runtime | export new correctness modules |
| `backend/tests/test_context_quality_gate.py` | test | verify missing-path/error and critical-compression checks |
| `backend/tests/test_context_cache_key.py` | test | verify hash-aware cache invalidation |
| `backend/tests/test_context_auto_escalation.py` | test | verify bounded escalation |
| `backend/tests/test_context_multi_agent_registry.py` | test | verify multi-agent consistency detection |
| `backend/tests/test_token_roi.py` | test | verify ROI penalties and recommendations |
| `docs/PHASE5_CONTEXT_CORRECTNESS_REPORT.md` | docs | phase closeout |

### Tests Run
| Command | Result | Notes |
|---|---|---|
| `python -m compileall backend/app` | PASS | context modules compile cleanly |
| `pytest backend/tests/test_context_quality_gate.py -q` | PASS | `4 passed` |
| `pytest backend/tests/test_context_cache_key.py -q` | PASS | `2 passed` |
| `pytest backend/tests/test_context_auto_escalation.py -q` | PASS | `2 passed` |
| `pytest backend/tests/test_context_multi_agent_registry.py -q` | PASS | `2 passed` |
| `pytest backend/tests/test_token_roi.py -q` | PASS | `2 passed` |
| `pytest backend/tests/test_context_engine_pack.py -q` | PASS | `8 passed` |
| `pytest backend/tests/test_context_engine_diff_cache.py -q` | PASS | `13 passed` |
| `pytest backend/tests/test_mcp_context_tools.py -q` | PASS | `17 passed` |
| `pytest backend/tests/test_workflow_token_benchmark_review.py -q` | PASS | `4 passed` |

### Auto-Fixes
| Issue | Fix | Evidence |
|---|---|---|
| cache invalidation needed file-hash awareness | added `build_context_cache_key()` and used included-file hashes in final pack key | `test_cache_key_changes_when_file_hash_changes` passes |
| critical files could silently downgrade into weak modes | added `critical_policy` and quality-gate enforcement | `test_critical_files_never_aggressive_compressed` passes |
| Windows `tmp_path` fixture hit `PermissionError` in this environment | switched cache-key test to `tempfile.TemporaryDirectory()` | rerun `pytest backend/tests/test_context_cache_key.py -q` passed |
| context packs could miss key error text without signal | added quality gate `MISSING_ERROR_MESSAGE` finding | `test_quality_gate_catches_missing_error_message` passes |

### Safety
- `.env` read: no
- secrets printed: no
- `git add .` used: no
- destructive command used: no
- live provider called: no
- agent-stack root copied: no

### Readiness Gained

- `CONTEXT_SAFE` achieved for local-dev review flows
- context packs now have correctness checks, bounded escalation, and retry-aware ROI metrics
- multi-agent consistency can be validated before orchestration layers are added

### Remaining Blockers

- canonical business-event service not implemented yet
- runtime gateway/orchestration/worker boundaries not implemented yet
- no staging readiness integration for new context metrics yet

### Next Phase Decision

- continue to `Phase 6 — BusinessEvent Emission`

## Phase 6 — BusinessEvent Emission

### Verdict
PASS

### Commits
| Commit | Purpose |
|---|---|
| `b5dc175` | emit canonical business events from funnel flows |

### Files Changed
| Path | Type | Reason |
|---|---|---|
| `backend/app/runtime/events/__init__.py` | runtime | export business-event service and repository |
| `backend/app/runtime/events/types.py` | runtime | define canonical funnel/runtime event names |
| `backend/app/runtime/events/repository.py` | runtime | add in-memory idempotent event storage |
| `backend/app/runtime/events/service.py` | runtime | sanitize payloads and emit canonical `BusinessEvent` values |
| `backend/app/services/funnel_service.py` | runtime | emit events for payment, order, delivery access, delivery open, lead capture, and recommendation creation |
| `backend/app/api/funnel.py` | runtime | emit `approval.requested` after recommendation approval submission |
| `backend/tests/test_business_event_emission.py` | test | verify canonical events from real funnel flows |
| `docs/PHASE6_BUSINESS_EVENT_REPORT.md` | docs | phase closeout |

### Tests Run
| Command | Result | Notes |
|---|---|---|
| `python -m compileall backend/app` | PASS | runtime event modules compile cleanly |
| `pytest backend/tests/test_business_event_emission.py -q` | PASS | `5 passed` |
| `pytest backend/tests/test_funnel_v5.py -q` | PASS | `26 passed` |
| `pytest backend/tests/test_approval_org_scope.py -q` | PASS | `5 passed` |

### Auto-Fixes
| Issue | Fix | Evidence |
|---|---|---|
| repository org filter compared UUID objects to strings | normalized `organization_id` comparison with `str(event.organization_id)` | `test_checkout_completed_emits_payment_order_and_delivery_events` passes |
| package export pointed `business_event_repository` at wrong module | corrected `backend/app/runtime/events/__init__.py` import source | funnel and approval regression suites pass |
| delivery-open test passed `str` into UUID lookup | wrapped `result[\"access_id\"]` with `UUID(...)` in test | `test_delivery_open_emits_business_event` passes |

### Safety
- `.env` read: no
- secrets printed: no
- `git add .` used: no
- destructive command used: no
- live provider called: no
- agent-stack root copied: no

### Readiness Gained

- `EVENT_READY` achieved for current Graxia funnel flows
- payment/order/delivery/lead/recommendation/approval events now emit canonically without raw-token leakage
- event layer is additive and remains repository-backed, ready for future gateway bridge

### Remaining Blockers

- `checkout.started` and `product.published.requested` are deferred because this repo currently has no real creation/request route to hook safely
- runtime gateway/orchestration/worker boundaries not implemented yet

### Next Phase Decision

- continue to `Phase 7 — Runtime Gateway Bridge`

## Phase 7 — Runtime Gateway Bridge

### Verdict
PASS

### Commits
| Commit | Purpose |
|---|---|
| `2140402` | add OpenClaw-style runtime gateway bridge |

### Files Changed
| Path | Type | Reason |
|---|---|---|
| `backend/app/runtime/gateway/__init__.py` | runtime | export gateway bridge entrypoints |
| `backend/app/runtime/gateway/errors.py` | runtime | define gateway-specific blocked/dispatch errors |
| `backend/app/runtime/gateway/policy.py` | runtime | evaluate dangerous and approval-required routes |
| `backend/app/runtime/gateway/repository.py` | runtime | store intake, dispatch, status, audit, and dead-letter records |
| `backend/app/runtime/gateway/dispatcher.py` | runtime | provide injectable task dispatch boundary |
| `backend/app/runtime/gateway/service.py` | runtime | implement intake, dispatch, approval, idempotency, dead-letter, and replay flow |
| `backend/tests/test_runtime_gateway_dispatch.py` | test | verify gateway dispatch, dangerous block, approval block, dead-letter replay, and idempotency |
| `backend/tests/test_mcp_approval_tools.py` | test | seed fixed org rows so approval-FK assertions run against the real schema |
| `docs/PHASE7_RUNTIME_GATEWAY_REPORT.md` | docs | phase closeout |

### Tests Run
| Command | Result | Notes |
|---|---|---|
| `python -m compileall backend/app` | PASS | gateway modules compile cleanly |
| `pytest backend/tests/test_runtime_gateway_dispatch.py -q` | PASS | `5 passed` |
| `pytest backend/tests/test_mcp_dangerous_tools.py -q` | PASS | `13 passed` |
| `pytest backend/tests/test_mcp_approval_tools.py -q` | PASS | `13 passed` |

### Auto-Fixes
| Issue | Fix | Evidence |
|---|---|---|
| blocked gateway reason string mismatched the dangerous-path assertion | capitalized policy reason to `Dangerous MCP tool blocked: ...` | `pytest backend/tests/test_runtime_gateway_dispatch.py -q` passed after patch |
| approval-gated MCP tests hit `sqlite3.IntegrityError: FOREIGN KEY constraint failed` on `approval_requests.organization_id` | seeded fixed `Organization` rows for `TEST_ORG_ID` and `OTHER_ORG_ID` in `backend/tests/test_mcp_approval_tools.py` | `pytest backend/tests/test_mcp_approval_tools.py -q` passed after patch |

### Safety
- `.env` read: no
- secrets printed: no
- `git add .` used: no
- destructive command used: no
- live provider called: no
- agent-stack root copied: no

### Readiness Gained

- `RUNTIME_READY` advanced to gateway-intake/dispatch/dead-letter bridge readiness
- Graxia now has additive task intake, approval blocking, dangerous blocking, idempotency, and replay primitives
- runtime bridge reuses existing control-plane hook boundaries without replacing Graxia MCP/UI/domain

### Remaining Blockers

- workflow boundary not implemented yet
- worker capability layer not implemented yet
- gateway storage is still in-memory only

### Next Phase Decision

- continue to `Phase 8 — Workflow / n8n Boundary`

## Phase 8 — Workflow / n8n Boundary

### Verdict
PASS

### Commits
| Commit | Purpose |
|---|---|
| `a58873d` | add runtime workflow orchestration boundary |

### Files Changed
| Path | Type | Reason |
|---|---|---|
| `backend/app/runtime/orchestration/__init__.py` | runtime | export orchestration boundary entrypoints |
| `backend/app/runtime/orchestration/workflow_registry.py` | runtime | define runtime workflow names and backend aliases/placeholders |
| `backend/app/runtime/orchestration/dispatcher.py` | runtime | add queue-boundary request/receipt abstraction |
| `backend/app/runtime/orchestration/trace_store.py` | runtime | persist runtime workflow traces with correlation/event/context refs |
| `backend/app/runtime/orchestration/service.py` | runtime | route local vs queue execution and adapt existing Graxia workflow runs |
| `backend/tests/test_runtime_orchestration.py` | test | verify local, queue, alias, placeholder, and trace behaviors |
| `docs/PHASE8_WORKFLOW_ORCHESTRATION_REPORT.md` | docs | phase closeout |

### Tests Run
| Command | Result | Notes |
|---|---|---|
| `python -m compileall backend/app` | PASS | orchestration modules compile cleanly |
| `pytest backend/tests/test_runtime_orchestration.py -q` | PASS | `5 passed` |
| `pytest backend/tests/test_mcp_workflow_tools.py -q` | PASS | `8 passed` |

### Auto-Fixes
| Issue | Fix | Evidence |
|---|---|---|
| local workflow fetch path could lose caller correlation and fall back to `auth.request_id` | stored real `correlation_id` in workflow metadata before saving | rerun `pytest backend/tests/test_runtime_orchestration.py -q` passed |

### Safety
- `.env` read: no
- secrets printed: no
- `git add .` used: no
- destructive command used: no
- live provider called: no
- agent-stack root copied: no

### Readiness Gained

- workflow boundary now exists with `local|queue` execution modes
- runtime traces preserve `correlationId`, `businessEventId`, and `contextPacketId`
- existing Graxia `agent_workflows` remain primary local execution engine

### Remaining Blockers

- worker capability layer not implemented yet
- queue backend remains injectable boundary only
- trace persistence is still in-memory

### Next Phase Decision

- continue to `Phase 9 — Worker Capability Layer`

## Phase 9 — Worker Capability Layer

### Verdict
PASS

### Commits
| Commit | Purpose |
|---|---|
| `<pending>` | add Hermes-style runtime worker capability layer |

### Files Changed
| Path | Type | Reason |
|---|---|---|
| `backend/app/runtime/__init__.py` | runtime | export runtime worker entrypoints |
| `backend/app/runtime/workers/__init__.py` | runtime | export worker service/context/provider symbols |
| `backend/app/runtime/workers/capabilities.py` | runtime | define execution context and result types |
| `backend/app/runtime/workers/mock_provider.py` | runtime | provide deterministic mock worker behavior and redaction/block rules |
| `backend/app/runtime/workers/service.py` | runtime | register and execute runtime worker capabilities |
| `backend/tests/test_runtime_worker_capabilities.py` | test | verify registry, deterministic summarize, approval gating, redaction, and dangerous blocking |
| `docs/PHASE9_WORKER_CAPABILITY_REPORT.md` | docs | phase closeout |

### Tests Run
| Command | Result | Notes |
|---|---|---|
| `pytest backend/tests/test_runtime_worker_capabilities.py -q` | PASS | `5 passed` |
| `python -m compileall backend/app` | PASS | worker modules compile cleanly |
| `pytest backend/tests/test_runtime_orchestration.py -q` | PASS | workflow boundary unchanged |

### Auto-Fixes
| Issue | Fix | Evidence |
|---|---|---|
| missing runtime worker package caused `ModuleNotFoundError: No module named 'app.runtime.workers'` during RED phase | added additive `backend/app/runtime/workers/` package with deterministic service/provider | `pytest backend/tests/test_runtime_worker_capabilities.py -q` now passes |

### Safety
- `.env` read: no
- secrets printed: no
- `git add .` used: no
- destructive command used: no
- live provider called: no
- agent-stack root copied: no

### Readiness Gained

- `RUNTIME_READY` advanced to worker capability readiness
- Graxia runtime can now produce deterministic summaries, customer draft proposals, recommendation briefs, memory drafts, and tool proposals without real LLM calls
- dangerous worker proposal paths are blocked before any MCP alignment work

### Remaining Blockers

- MCP runtime alignment not implemented yet
- no persisted worker run store yet
- real provider path remains intentionally disabled by default

### Next Phase Decision

- continue to `Phase 10 — MCP Runtime Alignment`
