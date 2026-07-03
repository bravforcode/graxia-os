# Phase 16 Researched Enterprise Plan

## Scope

Phase 16 hardens the existing Graxia OS security boundary to staging-grade.

This is **not** a greenfield auth implementation. The repo already contains:

- `backend/app/auth/context.py`
- `backend/app/auth/dependencies.py`
- `backend/app/auth/middleware.py`
- `backend/app/middleware/auth.py`
- `backend/app/middleware/rate_limit.py`
- `backend/app/api/approvals.py`
- `backend/app/api/audit.py`
- `backend/app/api/funnel.py`
- `backend/app/api/health.py`
- `backend/app/api/mcp.py`
- `backend/app/mcp/registry.py`
- `backend/app/agent_workflows/service.py`

Phase 16 therefore follows a **reuse and harden** strategy:

1. Inventory actual routes, MCP tools, and workflow surfaces.
2. Normalize a deny-by-default `AuthContext` and permission model.
3. Close org-boundary leaks.
4. Upgrade rate limits and payload guards to request-aware safe responses.
5. Enforce MCP and workflow auth/policy at execution boundaries.
6. Add readiness evidence proving the security boundary.

## Current Security Baseline

### Existing strengths

- `AuthContextMiddleware` already attaches `request.state.auth_context`.
- `AuthMiddleware` already classifies routes into `PUBLIC`, `AUTHENTICATED`, `OPERATOR`, `ADMIN`, `BLOCKED`.
- `backend/app/api/audit.py` already uses `require_organization`.
- `backend/app/api/approvals.py` already filters single-item access by `organization_id`.
- `backend/app/mcp/registry.py` already blocks dangerous tools through `risk_policy`.
- `backend/app/agent_workflows/policies.py` already blocks globally dangerous workflow tools.
- `backend/app/main.py` already mounts request-size, security-header, auth, and rate-limit middleware.

### Current gaps found in inventory

- `backend/app/api/mcp.py` falls back to local-dev org `00000000-0000-0000-0000-000000000001`.
- `backend/app/api/mcp.py` accepts body/header org values without route-level auth enforcement.
- `backend/app/api/approvals.py` batch approve/reject endpoints have no auth dependency.
- `backend/app/api/funnel.py` public lead-magnet routes still depend on `get_auth_context`.
- `backend/app/api/funnel.py` public delivery token routes do not yet use token fingerprint rate limiting.
- `backend/app/middleware/rate_limit.py` returns `{"detail": ...}` rather than Phase 16 safe error shape.
- `backend/app/mcp/registry.py` records `required_permission` metadata but does not enforce it centrally.
- `backend/app/agent_workflows/service.py` runs workflows with `MCPAuthContext` but has no explicit permission gate.
- `backend/app/auth/context.py` is narrower than the Phase 16 target model and lacks scopes/correlation/auth-method flags.
- `backend/app/api/health.py` readiness is present but does not yet prove auth/org/rate-limit/security checks as first-class gates.

## Execution Order

### Lane A

- inventory routes
- inventory MCP tools
- inventory workflows
- write Phase 16 matrices

### Lane B

- extend `AuthContext`
- add permission namespace and dependency helpers
- centralize request context fields

### Lane C

- apply explicit route protection deps
- remove implicit auth assumptions from public/customer routes

### Lane D

- add shared org-boundary helpers
- enforce same-org checks across APIs, MCP, and workflows

### Lane E

- harden `backend/app/middleware/rate_limit.py`
- add request-aware 429 errors
- add MCP/workflow/public-route keying

### Lane F

- align payload-size errors with safe error contract

### Lane G

- add app-level safe error primitives and exception handlers

### Lane H

- add security audit event helpers and denied-event logging

### Lane I

- enforce MCP `required_permission`, org scope, and auth presence in `backend/app/mcp/registry.py`

### Lane J

- enforce workflow permission, org scope, and draft-only execution in `backend/app/agent_workflows/service.py`

### Lane K

- secure customer/public funnel routes
- keep live providers disabled

### Lane L

- add auth/org/rate-limit checks to readiness output
- keep production readiness false by default

### Lane M

- run verification matrix
- write closeout report
- update ledger

## Phase 16 Definition of Done

- cross-org API/MCP/workflow access denied by tests
- batch approval endpoints protected
- MCP org fallback removed from HTTP transport
- public/customer routes separated from operator auth routes
- rate-limited responses carry safe `request_id` and `correlation_id`
- dangerous tools remain blocked
- readiness proves auth/org/rate-limit/security checks
- `python -m compileall backend/app` passes
- security test matrix passes or deferrals are explicitly documented

