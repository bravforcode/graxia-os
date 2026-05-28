# Phase 16 Permission Matrix

Every permission policy across API routes, MCP tools, workflow names, approval operations, runtime/context operations, and revenue ops tools.

## Permission Model

Permissions are string tokens checked at three layers:
1. **HTTP middleware** — `classify_route()` checks role satisfaction (user/operator/admin)
2. **MCP registry** — `_has_tool_permission()` checks `mcp:read`, `mcp:write`, domain-specific perms
3. **Workflow service** — `_require_workflow_access()` checks org match + perms in `WORKFLOW_REQUIRED_PERMISSIONS`

**Deny-by-default**: Any route/tool/workflow without an explicit permission entry is denied unless classified PUBLIC_SAFE.

## API Route Permissions

| Route group | Required role | Org scoped? | Audit-on-deny |
|------------|---------------|------------|---------------|
| /api/v1/auth/* public | PUBLIC | No | auth.invalid |
| /api/v1/auth/* authenticated | user | Yes | auth.missing |
| /api/v1/billing/* | user | Yes | permission.denied |
| /api/v1/funnel/* (auth) | user | Yes | permission.denied |
| /api/v1/contacts/* | user | Yes | permission.denied |
| /api/v1/opportunities/* | user | Yes | permission.denied |
| /api/v1/approvals/* | operator | Yes | permission.denied |
| /api/v1/admin/* | admin | Yes | permission.denied |
| /api/v1/system/* | admin | Yes | permission.denied |
| /api/v1/events/* | admin | Yes | permission.denied |
| /api/v1/scrapers/* | admin | Yes | permission.denied |
| /api/v1/mcp/* | user | Yes | mcp.permission.denied |
| /api/v1/health/* | user | Yes | auth.missing |
| /api/v1/audit/* | user | Yes | permission.denied |
| /internal/* | internal_service | No | auth.invalid |

## MCP Tool Permissions

| Tool group | Required permission | Org scoped? | Risk level | Rate limit |
|-----------|-------------------|------------|-----------|------------|
| system:read | `mcp:read` + `system:read` | Yes | READ_ONLY | mcp_read_system |
| analytics:read | `mcp:read` + `analytics:read` | Yes | READ_ONLY | mcp_read_analytics |
| funnel:read | `mcp:read` + `funnel:read` | Yes | READ_ONLY | mcp_read_funnel |
| runtime:read | `mcp:read` + `runtime:read` | Yes | READ_ONLY | mcp_read_runtime |
| workflow:read | `mcp:read` + `workflow:read` | Yes | READ_ONLY | mcp_workflow |
| workflow:run | `mcp:write` + `workflow:run` | Yes | LOW_WRITE | mcp_workflow |
| context:read | `mcp:read` + `context:read` | Yes | READ_ONLY | mcp_context |
| context:write | `mcp:write` + `context:write` | Yes | LOW_WRITE | mcp_context |
| workspace:write | `mcp:write` + domain write perm | Yes | LOW_WRITE/APPROVAL | mcp_write |
| dangerous | BLOCKED | N/A | DANGEROUS | mcp_blocked |

## Workflow Permissions

| Workflow | Required permission | Org scoped? | Rate limit |
|---------|-------------------|------------|-----------|
| daily_funnel_brief | `workflow:run` + `analytics:read` | Yes | workflow_daily_funnel_brief |
| launch_plan_builder | `workflow:run` | Yes | workflow_launch_plan_builder |
| customer_inbox_triage | `workflow:run` | Yes | workflow_customer_inbox_triage |
| token_benchmark_review | `workflow:run` | Yes | workflow_token_benchmark_review |
| delivery_failure_monitor | `workflow:run` | Yes | workflow_delivery_failure_monitor |
| weekly_revenue_review | `workflow:run` + `analytics:read` | Yes | workflow_weekly_revenue_review |
| opportunity_scout | `workflow:run` + `analytics:read` | Yes | workflow_opportunity_scout |
| experiment_planner | `workflow:run` | Yes | workflow_experiment_planner |
| content_plan_draft | `workflow:run` | Yes | workflow_content_plan_draft |
| failure_analysis_review | `workflow:run` + `analytics:read` | Yes | workflow_failure_analysis_review |

## Approval Operations

| Operation | Permission requirement | Org scoped? | Audit event |
|-----------|----------------------|------------|-------------|
| View approval list | operator role | Yes | permission.denied |
| View single approval | operator role | Yes | permission.denied |
| Approve | operator role | Yes | permission.denied |
| Reject | operator role | Yes | permission.denied |
| Batch approve | operator role | Yes | permission.denied |
| Batch reject | operator role | Yes | permission.denied |
| Create approval (MCP) | `mcp:write` + domain perm | Yes | mcp.permission.denied |

## Runtime / Context Operations

| Operation | Permission requirement | Org scoped? | Audit event |
|-----------|----------------------|------------|-------------|
| Get runtime status | `mcp:read` + `runtime:read` | Yes | mcp.permission.denied |
| List runtime tasks | `mcp:read` + `runtime:read` | Yes | mcp.permission.denied |
| Get runtime task | `mcp:read` + `runtime:read` | Yes | mcp.permission.denied |
| List dead letters | `mcp:read` + `runtime:read` | Yes | mcp.permission.denied |
| Context build | `mcp:write` + `context:write` | Yes | mcp.permission.denied |
| Context search | `mcp:read` + `context:read` | Yes | mcp.permission.denied |
| Context get | `mcp:read` + `context:read` | Yes | mcp.permission.denied |
| Context estimate | `mcp:read` + `context:read` | Yes | mcp.permission.denied |

## Revenue Ops Tools

| Tool | Required permission | Org scoped? | Risk level |
|------|-------------------|------------|-----------|
| get_revenue_summary | `mcp:read` + `analytics:read` | Yes | READ_ONLY |
| get_conversion_summary | `mcp:read` + `analytics:read` | Yes | READ_ONLY |
| get_high_score_opportunities | `mcp:read` + `funnel:read` | Yes | READ_ONLY |
| get_outcome_patterns_summary | `mcp:read` + `analytics:read` | Yes | READ_ONLY |
| list_products | `mcp:read` + `funnel:read` | Yes | READ_ONLY |
| get_product | `mcp:read` + `funnel:read` | Yes | READ_ONLY |
| get_orders_summary | `mcp:read` + `funnel:read` | Yes | READ_ONLY |
| get_pending_recommendations | `mcp:read` + `funnel:read` | Yes | READ_ONLY |

## Deny-by-Default Enforcement Points

| Layer | What happens on deny | Audit event |
|-------|---------------------|-------------|
| AuthMiddleware (HTTP) | 401/403 JSON response | auth.missing / auth.invalid / permission.denied |
| CSRFMiddleware (HTTP) | 403 JSON response | security.csrf |
| RateLimitMiddleware (HTTP) | 429 JSON response | rate_limit.exceeded |
| MCPRegistry.call_tool | safe_error_response + audit | mcp.permission.denied / org.boundary.denied / mcp.dangerous.blocked |
| WorkflowEngineService._require_workflow_access | raises WorkflowOrgMismatchError | workflow.permission.denied |
| API route handler (org mismatch) | 404 JSON response | org.boundary.denied |
| API route handler (missing perms) | 403/401 JSON response | permission.denied |
