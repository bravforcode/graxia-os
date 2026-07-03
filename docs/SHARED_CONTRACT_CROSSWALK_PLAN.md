# Shared Contract Crosswalk Plan

## Primary Rule

- `graxia os` backend/API/model remains primary.
- `agent-stack` runtime contracts are donor/reference only.
- No second MCP stack.
- No second operator UI.
- No root-to-root copy.

## Crosswalk

| Concept | Primary in graxia os | Donor in agent-stack | Conflict | Decision | Adapter needed? |
|---|---|---|---|---|---|
| ApprovalRequest | `backend/app/models/approval_request.py`, `backend/app/api/approvals.py` | `packages/shared-contracts/src/index.ts` approval schemas, `apps/openclaw-gateway/src/lib/policy.ts` approval builder | field/status drift and different lifecycle metadata | reuse existing Graxia model | yes |
| TaskEnvelope | no single canonical envelope yet; closest runtime/task surfaces are split across API/workflow/MCP | `WorkerTaskEnvelope`, `RoutedTaskEnvelope`, `AgentTask` in `packages/shared-contracts/src/index.ts` | Graxia lacks one canonical runtime envelope | import concept only into future runtime layer | yes |
| BusinessEvent | existing funnel models and event sources under `backend/app/api/funnel.py`, `backend/app/core/event_bus.py` | no exact donor type; donor is task/audit/workflow oriented | business-event shape not unified today | add compatibility schema later, do not import now | yes |
| WorkflowRun | `backend/app/agent_workflows/schemas.py::WorkflowRun` | workflow trace/webhook concepts in `packages/shared-contracts/src/index.ts`, `apps/n8n-orchestrator` | workflow status/result fields differ | reuse Graxia workflow model | yes |
| ContextPacket | `backend/app/context_engine/schemas.py::ContextPack` and context engine services | `packages/context-pipeline/src/index.ts::ContextPacket` | naming and payload semantics differ | reuse Graxia ContextPack, map donor concept later | yes |
| ToolCallResult | `backend/app/mcp/schemas.py::MCPResponse` | closest donor concepts are `ExecutionResult` and `DispatchReceipt` | MCP tool result vs runtime dispatch result are different | reuse Graxia MCPResponse | yes |
| AuditEvent | `backend/app/api/audit.py`, `backend/app/mcp/audit.py`, compliance/security audit services | `AuditEventSchema` in `packages/shared-contracts/src/index.ts` | multiple Graxia audit streams vs single donor schema | keep Graxia audit APIs primary, donor as reference | yes |
| ReadinessStatus | `backend/app/api/health.py` readiness endpoints | `normalizeReadiness()` patterns in gateway/hermes/n8n HTTP modules, `scripts/ci/prod-ready-gate.mjs` | shape differs across planes | keep Graxia health/readiness primary | yes |
| RuntimeHealth | `backend/app/api/health.py`, internal health routes | `/health` and `/ready` contracts across donor gateway/hermes/n8n | Graxia is platform-oriented, donor is multi-plane runtime-oriented | defer unified runtime health adapter to later phase | yes |

## Merge Boundary Plan

| Import source | Candidate target in graxia os | Reason | Risk | Tests needed | Phase |
|---|---|---|---|---|---|
| `agent-stack/packages/shared-contracts` | `backend/app/runtime/contracts/` | unify runtime envelopes and approval/task/audit compat layer | medium | schema parse tests, backward-compat tests | later after cleanup |
| `agent-stack/packages/context-pipeline` | `backend/app/runtime/context_bridge/` or existing `backend/app/context_engine/` adapter | donor has compact runtime-oriented packet assembly | high | context pack parity tests, cache/quality tests | later |
| `agent-stack/apps/openclaw-gateway` patterns | `backend/app/runtime/gateway/` | donor has clean dispatch/policy/idempotency boundaries | high | gateway dispatch contract tests | later |
| `agent-stack/apps/hermes-worker` patterns | `backend/app/runtime/workers/` | capability boundary donor | high | worker capability tests | later |
| `agent-stack/apps/n8n-orchestrator` patterns | `backend/app/runtime/orchestration/` | workflow boundary donor | high | workflow bridge tests | later |
| `agent-stack/apps/mercury-sidecar` patterns | `scripts/ops/` or optional CLI helper area | optional helper only | medium | dry-run CLI tests | defer |
| `agent-stack/packages/knowledge-plane` patterns | existing knowledge write-back services | safe write-back ideas only | medium | redaction/write-safety tests | defer |

## Do Not Import Yet

- Any donor root-level workspace structure
- Any donor app/package by blind copy
- Any second MCP transport/server
- Any second frontend/operator shell
- Any donor temp/test/runtime artifact
