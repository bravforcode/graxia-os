-- Migration: 0009_trading_outbound.sql

-- Table for tracking outbound email campaigns
CREATE TABLE IF NOT EXISTS email_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    recipient VARCHAR(255) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    sent_at TIMESTAMP WITH TIME ZONE
);

-- Enable Row Level Security (RLS) for email_campaigns
ALTER TABLE email_campaigns ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_email_campaigns ON email_campaigns
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant')::UUID);

-- Table for tracking paper trading ledger/transactions
CREATE TABLE IF NOT EXISTS paper_trading_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    action VARCHAR(20) NOT NULL, -- e.g., 'BUY', 'SELL'
    quantity NUMERIC(15, 6) NOT NULL,
    price NUMERIC(15, 6) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    realized_pnl NUMERIC(15, 6) DEFAULT 0.0
);

-- Enable Row Level Security (RLS) for paper_trading_ledger
ALTER TABLE paper_trading_ledger ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_paper_trading_ledger ON paper_trading_ledger
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant')::UUID);
