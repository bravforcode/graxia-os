-- Migration: 0008_revenue_lanes.sql
-- Description: Create revenue lane tables and RLS policies

-- Create sales_proposals table
CREATE TABLE IF NOT EXISTS public.sales_proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'draft' NOT NULL,
    tenant_id UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- Enable RLS for sales_proposals
ALTER TABLE public.sales_proposals ENABLE ROW LEVEL SECURITY;

-- Create policy for sales_proposals
CREATE POLICY "tenant_isolation_sales_proposals" 
ON public.sales_proposals 
AS PERMISSIVE 
FOR ALL 
TO public 
USING (tenant_id = auth.uid()) 
WITH CHECK (tenant_id = auth.uid());

-- Create funding_opportunities table
CREATE TABLE IF NOT EXISTS public.funding_opportunities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(255) NOT NULL,
    url VARCHAR(1024),
    deadline TIMESTAMPTZ,
    fit_score NUMERIC(5,2),
    tenant_id UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- Enable RLS for funding_opportunities
ALTER TABLE public.funding_opportunities ENABLE ROW LEVEL SECURITY;

-- Create policy for funding_opportunities
CREATE POLICY "tenant_isolation_funding_opportunities" 
ON public.funding_opportunities 
AS PERMISSIVE 
FOR ALL 
TO public 
USING (tenant_id = auth.uid()) 
WITH CHECK (tenant_id = auth.uid());
