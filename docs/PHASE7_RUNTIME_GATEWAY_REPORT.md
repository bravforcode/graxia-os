# Phase 7 Runtime Gateway Report

## 1. Verdict
PASS

## 2. Scope
- add additive runtime gateway bridge under `backend/app/runtime/gateway/`
- reuse Graxia-native `control_plane` run/approval hooks through injectable adapters
- preserve existing Graxia MCP/UI/domain as primary systems

## 3. Files Changed
- `backend/app/runtime/gateway/__init__.py`
- `backend/app/runtime/gateway/errors.py`
- `backend/app/runtime/gateway/policy.py`
- `backend/app/runtime/gateway/repository.py`
- `backend/app/runtime/gateway/dispatcher.py`
- `backend/app/runtime/gateway/service.py`
- `backend/tests/test_runtime_gateway_dispatch.py`

## 4. What Gateway Adds
- task intake validation from `TaskEnvelope`
- dangerous-tool guard for MCP tasks
- approval-required blocking path for public/customer actions
- in-memory dispatch/status/audit/dead-letter repository
- idempotency replay protection via payload `idempotencyKey`
- replay/requeue path for gateway-owned dead letters

## 5. Reused Existing Graxia Systems
- `app.core.control_plane.create_run`
- `app.core.control_plane.mark_run_started`
- `app.core.control_plane.mark_run_completed`
- `app.core.control_plane.mark_run_failed`
- `app.core.control_plane.queue_approval_request`

Note:
- these hooks remain injectable so tests and local runtime bridge can run without forcing DB/network side effects
- existing `app.core.event_bus` dead-letter/replay remains separate infrastructure; this phase adds gateway-local dead letters only

## 6. Policy Rules
- MCP `toolName` in dangerous blocked set -> `DANGEROUS_BLOCKED`
- payload flags `approvalRequired`, `customer_action`, `public_action`, customer/public facing -> `APPROVAL_REQUIRED`
- `taskType` prefixes `send_`, `grant_`, `revoke_`, `publish_`, `public_`, `customer_` -> approval guard
- other routed work -> `LOW_WRITE` or `READ_ONLY`

## 7. Auto-Fixes
- normalized dangerous blocked reason to `Dangerous MCP tool blocked: ...` so blocked-path assertions stay stable
- seeded fixed `Organization` rows in `backend/tests/test_mcp_approval_tools.py` because `approval_requests.organization_id` has a real FK to `organizations.id`

## 8. Tests
| Command | Result | Notes |
|---|---|---|
| `python -m compileall backend/app` | PASS | gateway modules compile |
| `pytest backend/tests/test_runtime_gateway_dispatch.py -q` | PASS | gateway intake/dispatch/approval/dead-letter/idempotency |
| `pytest backend/tests/test_mcp_dangerous_tools.py -q` | PASS | dangerous blocked tools unchanged |
| `pytest backend/tests/test_mcp_approval_tools.py -q` | PASS | approval-gated MCP tools unchanged |

## 9. Safety Review
- `.env` read: no
- secrets printed: no
- `git add .` used: no
- destructive commands used: no
- live provider called: no
- `agent-stack` root copied: no

## 10. Readiness
- `RUNTIME_READY`: partial yes for gateway intake/dispatch/policy/dead-letter bridge
- ready for `Phase 8 — Workflow / n8n Boundary`: yes
- ready for runtime import: not applicable; donor remains read-only reference

## 11. Remaining Gaps
- gateway state is in-memory, not DB-backed yet
- event-bus DLQ and gateway DLQ are intentionally separate in this phase
- no MCP runtime exposure yet
