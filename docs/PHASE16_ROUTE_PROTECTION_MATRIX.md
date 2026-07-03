# Phase 16 Route Protection Matrix

Every FastAPI route classified by required actor, permission, org scope, rate-limit key, audit-on-deny rule, and test file.

## Classification Legend

| Tag | Meaning | Middleware check |
|-----|---------|-----------------|
| `PUBLIC_SAFE` | No auth, no rate limit (root health, favicon) | None |
| `PUBLIC_RATE_LIMITED` | No auth, rate-limited (login, register, tracking) | RateLimit only |
| `CUSTOMER_TOKEN` | Delivery token auth, rate-limited by token fingerprint | RateLimit by token hash |
| `AUTH_REQUIRED` | Valid JWT required, any role >= "user" | AuthMiddleware |
| `OPERATOR_REQUIRED` | Role >= "operator" | AuthMiddleware + role check |
| `ADMIN_REQUIRED` | Role == "admin" | AuthMiddleware + role check |
| `INTERNAL_SERVICE` | Internal API key header | verify_internal_api_key |
| `WEBHOOK_SIGNED` | HMAC-signed webhook | AuthMiddleware internal check |
| `DANGEROUS_BLOCKED` | Blocked surface (docs, metrics in strict mode) | AuthMiddleware blocks |

## Route Inventory

### Authentication & Users (`/api/v1/auth`)

| Method | Path | Classification | Rate-limit key | Deny audit event | Test |
|--------|------|---------------|----------------|-----------------|------|
| POST | /api/v1/auth/register | PUBLIC_RATE_LIMITED | `register` | auth.invalid | test_auth_registration |
| POST | /api/v1/auth/social-login | PUBLIC_RATE_LIMITED | `login` | auth.invalid | test_auth_social |
| POST | /api/v1/auth/login | PUBLIC_RATE_LIMITED | `login` | auth.invalid | test_auth_login |
| POST | /api/v1/auth/refresh | PUBLIC_RATE_LIMITED | `refresh` | auth.invalid | test_auth_refresh |
| POST | /api/v1/auth/logout | PUBLIC_SAFE | - | - | test_auth_logout |
| POST | /api/v1/auth/test-session | PUBLIC_SAFE | - | - | test_auth_session |
| GET | /api/v1/auth/me | AUTH_REQUIRED | `api_read` | auth.missing | test_auth_me |
| PUT | /api/v1/auth/me | AUTH_REQUIRED | `api_write` | auth.missing | test_auth_me |
| POST | /api/v1/auth/change-password | AUTH_REQUIRED | `api_write` | auth.missing | test_auth_password |
| DELETE | /api/v1/auth/me | AUTH_REQUIRED | `api_write` | auth.missing | test_auth_delete |
| GET | /api/v1/auth/me/export | AUTH_REQUIRED | `api_read` | auth.missing | test_auth_export |

### Billing (`/billing`)

| Method | Path | Classification | Rate-limit key | Deny audit event | Test |
|--------|------|---------------|----------------|-----------------|------|
| GET | /billing/plans | PUBLIC_RATE_LIMITED | `api_read` | - | test_billing_plans |
| POST | /billing/checkout | AUTH_REQUIRED | `checkout` | permission.denied | test_billing_checkout |
| POST | /billing/portal | AUTH_REQUIRED | `api_write` | permission.denied | test_billing_portal |
| GET | /billing/usage | AUTH_REQUIRED | `api_read` | permission.denied | test_billing_usage |
| POST | /billing/cancel | AUTH_REQUIRED | `api_write` | permission.denied | test_billing_cancel |

### Funnel — Delivery & Public

| Method | Path | Classification | Rate-limit key | Deny audit event | Test |
|--------|------|---------------|----------------|-----------------|------|
| POST | /api/v1/funnel/orders/{order_id}/delivery-access | AUTH_REQUIRED | `api_write` | permission.denied | test_funnel_delivery_access |
| GET | /api/v1/funnel/delivery-access/{access_id} | AUTH_REQUIRED | `api_read` | permission.denied | test_funnel_delivery_access |
| POST | /api/v1/funnel/delivery-access/{access_id}/revoke | AUTH_REQUIRED | `api_write` | permission.denied | test_funnel_delivery_access |
| GET | /api/v1/funnel/delivery/{access_token} | CUSTOMER_TOKEN | `delivery` | customer_token.invalid | test_public_routes_rate_limit |
| POST | /api/v1/funnel/webhook/checkout-completed | AUTH_REQUIRED | `api_write` | permission.denied | test_funnel_webhook |
| GET | /api/v1/funnel/analytics/summary | AUTH_REQUIRED | `api_read` | permission.denied | test_funnel_analytics |
| GET | /api/v1/funnel/products/{product_id}/analytics | AUTH_REQUIRED | `api_read` | permission.denied | test_funnel_analytics |
| GET | /api/v1/funnel/products/{product_id}/conversion | AUTH_REQUIRED | `api_read` | permission.denied | test_funnel_analytics |
| GET | /api/v1/funnel/products/{product_id}/delivery-open-rate | AUTH_REQUIRED | `api_read` | permission.denied | test_funnel_analytics |
| POST | /api/v1/funnel/events/product-view | PUBLIC_RATE_LIMITED | `api_write` | - | test_funnel_events |
| POST | /api/v1/funnel/events/delivery-opened | CUSTOMER_TOKEN | `delivery` | customer_token.invalid | test_public_routes_rate_limit |
| GET | /api/v1/funnel/lead-magnets/{slug} | AUTH_REQUIRED | `api_read` | permission.denied | test_funnel_lead_magnet |
| POST | /api/v1/funnel/lead-magnets/{slug}/capture | AUTH_REQUIRED | `lead_capture` | permission.denied | test_funnel_lead_capture |
| POST | /api/v1/funnel/lead-magnets/{slug}/deliver | AUTH_REQUIRED | `api_write` | permission.denied | test_funnel_lead_magnet |
| POST | /api/v1/funnel/products/{product_id}/recommendations | AUTH_REQUIRED | `api_write` | permission.denied | test_funnel_recommendations |
| GET | /api/v1/funnel/recommendations | AUTH_REQUIRED | `api_read` | permission.denied | test_funnel_recommendations |
| GET | /api/v1/funnel/recommendations/{rec_id} | AUTH_REQUIRED | `api_read` | permission.denied | test_funnel_recommendations |
| POST | /api/v1/funnel/recommendations/{rec_id}/submit-for-approval | AUTH_REQUIRED | `api_write` | permission.denied | test_funnel_recommendations |

### Contacts

| Method | Path | Classification | Rate-limit key | Deny audit event | Test |
|--------|------|---------------|----------------|-----------------|------|
| GET | /api/v1/contacts | AUTH_REQUIRED | `api_read` | permission.denied | test_contacts |
| GET | /api/v1/contacts/stats | AUTH_REQUIRED | `api_read` | permission.denied | test_contacts |
| POST | /api/v1/contacts | AUTH_REQUIRED | `api_write` | permission.denied | test_contacts |
| POST | /api/v1/contacts/bulk | AUTH_REQUIRED | `api_write` | permission.denied | test_contacts |
| GET | /api/v1/contacts/{contact_id} | AUTH_REQUIRED | `api_read` | permission.denied | test_contacts |
| PATCH | /api/v1/contacts/{contact_id} | AUTH_REQUIRED | `api_write` | permission.denied | test_contacts |
| DELETE | /api/v1/contacts/{contact_id} | AUTH_REQUIRED | `api_write` | permission.denied | test_contacts |

### Opportunities

| Method | Path | Classification | Rate-limit key | Deny audit event | Test |
|--------|------|---------------|----------------|-----------------|------|
| GET | /api/v1/opportunities | AUTH_REQUIRED | `api_read` | permission.denied | test_opportunities |
| GET | /api/v1/opportunities/high-score | AUTH_REQUIRED | `api_read` | permission.denied | test_opportunities |
| GET | /api/v1/opportunities/{opp_id} | AUTH_REQUIRED | `api_read` | permission.denied | test_opportunities |
| PATCH | /api/v1/opportunities/{opp_id}/approve | AUTH_REQUIRED | `api_write` | permission.denied | test_opportunities |
| PATCH | /api/v1/opportunities/{opp_id}/skip | AUTH_REQUIRED | `api_write` | permission.denied | test_opportunities |
| POST | /api/v1/opportunities | AUTH_REQUIRED | `api_write` | permission.denied | test_opportunities |
| POST | /api/v1/opportunities/{opp_id}/score | AUTH_REQUIRED | `api_write` | permission.denied | test_opportunities |
| POST | /api/v1/opportunities/{opp_id}/decide | AUTH_REQUIRED | `api_write` | permission.denied | test_opportunities |
| POST | /api/v1/opportunities/{opp_id}/draft | AUTH_REQUIRED | `api_write` | permission.denied | test_opportunities |
| GET | /api/v1/opportunities/{opp_id}/drafts | AUTH_REQUIRED | `api_read` | permission.denied | test_opportunities |

### Approvals

| Method | Path | Classification | Rate-limit key | Deny audit event | Test |
|--------|------|---------------|----------------|-----------------|------|
| GET | /api/v1/approvals | OPERATOR_REQUIRED | `api_read` | permission.denied | test_approvals |
| GET | /api/v1/approvals/{approval_id} | OPERATOR_REQUIRED | `api_read` | permission.denied | test_approvals |
| PATCH | /api/v1/approvals/{approval_id}/approve | OPERATOR_REQUIRED | `api_write` | permission.denied | test_approvals |
| PATCH | /api/v1/approvals/{approval_id}/reject | OPERATOR_REQUIRED | `api_write` | permission.denied | test_approvals |
| PATCH | /api/v1/approvals/batch/{batch_key}/approve | OPERATOR_REQUIRED | `api_write` | permission.denied | test_approvals |
| PATCH | /api/v1/approvals/batch/{batch_key}/reject | OPERATOR_REQUIRED | `api_write` | permission.denied | test_approvals |

### Admin & System

| Method | Path | Classification | Rate-limit key | Deny audit event | Test |
|--------|------|---------------|----------------|-----------------|------|
| GET | /api/v1/admin/audit-logs | ADMIN_REQUIRED | `admin` | permission.denied | test_admin |
| GET | /api/v1/admin/dlq | ADMIN_REQUIRED | `admin` | permission.denied | test_admin |
| POST | /api/v1/admin/dlq/{message_id}/replay | ADMIN_REQUIRED | `admin` | permission.denied | test_admin |
| GET | /api/v1/admin/runtime | ADMIN_REQUIRED | `admin` | permission.denied | test_admin |

### Events & Scrapers

| Method | Path | Classification | Rate-limit key | Deny audit event | Test |
|--------|------|---------------|----------------|-----------------|------|
| GET | /api/v1/events/stats | ADMIN_REQUIRED | `admin` | permission.denied | test_events |
| GET | /api/v1/events/failed | ADMIN_REQUIRED | `admin` | permission.denied | test_events |
| POST | /api/v1/events/replay/{index} | ADMIN_REQUIRED | `admin` | permission.denied | test_events |
| DELETE | /api/v1/events/failed/{index} | ADMIN_REQUIRED | `admin` | permission.denied | test_events |
| DELETE | /api/v1/events/failed | ADMIN_REQUIRED | `admin` | permission.denied | test_events |
| GET | /api/v1/events/health | ADMIN_REQUIRED | `admin` | permission.denied | test_events |
| GET | /api/v1/scrapers/health | ADMIN_REQUIRED | `admin` | permission.denied | test_scrapers |
| GET | /api/v1/scrapers/health/{scraper_name} | ADMIN_REQUIRED | `admin` | permission.denied | test_scrapers |
| GET | /api/v1/scrapers/stats | ADMIN_REQUIRED | `admin` | permission.denied | test_scrapers |

### MCP

| Method | Path | Classification | Rate-limit key | Deny audit event | Test |
|--------|------|---------------|----------------|-----------------|------|
| POST | /api/v1/mcp | AUTH_REQUIRED | `mcp` | mcp.permission.denied | test_mcp |
| POST | /api/v1/mcp/tools/list | AUTH_REQUIRED | `mcp` | mcp.permission.denied | test_mcp |
| POST | /api/v1/mcp/tools/call | AUTH_REQUIRED | `mcp` | mcp.permission.denied | test_mcp_auth_enforcement |

### Health & Readiness

| Method | Path | Classification | Rate-limit key | Deny audit event | Test |
|--------|------|---------------|----------------|-----------------|------|
| GET | /api/v1/health | AUTH_REQUIRED | `health` | auth.missing | test_health_readiness |
| GET | /api/v1/health/readiness | AUTH_REQUIRED | `health` | auth.missing | test_health_readiness |
| GET | /api/v1/health/readiness/local-agent | AUTH_REQUIRED | `health` | auth.missing | test_health_readiness |
| GET | /api/v1/health/readiness/staging | AUTH_REQUIRED | `health` | auth.missing | test_staging_auth_readiness |
| GET | /api/v1/health/readiness/production | AUTH_REQUIRED | `health` | auth.missing | test_production_auth_gate |

### Tracking (Public)

| Method | Path | Classification | Rate-limit key | Deny audit event | Test |
|--------|------|---------------|----------------|-----------------|------|
| GET | /t/open.gif | PUBLIC_RATE_LIMITED | `delivery` | - | test_tracking |
| GET | /t/click | PUBLIC_RATE_LIMITED | `delivery` | - | test_tracking |

### Audit

| Method | Path | Classification | Rate-limit key | Deny audit event | Test |
|--------|------|---------------|----------------|-----------------|------|
| GET | /api/v1/audit/events | AUTH_REQUIRED | `api_read` | permission.denied | test_audit_query |
| GET | /api/v1/audit/mcp | AUTH_REQUIRED | `api_read` | permission.denied | test_audit_query |
| GET | /api/v1/audit/workflows | AUTH_REQUIRED | `api_read` | permission.denied | test_audit_query |
| GET | /api/v1/audit/approvals | AUTH_REQUIRED | `api_read` | permission.denied | test_audit_query |

### Internal Service

| Method | Path | Classification | Rate-limit key | Deny audit event | Test |
|--------|------|---------------|----------------|-----------------|------|
| GET | /internal/health | INTERNAL_SERVICE | - | auth.invalid | test_internal |
| POST | /internal/run-lead-hunter | INTERNAL_SERVICE | - | auth.invalid | test_internal |
| POST | /internal/daily-report | INTERNAL_SERVICE | - | auth.invalid | test_internal |
| POST | /internal/cleanup | INTERNAL_SERVICE | - | auth.invalid | test_internal |
| POST | /internal/backup | INTERNAL_SERVICE | - | auth.invalid | test_internal |
| GET | /internal/queue-status | INTERNAL_SERVICE | - | auth.invalid | test_internal |

### Root

| Method | Path | Classification | Rate-limit key | Deny audit event | Test |
|--------|------|---------------|----------------|-----------------|------|
| GET | / | PUBLIC_SAFE | - | - | - |
| GET | /health | PUBLIC_SAFE | - | - | - |
| GET | /favicon.ico | PUBLIC_SAFE | - | - | - |

### Blocked Surfaces

| Path | Classification | Notes |
|------|---------------|-------|
| /docs | DANGEROUS_BLOCKED (STRICT) | Blocked when STRICT_BOOTSTRAP=True |
| /redoc | DANGEROUS_BLOCKED (STRICT) | Blocked when STRICT_BOOTSTRAP=True |
| /openapi.json | DANGEROUS_BLOCKED (STRICT) | Blocked when STRICT_BOOTSTRAP=True |
| /metrics | DANGEROUS_BLOCKED | Always blocked from external |
| /flower | DANGEROUS_BLOCKED | Always blocked |
| /admin | DANGEROUS_BLOCKED | Always blocked |

## Summary Statistics

| Classification | Count |
|---------------|-------|
| PUBLIC_SAFE | 4 |
| PUBLIC_RATE_LIMITED | 10 |
| CUSTOMER_TOKEN | 2 |
| AUTH_REQUIRED | 55+ |
| OPERATOR_REQUIRED | 6 |
| ADMIN_REQUIRED | 15+ |
| INTERNAL_SERVICE | 6 |
| WEBHOOK_SIGNED | 2 |
| DANGEROUS_BLOCKED | 6 |
