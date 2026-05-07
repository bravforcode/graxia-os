-- ============================================================
-- Migration: 0010_enterprise_revenue_os_merge
-- Description: Integrate Revenue OS v10 schema into Graxia
-- Author: backend-architect subagent
-- Rollback: 0010_rollback.sql
-- ============================================================

BEGIN;

-- ── Extensions ──────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- ── updated_at trigger function ──────────────────────────────────
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ── Core financial tables ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform VARCHAR(50) NOT NULL,
    platform_order_id VARCHAR(255) NOT NULL,
    customer_email VARCHAR(320) NOT NULL,
    customer_name VARCHAR(255),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    metadata JSONB,
    idempotency_key VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_orders_platform_order UNIQUE (platform, platform_order_id)
);
CREATE INDEX IF NOT EXISTS ix_orders_customer_email ON orders(customer_email);
CREATE INDEX IF NOT EXISTS ix_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS ix_orders_created_at ON orders(created_at DESC);

CREATE TRIGGER set_orders_updated_at BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- ── Row-Level Security on orders ──────────────────────────────────
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY orders_tenant_isolation ON orders
    USING (current_setting('app.tenant_id', true) IS NULL
           OR metadata->>'tenant_id' = current_setting('app.tenant_id', true));

-- Ledger entries
CREATE TABLE IF NOT EXISTS ledger_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id),
    entry_type VARCHAR(50) NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents != 0),
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    description TEXT,
    stripe_balance_transaction_id VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_ledger_order_id ON ledger_entries(order_id);
CREATE INDEX IF NOT EXISTS ix_ledger_entry_type ON ledger_entries(entry_type);

-- Refunds
CREATE TABLE IF NOT EXISTS refunds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id),
    platform_refund_id VARCHAR(255) UNIQUE NOT NULL,
    amount_cents INTEGER NOT NULL,
    reason TEXT,
    status VARCHAR(50) NOT NULL,
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_refunds_order_id ON refunds(order_id);
CREATE TRIGGER set_refunds_updated_at BEFORE UPDATE ON refunds
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- Entitlements
CREATE TABLE IF NOT EXISTS entitlements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id),
    customer_email VARCHAR(320) NOT NULL,
    product_key VARCHAR(255) NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    metadata JSONB
);
CREATE INDEX IF NOT EXISTS ix_entitlements_customer_email ON entitlements(customer_email);
CREATE INDEX IF NOT EXISTS ix_entitlements_product_key ON entitlements(product_key);

-- Revenue Campaigns
CREATE TABLE IF NOT EXISTS revenue_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    created_by_agent VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'draft',
    budget_cents INTEGER,
    target_revenue_cents INTEGER,
    actual_revenue_cents INTEGER NOT NULL DEFAULT 0,
    start_date TIMESTAMPTZ,
    end_date TIMESTAMPTZ,
    paused_reason TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_campaigns_status ON revenue_campaigns(status);
CREATE INDEX IF NOT EXISTS ix_campaigns_created_by_agent ON revenue_campaigns(created_by_agent);
CREATE TRIGGER set_revenue_campaigns_updated_at BEFORE UPDATE ON revenue_campaigns
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- Attribution Events
CREATE TABLE IF NOT EXISTS attribution_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID REFERENCES revenue_campaigns(id),
    order_id UUID REFERENCES orders(id),
    event_type VARCHAR(100) NOT NULL,
    channel VARCHAR(100) NOT NULL,
    ad_spend_cents INTEGER,
    revenue_attributed_cents INTEGER,
    customer_email VARCHAR(320),
    utm_source VARCHAR(255),
    utm_medium VARCHAR(255),
    utm_campaign VARCHAR(255),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_attribution_campaign_id ON attribution_events(campaign_id);
CREATE INDEX IF NOT EXISTS ix_attribution_occurred_at ON attribution_events(occurred_at);

-- Leads
CREATE TABLE IF NOT EXISTS leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(320) UNIQUE NOT NULL,
    name VARCHAR(255),
    company VARCHAR(255),
    title VARCHAR(255),
    linkedin_url VARCHAR(512),
    source VARCHAR(100) NOT NULL,
    score INTEGER,
    score_rationale TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'new',
    campaign_id UUID REFERENCES revenue_campaigns(id),
    contacted_at TIMESTAMPTZ,
    converted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS ix_leads_score ON leads(score);
CREATE TRIGGER set_leads_updated_at BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- Approvals
CREATE TABLE IF NOT EXISTS approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_type VARCHAR(100) NOT NULL,
    item_id UUID NOT NULL,
    requested_by_agent VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    ceo_notes TEXT,
    reviewed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_approvals_status ON approvals(status);
CREATE INDEX IF NOT EXISTS ix_approvals_item_type_id ON approvals(item_type, item_id);
CREATE TRIGGER set_approvals_updated_at BEFORE UPDATE ON approvals
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- Email Outbox
CREATE TABLE IF NOT EXISTS email_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    to_email VARCHAR(320) NOT NULL,
    to_name VARCHAR(255),
    subject VARCHAR(998) NOT NULL,
    html_body TEXT NOT NULL,
    text_body TEXT,
    from_email VARCHAR(320) NOT NULL,
    reply_to VARCHAR(320),
    approval_id UUID REFERENCES approvals(id),
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    scheduled_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    resend_message_id VARCHAR(255),
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_email_outbox_status ON email_outbox(status);
CREATE INDEX IF NOT EXISTS ix_email_outbox_scheduled_at ON email_outbox(scheduled_at);

-- Delivery Events
CREATE TABLE IF NOT EXISTS delivery_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id),
    delivery_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'queued',
    email_outbox_id UUID REFERENCES email_outbox(id),
    delivered_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,
    failure_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TRIGGER set_delivery_events_updated_at BEFORE UPDATE ON delivery_events
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- AI Drafts
CREATE TABLE IF NOT EXISTS ai_drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_type VARCHAR(100) NOT NULL,
    generated_by_agent VARCHAR(100) NOT NULL,
    lead_id UUID REFERENCES leads(id),
    campaign_id UUID REFERENCES revenue_campaigns(id),
    content TEXT NOT NULL,
    subject VARCHAR(998),
    anthropic_model VARCHAR(100),
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    approval_id UUID REFERENCES approvals(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Incident Events
CREATE TABLE IF NOT EXISTS incident_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    severity VARCHAR(50) NOT NULL,
    source_agent VARCHAR(100) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT NOT NULL,
    affected_campaign_id UUID REFERENCES revenue_campaigns(id),
    affected_order_id UUID REFERENCES orders(id),
    bwcp_message_id UUID,
    resolved_at TIMESTAMPTZ,
    resolution_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_incidents_severity ON incident_events(severity);
CREATE INDEX IF NOT EXISTS ix_incidents_created_at ON incident_events(created_at);

-- ── automation_locks ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS automation_locks (
    lock_name VARCHAR(255) PRIMARY KEY,
    locked_by_worker VARCHAR(255) NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    heartbeat_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_locks_expires_at ON automation_locks(expires_at);

-- Webhook Events
CREATE TABLE IF NOT EXISTS webhook_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform VARCHAR(50) NOT NULL,
    event_type VARCHAR(255) NOT NULL,
    platform_event_id VARCHAR(255) UNIQUE NOT NULL,
    payload JSONB NOT NULL,
    processed BOOLEAN NOT NULL DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_webhook_events_processed ON webhook_events(processed);
CREATE INDEX IF NOT EXISTS ix_webhook_events_platform_event ON webhook_events(platform, event_type);

-- ── Alembic version stamp ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
);
INSERT INTO alembic_version (version_num) VALUES ('0010') ON CONFLICT DO NOTHING;

COMMIT;
