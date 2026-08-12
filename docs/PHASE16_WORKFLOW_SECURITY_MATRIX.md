# Phase 16 Workflow Security Matrix

| Workflow | Current registration source | Draft only? | Required permission | Org scoped? | Rate limit group | Approval for external/customer action? | Gap |
|---|---|---:|---|---:|---|---:|---|
| `daily_funnel_brief` | `backend/app/agent_workflows/service.py` | yes | `workflow:run` + `analytics:read` | yes | `workflow_daily_funnel_brief` | yes | service gate implemented |
| `launch_plan_builder` | `backend/app/agent_workflows/service.py` | yes | `workflow:run` | yes | `workflow_launch_plan_builder` | yes | service gate implemented |
| `customer_inbox_triage` | `backend/app/agent_workflows/service.py` | yes | `workflow:run` | yes | `workflow_customer_inbox_triage` | yes | service gate implemented |
| `token_benchmark_review` | `backend/app/agent_workflows/service.py` | yes | `workflow:run` | yes | `workflow_token_benchmark_review` | yes | analytics/context granularity can tighten later |
| `delivery_failure_monitor` | `backend/app/agent_workflows/service.py` | yes | `workflow:run` | yes | `workflow_delivery_failure_monitor` | yes | delivery-specific read perm can tighten later |
| `weekly_revenue_review` | `backend/app/agent_workflows/service.py` | yes | `workflow:run` + `analytics:read` | yes | `workflow_weekly_revenue_review` | yes | service gate implemented |
| `opportunity_scout` | `backend/app/agent_workflows/service.py` | yes | `workflow:run` + `analytics:read` | yes | `workflow_opportunity_scout` | yes | service + registry checks implemented |
| `experiment_planner` | `backend/app/agent_workflows/service.py` | yes | `workflow:run` | yes | `workflow_experiment_planner` | yes | service gate implemented |
| `content_plan_draft` | `backend/app/agent_workflows/service.py` | yes | `workflow:run` | yes | `workflow_content_plan_draft` | yes | service gate implemented |
| `failure_analysis_review` | `backend/app/agent_workflows/service.py` | yes | `workflow:run` + `analytics:read` | yes | `workflow_failure_analysis_review` | yes | service + registry checks implemented |

## Workflow policy hard requirements

- no live provider calls
- no public publish
- no real customer send
- no approval bypass
- no cross-org run lookup
- no fallback system context for user-triggered runs

## Implementation target

- service now enforces auth/org checks in `backend/app/agent_workflows/service.py`
- registry now blocks MCP org mismatch before handler execution
- next tightening step: declare workflow security policy metadata explicitly per definition
