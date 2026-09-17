-- Revenue OS 0012: server-side private digital fulfillment metadata.
-- The value stores only a relative object-store key, never a public URL.
ALTER TABLE IF EXISTS revenue_os_products
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
