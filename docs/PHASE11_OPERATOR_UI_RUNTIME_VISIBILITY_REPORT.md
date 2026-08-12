# Phase 11 Operator UI Runtime Visibility Report

## 1. Verdict
PASS

## 2. Scope
- keep existing Graxia operator UI as primary
- add runtime visibility through existing MCP/admin API path
- do not add second UI stack
- do not import `agent-stack` root code

## 3. Files Changed
| Path | Type | Reason |
|---|---|---|
| `frontend/src/lib/admin-api.ts` | frontend | add runtime MCP client types and helpers |
| `frontend/src/pages/admin/Runtime.tsx` | frontend | add runtime status/task/event/dead-letter view in existing admin UI |
| `frontend/src/App.tsx` | frontend | register `/admin/runtime` route |
| `frontend/src/components/Layout.tsx` | frontend | add Runtime nav entry |
| `frontend/src/pages/admin/AgentControl.tsx` | frontend | replace fake readiness badges with runtime/tool evidence and add runtime quick link |
| `frontend/src/pages/admin/Audit.tsx` | frontend | surface runtime snapshot, dead letters, and canonical business events |
| `frontend/src/pages/admin/Readiness.tsx` | frontend | include runtime evidence in readiness evaluation |

## 4. Runtime Surfaces Added
- Runtime status metrics: gateway tasks, dead letters, workflow traces, business events, worker capabilities
- Runtime task list from `list_runtime_tasks`
- Dead letter panel with approval-gated `request_dead_letter_requeue`
- Business event list from `list_business_events`
- Token ROI evaluator baseline preview from `get_token_roi_summary`
- Runtime route wired into existing admin navigation

## 5. Auto-Fixes
- fixed `AgentControl` readiness bug where every row rendered `ready` because `item.key.includes("READY")` always returned true
- switched `Audit` from tool-registry-only derivation to actual runtime/task/event evidence
- switched `Readiness` from static local claims to runtime-backed checks

## 6. Tests Run
| Command | Result | Notes |
|---|---|---|
| `cd frontend && bun run build` | PASS | production build includes `assets/Runtime-wI-E8Jlg.js` |
| `python -m compileall backend/app` | PASS | backend runtime imports still compile |
| `pytest backend/tests/test_mcp_runtime_tools.py -q` | PASS | `7 passed` |
| `pytest backend/tests/test_mcp_foundation.py -q` | PASS | `33 passed` |

## 7. Safety
- `.env` read: no
- secrets printed: no
- `git add .` used: no
- destructive command used: no
- live provider called: no
- `agent-stack` root copied: no

## 8. Readiness Gained
- `UI_READY` advanced to runtime visibility readiness
- existing operator UI now exposes runtime state through existing Graxia MCP/admin surfaces
- dead-letter requeue stays approval-gated in UI

## 9. Remaining Blockers
- no browser/live runtime verification in this phase
- token ROI shown as evaluator baseline only; persisted ROI telemetry is Phase 12
- runtime state remains in-memory until persistence/staging phases

## 10. Next Phase
- continue to `Phase 12 — Token ROI Dashboard`
