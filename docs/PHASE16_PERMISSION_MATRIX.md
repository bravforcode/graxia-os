# Phase 16 Permission Matrix

## Canonical permission namespace

| Namespace | Permissions |
|---|---|
| system | `system:read`, `system:write` |
| org | `org:read`, `org:write` |
| funnel | `funnel:read`, `funnel:write` |
| products | `products:read`, `products:write` |
| orders | `orders:read`, `orders:write` |
| delivery | `delivery:read`, `delivery:write` |
| leads | `leads:read`, `leads:write` |
| analytics | `analytics:read` |
| approvals | `approvals:read`, `approvals:write`, `approvals:resolve` |
| mcp | `mcp:read`, `mcp:write`, `mcp:admin` |
| runtime | `runtime:read`, `runtime:write`, `runtime:requeue` |
| workflow | `workflow:read`, `workflow:run` |
| context | `context:read`, `context:write` |
| audit | `audit:read` |
| admin | `admin:read`, `admin:write` |

## Existing enforcement sources

| Surface | Current model | Gap | Phase 16 action |
|---|---|---|---|
| `backend/app/middleware/auth.py` | role ladder `viewer/user/operator/admin` | role-only, not namespace-based | map roles into canonical permission sets |
| `backend/app/auth/context.py` | `permissions: list[str]` exists | no central population logic | populate canonical permissions in auth context |
| `backend/app/core/authorization.py` | legacy `read:*` / `write:*` enums | different namespace than Phase 16 | keep for compatibility, add Phase 16 layer beside it |
| `backend/app/mcp/registry.py` | `required_permission` metadata only | registry does not enforce it | centralize enforcement in registry |
| `backend/app/api/approvals.py` | org filtering only | no explicit `approvals:*` checks | add permission dependencies |
| `backend/app/agent_workflows/service.py` | workflow policy only | no auth permission gate | add `workflow:*` checks |

## Route to permission mapping

| Surface | Permission |
|---|---|
| health/readiness protected views | `system:read` |
| audit queries | `audit:read` |
| approval listing/get | `approvals:read` |
| approval create/submit | `approvals:write` |
| approval approve/reject/batch resolve | `approvals:resolve` |
| funnel analytics summary | `analytics:read` |
| funnel recommendations list/get | `funnel:read` |
| funnel recommendation create | `funnel:write` |
| delivery access get | `delivery:read` |
| delivery access grant/revoke | `delivery:write` |
| MCP tools/list | `mcp:read` |
| MCP read-only funnel/system/runtime tools | `mcp:read` + domain read permission |
| MCP write/approval tools | `mcp:write` + domain write permission |
| MCP runtime requeue | `runtime:requeue` + approval |
| workflow list/get policy | `workflow:read` |
| workflow execution | `workflow:run` |

## Deny-by-default rules

- Any route without explicit permission mapping fails closed.
- Any MCP tool without explicit policy metadata fails closed.
- Any workflow execution without explicit security metadata fails closed.
- `DANGEROUS_BLOCKED` stays blocked even for admin.

