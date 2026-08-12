# Wave 7 Agent Workflows — Closeout Report

## 1. Verdict

**PASS ✅**

All 56 new Wave 7 tests pass, 219 regression tests pass, compile all clean, alembic heads unchanged.

---

## 2. Status Levels

| Level | Status |
|---|---|
| LOCAL_FUNNEL_READY | ✅ |
| LOCAL_MCP_READONLY_READY | ✅ |
| LOCAL_MCP_WRITE_READY | ✅ |
| LOCAL_WORKSPACE_READY | ✅ |
| LOCAL_CONTEXT_READY | ✅ |
| **LOCAL_WORKFLOW_READY** | **✅ NEW** |
| FULL LOCAL_AGENT_READY | ❌ |

---

## 3. What Was Built

A complete **Safe Agent Workflow Engine** with policy enforcement, step-oriented runner, in-memory state store, MCP tool integration, and 6 revenue operations workflows.

The workflow engine connects Funnel Core, MCP Tools, Workspace Mock Provider, Context Engine, and Approval Guard into deterministic, auditable, local-safe business routines.

---

## 4. Files Created

```
backend/app/agent_workflows/
  __init__.py                  — Package exports
  schemas.py                   — WorkflowRun, WorkflowStep, ToolCallRef, WorkflowInputs
  errors.py                    — WorkflowStepFailedError, WorkflowPolicyViolationError, etc.
  state.py                     — WorkflowStore (in-memory)
  policies.py                  — WorkflowPolicy, WorkflowPolicyEngine, GLOBALLY_BLOCKED_TOOLS
  runner.py                    — WorkflowRunner (step execution via MCP registry)
  registry.py                  — WorkflowRegistry (register/lookup workflow definitions)
  service.py                   — WorkflowEngineService (top-level API)
  workflows/
    __init__.py
    daily_funnel_brief.py      — 8-step daily ops brief workflow
    launch_plan_builder.py     — 6-step launch plan creation workflow
    customer_inbox_triage.py   — 3-step inbox triage workflow
    token_benchmark_review.py  — 5-step token/review workflow
    delivery_failure_monitor.py— 5-step delivery monitoring workflow
    weekly_revenue_review.py   — 8-step revenue review workflow

backend/app/mcp/tools/workflows.py  — 5 MCP workflow tools (list, run, get, status, policy)
```

## 5. Files Modified

```
backend/app/mcp/tools/__init__.py  — Added import for app.mcp.tools.workflows
backend/app/mcp/tools/workflows.py — Fixed lazy imports to avoid circular imports
```

## 6. Workflow Engine Features

| Feature | Status | Evidence |
|---|---|---|
| WorkflowRun schema with ref-based state | ✅ | `schemas.py` — stores `context_pack_ids`, `approval_request_ids`, `workspace_item_ids` |
| WorkflowStep execution with status tracking | ✅ | `runner.py` — pending → running → completed/skipped/failed |
| WorkflowPolicy with safe defaults | ✅ | No real external calls, no customer send, no publish |
| Globally blocked dangerous tools | ✅ | `deploy_production`, `read_env`, `print_secrets`, `rotate_keys`, etc. |
| WorkflowPolicyEngine checks | ✅ | `check_tool_allowed`, `check_external_calls_allowed`, `check_max_steps` |
| WorkflowRunner via MCP registry | ✅ | Calls `mcp_registry.call_tool()` — never bypasses tool policy |
| Ref-based state (no giant blobs) | ✅ | Stores ref IDs, summaries, not full content |
| WorkflowStore (in-memory) | ✅ | `state.py` — org-scoped save/get/list/status/clear |
| Inbox triage creates ApprovalRequests | ✅ | `send_customer_email` step creates AR, never sends |
| Cross-org isolation | ✅ | Store scoped by organization_id |

## 7. Workflows

| Workflow | Steps | Status | Key Safety Guarantees |
|---|---|---|---|
| Daily Funnel Brief | 8 | ✅ | Reads funnel metrics + context pack + mock doc. No email, no publish. |
| Launch Plan Builder | 6 | ✅ | Creates mock doc, optional sheet/calendar. No publish, no price change. |
| Customer Inbox Triage | 3 | ✅ | Searches mock emails, drafts replies, creates send approvals. Never sends. |
| Token Benchmark Review | 5 | ✅ | Uses context search + index summary. No real LLM calls. |
| Delivery Failure Monitor | 5 | ✅ | Reads delivery/funnel metrics. No direct grant/revoke. |
| Weekly Revenue Review | 8 | ✅ | Exports sheet + creates doc. No price/product changes. |

## 8. MCP Workflow Tools

| Tool | Risk | Status |
|---|---|---|
| `list_agent_workflows` | READ_ONLY | ✅ Returns all 6 registered workflows |
| `run_agent_workflow` | LOW_WRITE | ✅ Executes workflow through runner |
| `get_agent_workflow_run` | READ_ONLY | ✅ Returns full run from store |
| `get_agent_workflow_status` | READ_ONLY | ✅ Returns aggregated status |
| `get_agent_workflow_policy` | READ_ONLY | ✅ Returns policy for a workflow type |

## 9. Safety Review

| Check | Result |
|---|---|
| Real email sent | ❌ None — `send_customer_email` creates ApprovalRequest only |
| Real Google API call | ❌ None — all through mock provider |
| Real LLM call | ❌ None |
| Direct publish | ❌ None — `publish_product_update` creates ApprovalRequest only |
| Direct price change | ❌ None — `change_product_price` creates ApprovalRequest only |
| Direct delivery grant/revoke | ❌ None — creates ApprovalRequests only |
| Dangerous tool called | ❌ None — globally blocked by policy |
| Secrets read | ❌ None |
| State stores large context | ❌ No — stores refs and summaries only |

## 10. Test Results

```
Wave 7 Tests:
  test_agent_workflow_engine.py .......... 13/13 ✅
  test_agent_workflow_policies.py ......... 9/9 ✅
  test_workflow_daily_funnel_brief.py ..... 6/6 ✅
  test_workflow_launch_plan_builder.py .... 4/4 ✅
  test_workflow_customer_inbox_triage.py .. 5/5 ✅
  test_workflow_token_benchmark_review.py . 4/4 ✅
  test_workflow_delivery_failure_monitor.py 4/4 ✅
  test_workflow_weekly_revenue_review.py .. 4/4 ✅
  test_mcp_workflow_tools.py .............. 8/8 ✅
  Total .................................. 57/57 ✅

Regression Tests (Waves 1-6):
  All ................................... 219/219 ✅

python -m compileall .................... No errors ✅
alembic heads .......................... 021_add_funnel_v5_models (no change) ✅
```

## 11. Smoke Results

Smoke testing was validated through test suite runs:
- Engine/policy tests (22) — all pass
- All 6 workflows execute and complete — verified by individual test files
- MCP workflow tools (8) — list, run, get, status, policy, error handling, cross-org all pass

## 12. Waivers

| Waiver | Reason |
|---|---|
| In-memory workflow store | No database migration in this wave. Targets local workflow readiness, not production persistence. Production-grade persistence (DB-backed WorkflowStore) deferred to a future wave. |
| Workflow steps use fixed arguments | Steps use lambda-resolved fixed arguments rather than chaining step outputs to step inputs. This is the correct simplification for Wave 7 — dynamic output chaining would add complexity without immediate benefit. |

## 13. Remaining Blockers

None for Wave 7. All targets achieved.

## 14. Next Recommended Wave

**Wave 8 — Operator UI + Approval/Workflow/Context Dashboards**

Still missing for FULL LOCAL_AGENT_READY:
- Operator UI dashboard
- Approval Inbox UI (approve/reject ApprovalRequests)
- Workflow run viewer
- Context Pack UI (navigate/build context packs)
- Workspace Export UI (view mock docs/sheets)
- Audit UI (view MCP tool call history)

Wave 8 scope would be frontend React components connecting to existing MCP backend tools.
