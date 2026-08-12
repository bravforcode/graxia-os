# Graxia OS — Migration Plan: Funnel + Agent Implementation

## Current Head

`1e9db9a3b0ba` (merge of funnel foundation + performance indexes)

## Platform

PostgreSQL 15+ via Supabase
Async SQLAlchemy 2.0 with Alembic

## Migration Order

### Wave 1 — Revenue Funnel Extras

| # | Migration | Models | Dependencies |
|---|-----------|--------|-------------|
| 1 | `021_add_delivery_email_events` | DeliveryEmailEvent | FunnelOrder, DeliveryAccess |
| 2 | `022_add_lead_magnets` | LeadMagnet | DigitalProduct (nullable FK) |
| 3 | `023_add_lead_captures` | LeadCapture | LeadMagnet |
| 4 | `024_add_funnel_recommendations` | FunnelRecommendation | DigitalProduct, ApprovalRequest (nullable FK) |
| 5 | `025_add_context_pack` | ContextPack | None |

### Wave 2 — MCP + Audit

| # | Migration | Models | Dependencies |
|---|-----------|--------|-------------|
| 6 | `026_add_mcp_audit_log` | MCPToolAuditLog | None |
| 7 | `027_add_agent_workflow` | AgentWorkflowRun, AgentWorkflowStep | None |
| 8 | `028_add_workspace_mock_actions` | GoogleWorkspaceMockAction | None |

### DeliveryAccess Field Alignment

Existing: `download_count` (int), `max_downloads` (int?), `first_accessed_at`, `last_accessed_at`
V5 Spec: `open_count` (default 0), `first_opened_at`, `last_opened_at`, `expires_at`

**Action:** Add migration to add `order_item_id` (nullable FK), rename `download_count → open_count`, rename `first_accessed_at → first_opened_at`, `last_accessed_at → last_opened_at`, add `metadata_json` JSONB column.

## Safety Rules

- All new models use TenantMixin for org isolation
- Never drop columns in the same migration that adds them
- FKs are nullable where possible
- Index on organization_id for every tenant model
- Unique constraints include organization_id (cross-org safety)
- Use `alembic_safe.py` wrapper, never raw `alembic`

## Rollback Strategy

Each migration has `downgrade()` that reverses the upgrade safely.
Check destructive operations with `scripts/ops/check_destructive_migrations.py`.
