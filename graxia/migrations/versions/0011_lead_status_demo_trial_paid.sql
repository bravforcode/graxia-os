-- Extend LeadStatus enum with demo/trial/paid (spec G4 — lead→paid KPI)
-- NOTE: SAEnum(LeadStatus) persists member NAMES (e.g. 'PAID'), matching the
-- existing enum labels (NEW, CONTACTED, ...). PostgreSQL 12+ supports ADD VALUE.
ALTER TYPE leadstatus ADD VALUE IF NOT EXISTS 'DEMO';
ALTER TYPE leadstatus ADD VALUE IF NOT EXISTS 'TRIAL';
ALTER TYPE leadstatus ADD VALUE IF NOT EXISTS 'PAID';