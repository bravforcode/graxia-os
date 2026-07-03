# Audit State — graxia-os-funnel

**Role**: auditor (Ruflow Project Gracia)
**Date**: 2026-06-05
**Target**: `C:\Users\menum\graxia-os-funnel`

## Critical findings collected so far

### 1. Secrets exposed (P0)
- `.env.graxia` at project root contains:
  - `STRIPE_SECRET_KEY=sk_live_51SwptU0u86vWnztXNKcs4Ajd...` (LIVE)
  - `STRIPE_PUBLISHABLE_KEY=pk_live_51SwptU0u86vWnztX10iyngMpK...` (LIVE)
  - `GITHUB_TOKEN=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` (PAT)
  - Keys are duplicated (declared twice on lines 2-3 and 5-6).
- This file is NOT a template/example. Real keys.
- `gitleaks-baseline.json` is empty `[]` — gitleaks never ran on the actual file, OR file is gitignored, OR baseline was hand-emptied.

### 2. Sales page does not exist
- No `sales_page/index.html` at root or anywhere in project.
- Only `frontend/index.html` (Vite entry) and `04-Archive/Legacy_Dashboard_Backup/index.html`.
- The "sales page" is the React component `PublicProductPage.tsx`, served inside the auth-protected React SPA. A customer cannot access it without a tenant org_id + slug, and the public route `/f/:org/:slug` only works if the React app is running.

### 3. Funnel API & model are real (not scaffold)
- `funnel_products.py`, `funnel_webhooks.py`, `funnel_delivery.py`, `funnel_analytics.py`, `funnel_ai.py` all exist and have real endpoints.
- `models/funnel.py` has full schema: DigitalProduct, DeliveryAsset, FunnelCheckoutSession, FunnelOrder, FunnelOrderItem, DeliveryAccess, ConversionEvent, LeadMagnet.
- Real Stripe webhook signature verification is implemented.
- BUT: tests mock Stripe checkout creation AND email sending.

### 4. Tests are smoke tests
- `conftest.py` uses **SQLite** (`sqlite+aiosqlite`), NOT PostgreSQL.
- `test_funnel_e2e_flow.py` mocks `create_stripe_checkout_session` and email service.
- `test_output.txt` at root is **empty (0 bytes)** — the "test report" is a phantom.

### 5. Competing app trees
- 5+ top-level app trees: `backend/`, `frontend/`, `core/`, `graxia/`, `xiarchitect/`
- 211 items in `04-Archive/` including:
  - `docker-compose-variants/` (8 variants)
  - `graxia-legacy/` (94 items)
  - `phase-reports/` (65 items of "ACHIEVEMENT" reports)
  - `tests_legacy/` (28 test files marked legacy)
  - `Legacy_Scripts/`, `Scripts-Unused/`, `Legacy_Dashboard_Backup/`
- `.env.staging`, `.env.graxia`, `.env.quant_os`, `.env.cpx11.template`, `.env.quant_os.example`, `.env.example`, `.env.production.template` — 7 env files at root.

### 6. Funnel UI is real but has XSS risk
- `PublicProductPage.tsx` line 205: `<div dangerouslySetInnerHTML={{ __html: product.sales_page_content }} />`
- `sales_page_content` is user-supplied via admin editor. If multi-tenant, cross-tenant script injection.

### 7. Frontend template copy is generic/LLM-generated
- Default content (line 208-214 of PublicProductPage.tsx): "Welcome to {product.name}! This exclusive program features advanced workflow automation systems, tactical framework configurations, and highly-optimized models."
- No real product / offer / pitch exists in code. The admin must write it.

## Still to read
- [ ] backend/app/agents/base.py, lead_hunter.py, outreach_agent.py, email_manager.py
- [ ] docs/secret-inventory.md
- [ ] docs/security-finding-tracker.md
- [ ] 04-Archive/phase-reports/REVENUE_OS_V12_PHASE*_COMPLETE.md
- [ ] 04-Archive/phase-reports/ACHIEVEMENT_100_REPORT.md
- [ ] 04-Archive/phase-reports/GUARANTEE_REPORT.md
- [ ] backend/app/middleware/auth.py
- [ ] backend/pytest.ini
- [ ] backend/tests/test_funnel_webhook_order.py
