-- 0007_revenue_ledger.sql

-- 1. Stripe Webhooks (Idempotency and Audit)
CREATE TABLE stripe_webhooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stripe_event_id TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', -- pending, processed, failed
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

-- 2. Revenue Ledger (Dual-Entry)
CREATE TABLE revenue_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    account_type TEXT NOT NULL, -- e.g., 'credits', 'escrow', 'revenue'
    amount NUMERIC(20, 2) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'THB',
    reference_id TEXT, -- e.g., Stripe Payment Intent ID or BWCP Task ID
    description TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Entitlements (Feature Access Control)
CREATE TABLE entitlements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    feature_key TEXT NOT NULL, -- e.g., 'agent_sales_outbound', 'voice_api_access'
    status TEXT NOT NULL DEFAULT 'active', -- active, suspended, expired
    value JSONB DEFAULT '{}', -- e.g., {"limit": 1000, "usage": 0}
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, feature_key)
);

-- 4. Usage Metrics (Aggregated from Redis)
CREATE TABLE usage_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    metric_key TEXT NOT NULL, -- e.g., 'tokens_consumed', 'tasks_completed'
    value NUMERIC(20, 4) NOT NULL DEFAULT 0,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- 5. Row-Level Security (RLS)
-- Identity Broker and Revenue API will use a service role that bypasses RLS for management.
-- Individual tenant agents will be restricted to their own records.

ALTER TABLE revenue_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE entitlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_metrics ENABLE ROW LEVEL SECURITY;

-- Policies for revenue_ledger
CREATE POLICY tenant_read_ledger ON revenue_ledger
    FOR SELECT USING (tenant_id = (current_setting('app.current_tenant_id', true)));

-- Policies for entitlements
CREATE POLICY tenant_read_entitlements ON entitlements
    FOR SELECT USING (tenant_id = (current_setting('app.current_tenant_id', true)));

-- Policies for usage_metrics
CREATE POLICY tenant_read_metrics ON usage_metrics
    FOR SELECT USING (tenant_id = (current_setting('app.current_tenant_id', true)));
