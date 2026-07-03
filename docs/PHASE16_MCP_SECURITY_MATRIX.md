# Phase 16 MCP Security Matrix

| Tool group | Example tools | Current state | Required permission | Org scoped? | Rate limit group | Approval | Gap |
|---|---|---|---|---|---|---|---|
| system | `get_system_status`, `get_runtime_health`, `get_readiness` | registry enforces auth + perm | `mcp:read` + `system:read` | yes | `mcp_read_system` | no | tool-specific MCP read/write split still coarse at HTTP layer |
| funnel analytics | `get_revenue_summary`, `get_conversion_summary`, `get_high_score_opportunities`, `get_outcome_patterns_summary` | read-only tools exist | `mcp:read` + `analytics:read` | yes | `mcp_read_analytics` | no | direct handler calls still bypass registry unless tests call registry |
| funnel products/orders | `list_products`, `get_product`, `get_orders_summary`, `get_pending_recommendations` | read-only tools exist | `mcp:read` + `funnel:read` | yes | `mcp_read_funnel` | no | per-tool org verification varies |
| runtime | `get_runtime_status`, `list_runtime_tasks`, `get_runtime_task`, `list_dead_letters` | mostly read-only metadata exists | `mcp:read` + `runtime:read` | yes | `mcp_read_runtime` | no | runtime requeue/write enforcement must be explicit |
| workflows | `list_agent_workflows`, `run_agent_workflow`, `get_agent_workflow_run`, `get_agent_workflow_status`, `get_agent_workflow_policy` | tools exist | `mcp:read` or `workflow:run` + `mcp:write` for run | yes | `mcp_workflow` | run paths may require approval on outputs | registry now blocks org mismatch; direct handler fallback still internal-only |
| context | context build/search/get/estimate tools | tools exist | `mcp:read` + `context:read` or `context:write` | yes | `mcp_context` | depends | registry permission checks now available; per-tool policy rollout remains |
| workspace/write | write and workspace mutation tools | many are `LOW_WRITE` or `APPROVAL_REQUIRED` | `mcp:write` + domain write perm | yes | `mcp_write` | often yes | approval + permission checks still need broader rollout |
| dangerous | `read_env`, `print_secrets`, `deploy_production`, `force_push`, `delete_data` | blocked by risk policy | blocked | n/a | `mcp_blocked` | blocked | keep blocked |

## Required Phase 16 registry pipeline

1. resolve auth context
2. require organization
3. rate-limit by org + actor + tool
4. enforce `required_permission`
5. enforce org scope against params/resource ids
6. block dangerous tools
7. create approval for approval-required writes
8. redact output
9. audit success/deny/failure

## Known priority gaps

- registry now enforces auth, permission, and org mismatch centrally
- HTTP route no longer falls back to local-dev org
- direct tool handler usage can still synthesize `MCPAuthContext.system(...)`; keep this internal-only and test through registry for security proof
