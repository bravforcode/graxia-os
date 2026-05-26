# Phase 16 Workflow Security Matrix

| Workflow | Current registration source | Draft only? | Required permission | Org scoped? | Rate limit group | Approval for external/customer action? | Gap |
|---|---|---:|---|---:|---|---:|---|
| `daily_funnel_brief` | `backend/app/agent_workflows/service.py` | yes | `workflow:read` + `analytics:read` | yes | `workflow_daily_funnel_brief` | yes | auth permission gate missing |
| `launch_plan_builder` | `backend/app/agent_workflows/service.py` | yes | `workflow:run` | yes | `workflow_launch_plan_builder` | yes | auth permission gate missing |
| `customer_inbox_triage` | `backend/app/agent_workflows/service.py` | yes | `workflow:run` | yes | `workflow_customer_inbox_triage` | yes | auth permission gate missing |
| `token_benchmark_review` | `backend/app/agent_workflows/service.py` | yes | `workflow:read` + `context:read` | yes | `workflow_token_benchmark_review` | yes | auth permission gate missing |
| `delivery_failure_monitor` | `backend/app/agent_workflows/service.py` | yes | `workflow:run` + `delivery:read` | yes | `workflow_delivery_failure_monitor` | yes | auth permission gate missing |
| `weekly_revenue_review` | `backend/app/agent_workflows/service.py` | yes | `workflow:read` + `analytics:read` | yes | `workflow_weekly_revenue_review` | yes | auth permission gate missing |
| `opportunity_scout` | `backend/app/agent_workflows/service.py` | yes | `workflow:run` + `analytics:read` | yes | `workflow_opportunity_scout` | yes | currently callable through MCP without central permission check |
| `experiment_planner` | `backend/app/agent_workflows/service.py` | yes | `workflow:run` | yes | `workflow_experiment_planner` | yes | currently callable through MCP without central permission check |
| `content_plan_draft` | `backend/app/agent_workflows/service.py` | yes | `workflow:run` | yes | `workflow_content_plan_draft` | yes | currently callable through MCP without central permission check |
| `failure_analysis_review` | `backend/app/agent_workflows/service.py` | yes | `workflow:run` + `analytics:read` | yes | `workflow_failure_analysis_review` | yes | currently callable through MCP without central permission check |

## Workflow policy hard requirements

- no live provider calls
- no public publish
- no real customer send
- no approval bypass
- no cross-org run lookup
- no fallback system context for user-triggered runs

## Implementation target

- extend workflow policy metadata with explicit security policy
- enforce auth and org checks in `backend/app/agent_workflows/service.py`
- enforce MCP workflow tools through the same policy path

