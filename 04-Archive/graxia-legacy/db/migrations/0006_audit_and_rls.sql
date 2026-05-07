-- 0006_audit_and_rls.sql

-- 1. Create Immutable Audit Table
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor_id TEXT NOT NULL,
    actor_type TEXT NOT NULL, -- AGENT, USER, SYSTEM
    event_type TEXT NOT NULL,
    mission_id UUID,
    payload JSONB NOT NULL DEFAULT '{}',
    trace_id TEXT
);

-- Protect audit logs from deletion or updates (Hard Rule compliance)
CREATE OR REPLACE FUNCTION block_audit_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit logs are immutable and cannot be modified or deleted.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_protect_audit_logs
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION block_audit_modification();

-- 2. Setup Row-Level Security (RLS) for Tenant Isolation
-- Apply to core tables
ALTER TABLE missions ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE ledger_entries ENABLE ROW LEVEL SECURITY;

-- Define a policy: Users/Agents can only see data belonging to their tenant
-- This assumes we set a session variable 'app.current_tenant_id'
CREATE POLICY tenant_isolation_policy ON missions
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

CREATE POLICY tenant_isolation_policy ON tasks
    USING (mission_id IN (SELECT id FROM missions WHERE tenant_id = current_setting('app.current_tenant_id')::UUID));

CREATE POLICY tenant_isolation_policy ON ledger_entries
    USING (customer_id IN (SELECT id FROM customers WHERE tenant_id = current_setting('app.current_tenant_id')::UUID));

-- 3. Create Inter-Agent Slack-Mode View (Inter-agent communication log)
CREATE TABLE inter_agent_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_name TEXT NOT NULL, -- e.g., #sales-room
    from_agent TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
