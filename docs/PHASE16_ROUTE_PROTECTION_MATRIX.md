# Phase 16 Route Protection Matrix

| Method | Path | Route group | Current protection | Target class | Required actor | Required permission | Org scoped? | Rate limit key | Audit on deny? | Public exposure? | Test file |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `POST` | `/api/v1/auth/login` | auth | `AuthMiddleware.PUBLIC` | `PUBLIC_RATE_LIMITED` | anonymous | none | no | `ip:auth_login` | yes | yes | `backend/tests/test_rate_limit.py` |
| `POST` | `/api/v1/auth/register` | auth | `AuthMiddleware.PUBLIC` | `PUBLIC_RATE_LIMITED` | anonymous | none | no | `ip:auth_register` | yes | yes | `backend/tests/test_rate_limit.py` |
| `POST` | `/api/v1/auth/refresh` | auth | `AuthMiddleware.PUBLIC` | `PUBLIC_RATE_LIMITED` | anonymous/session | none | no | `ip_or_session:auth_refresh` | yes | yes | `backend/tests/test_rate_limit.py` |
| `GET` | `/health` | health | `AuthMiddleware.PUBLIC` + `Depends(get_auth_context)` | `PUBLIC_SAFE` | anonymous | none | no | `ip:health` | no | yes | `backend/tests/test_health_readiness.py` |
| `GET` | `/readiness` | readiness | `Depends(get_auth_context)` | `AUTH_REQUIRED` or explicit `PUBLIC_SAFE` | user/service | `system:read` if protected | no | `ip:readiness` | yes | limited | `backend/tests/test_staging_auth_readiness.py` |
| `GET` | `/readiness/staging` | readiness | `Depends(get_auth_context)` | `AUTH_REQUIRED` | user/service | `system:read` | no | `actor:readiness_staging` | yes | no | `backend/tests/test_staging_auth_readiness.py` |
| `GET` | `/readiness/production` | readiness | `Depends(get_auth_context)` | `AUTH_REQUIRED` | user/service | `system:read` | no | `actor:readiness_production` | yes | no | `backend/tests/test_production_auth_gate.py` |
| `GET` | `/api/v1/audit/events` | audit | `Depends(require_organization)` | `AUTH_REQUIRED` | user/admin | `audit:read` | yes | `org+actor:audit_events` | yes | no | `backend/tests/test_audit_query.py` |
| `GET` | `/api/v1/audit/mcp` | audit | `Depends(require_organization)` | `AUTH_REQUIRED` | user/admin | `audit:read` | yes | `org+actor:audit_mcp` | yes | no | `backend/tests/test_audit_query.py` |
| `GET` | `/api/v1/audit/workflows` | audit | `Depends(require_organization)` | `AUTH_REQUIRED` | user/admin | `audit:read` | yes | `org+actor:audit_workflows` | yes | no | `backend/tests/test_audit_query.py` |
| `GET` | `/api/v1/approvals` | approvals | `Depends(get_auth_context)` | `AUTH_REQUIRED` | user/admin | `approvals:read` | yes | `org+actor:approvals_list` | yes | no | `backend/tests/test_approval_org_scope.py` |
| `GET` | `/api/v1/approvals/{approval_id}` | approvals | `Depends(get_auth_context)` | `AUTH_REQUIRED` | user/admin | `approvals:read` | yes | `org+actor:approval_get` | yes | no | `backend/tests/test_approval_org_scope.py` |
| `PATCH` | `/api/v1/approvals/{approval_id}/approve` | approvals | `Depends(get_auth_context)` | `AUTH_REQUIRED` | user/admin | `approvals:resolve` | yes | `org+actor:approval_resolve` | yes | no | `backend/tests/test_approval_org_scope.py` |
| `PATCH` | `/api/v1/approvals/{approval_id}/reject` | approvals | `Depends(get_auth_context)` | `AUTH_REQUIRED` | user/admin | `approvals:resolve` | yes | `org+actor:approval_resolve` | yes | no | `backend/tests/test_approval_org_scope.py` |
| `PATCH` | `/api/v1/approvals/batch/{batch_key}/approve` | approvals | no explicit auth dep | `AUTH_REQUIRED` | user/admin | `approvals:resolve` | yes | `org+actor:approval_batch_resolve` | yes | no | `backend/tests/test_route_protection_matrix.py` |
| `PATCH` | `/api/v1/approvals/batch/{batch_key}/reject` | approvals | no explicit auth dep | `AUTH_REQUIRED` | user/admin | `approvals:resolve` | yes | `org+actor:approval_batch_resolve` | yes | no | `backend/tests/test_route_protection_matrix.py` |
| `POST` | `/api/v1/funnel/orders/{order_id}/delivery-access` | funnel operator | `Depends(get_auth_context)` | `AUTH_REQUIRED` | user/admin | `delivery:write` | yes | `org+actor:delivery_grant` | yes | no | `backend/tests/test_org_boundary.py` |
| `GET` | `/api/v1/funnel/delivery-access/{access_id}` | funnel operator | `Depends(get_auth_context)` | `AUTH_REQUIRED` | user/admin | `delivery:read` | yes | `org+actor:delivery_access_get` | yes | no | `backend/tests/test_org_boundary.py` |
| `POST` | `/api/v1/funnel/delivery-access/{access_id}/revoke` | funnel operator | `Depends(get_auth_context)` | `AUTH_REQUIRED` | user/admin | `delivery:write` | yes | `org+actor:delivery_revoke` | yes | no | `backend/tests/test_org_boundary.py` |
| `GET` | `/api/v1/funnel/delivery/{access_token}` | funnel customer | public token verification in service only | `CUSTOMER_TOKEN` | customer | `delivery:read` | token scoped | `delivery:fingerprint` | yes | yes | `backend/tests/test_customer_delivery_auth.py` |
| `POST` | `/api/v1/funnel/events/delivery-opened` | funnel customer | public token verification in service only | `CUSTOMER_TOKEN` | customer | `delivery:read` | token scoped | `delivery:fingerprint` | yes | yes | `backend/tests/test_customer_delivery_auth.py` |
| `POST` | `/api/v1/funnel/webhook/checkout-completed` | funnel webhook | `Depends(get_auth_context)` | `WEBHOOK_SIGNED_TEST_ONLY` | internal/service | signed test webhook | yes | `webhook:checkout_completed` | yes | no | `backend/tests/test_public_routes_rate_limit.py` |
| `GET` | `/api/v1/funnel/analytics/summary` | funnel analytics | `Depends(get_auth_context)` | `AUTH_REQUIRED` | user/admin | `analytics:read` | yes | `org+actor:funnel_analytics` | yes | no | `backend/tests/test_org_boundary.py` |
| `GET` | `/api/v1/funnel/lead-magnets/{slug}` | funnel lead magnet | `Depends(get_auth_context)` | `PUBLIC_RATE_LIMITED` | anonymous | none | no direct org in client contract | `ip+slug:lead_magnet_view` | yes | yes | `backend/tests/test_public_routes_rate_limit.py` |
| `POST` | `/api/v1/funnel/lead-magnets/{slug}/capture` | funnel lead magnet | `Depends(get_auth_context)` | `PUBLIC_RATE_LIMITED` | anonymous | none | no direct org in client contract | `ip+slug:lead_capture` | yes | yes | `backend/tests/test_public_routes_rate_limit.py` |
| `POST` | `/api/v1/funnel/lead-magnets/{slug}/deliver` | funnel lead magnet | `Depends(get_auth_context)` | `PUBLIC_RATE_LIMITED` | anonymous/customer | none | no direct org in client contract | `ip+slug:lead_delivery` | yes | yes | `backend/tests/test_public_routes_rate_limit.py` |
| `POST` | `/api/v1/funnel/products/{product_id}/recommendations` | funnel recommendations | `Depends(get_auth_context)` | `AUTH_REQUIRED` | user/admin | `funnel:write` | yes | `org+actor:recommendation_create` | yes | no | `backend/tests/test_org_boundary.py` |
| `GET` | `/api/v1/funnel/recommendations` | funnel recommendations | `Depends(get_auth_context)` | `AUTH_REQUIRED` | user/admin | `funnel:read` | yes | `org+actor:recommendation_list` | yes | no | `backend/tests/test_org_boundary.py` |
| `POST` | `/api/v1/funnel/recommendations/{rec_id}/submit-for-approval` | funnel recommendations | `Depends(get_auth_context)` | `AUTH_REQUIRED` | user/admin | `approvals:write` | yes | `org+actor:recommendation_submit` | yes | no | `backend/tests/test_org_boundary.py` |
| `POST` | `/api/v1/mcp/` | mcp | raw JSON-RPC, body/header org fallback | `AUTH_REQUIRED` | user/agent/service | `mcp:read` or `mcp:write` per tool | yes | `org+actor:mcp_jsonrpc` | yes | limited | `backend/tests/test_mcp_auth_enforcement.py` |
| `POST` | `/api/v1/mcp/tools/list` | mcp | raw JSON-RPC, body/header org fallback | `AUTH_REQUIRED` | user/agent/service | `mcp:read` | yes | `org+actor:mcp_list` | yes | limited | `backend/tests/test_mcp_auth_enforcement.py` |
| `POST` | `/api/v1/mcp/tools/call` | mcp | raw JSON-RPC, body/header org fallback | `AUTH_REQUIRED` | user/agent/service | per-tool | yes | `org+actor+tool:mcp_call` | yes | limited | `backend/tests/test_mcp_auth_enforcement.py` |

## Priority fixes from the matrix

1. Remove local-dev org fallback from `backend/app/api/mcp.py`.
2. Add auth + org checks to approval batch endpoints.
3. Split funnel public/customer routes away from operator `get_auth_context` dependencies.
4. Align health/readiness exposure with explicit Phase 16 policy instead of implicit mixed behavior.

