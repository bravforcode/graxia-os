# Digital Product Funnel OS — Complete Technical Reference

**Version:** 1.0 | **Backend:** FastAPI + SQLAlchemy + PostgreSQL | **Payments:** Stripe

---

## Overview

Graxia OS ships with a production-ready **Digital Product Funnel OS** — a complete end-to-end system for selling digital products, delivering them automatically, capturing leads, and optimizing conversion via AI-powered recommendations.

### What's included

| Component | Description | Status |
|---|---|---|
| Digital Product Catalog | CRUD with publish/archive workflow | ✅ Live |
| Delivery Asset Management | Files, URLs, content bodies | ✅ Live |
| Stripe Checkout Integration | Hosted checkout sessions | ✅ Live |
| Stripe Webhook Handler | Order creation from payment events | ✅ Live |
| Automatic Delivery | Signed token-based secure delivery | ✅ Live |
| Customer Email Notification | Delivery email sent post-purchase | ✅ Live |
| Lead Magnet Capture | Opt-in + free product delivery | ✅ Live |
| Conversion Analytics | Event tracking + funnel metrics | ✅ Live |
| AI Funnel Recommendations | Health score + prioritized actions | ✅ Live |
| Admin Frontend | React SPA with all management pages | ✅ Live |
| Public Sales Pages | Customer-facing product + checkout | ✅ Live |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    PUBLIC BUYER JOURNEY                          │
│                                                                  │
│  [Sales Page]  →  [Lead Capture]  →  [Stripe Checkout]          │
│       /f/:org/:slug     /public/funnel/lead-magnets/:slug/capture│
│                                           ↓                      │
│                                    [Stripe Webhook]              │
│                                    /funnel/webhooks/stripe       │
│                                           ↓                      │
│                              [FunnelOrder created]               │
│                              [DeliveryAccess granted]            │
│                              [Email sent to buyer]               │
│                                           ↓                      │
│                              [Delivery Link /delivery/:token]    │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                      ADMIN DASHBOARD                             │
│                                                                  │
│  [Products]  [Assets]  [Analytics]  [Lead Magnets]  [AI Recs]   │
│  /products   /assets   /analytics   /lead-magnets   /ai/recs     │
└──────────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### Core Tables

#### `digital_products`
The product catalog. Each product belongs to an `organization_id`.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `organization_id` | UUID | FK → organizations, indexed |
| `name` | VARCHAR(255) | Required |
| `slug` | VARCHAR(100) | Unique per org |
| `description` | TEXT | Full sales copy |
| `short_description` | VARCHAR(500) | For cards/previews |
| `product_type` | VARCHAR(50) | `ebook`, `course`, `kit`, `template`, `lead_magnet`, `other` |
| `price_amount` | NUMERIC(12,2) | ≥ 0 |
| `currency` | VARCHAR(3) | Default: `THB` |
| `status` | VARCHAR(20) | `draft` → `published` → `archived` |
| `stripe_price_id` | VARCHAR(100) | Required for live checkout |
| `stripe_product_id` | VARCHAR(100) | Optional |
| `cover_image_url` | TEXT | Product thumbnail |
| `sales_page_content` | TEXT | Markdown/HTML |
| `published_at` | TIMESTAMP | Set on publish |

#### `delivery_assets`
Files or content delivered to buyers.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `organization_id` | UUID | FK → organizations |
| `product_id` | UUID | FK → digital_products |
| `asset_type` | VARCHAR(50) | `file`, `video`, `url`, `content` |
| `title` | VARCHAR(255) | Display name |
| `storage_path` | TEXT | S3/storage bucket path |
| `external_url` | TEXT | For `url`/`video` types |
| `content_body` | TEXT | For `content` type (markdown) |
| `is_active` | BOOLEAN | Soft delete |

#### `funnel_checkout_sessions`
Local mirror of Stripe checkout sessions.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `organization_id` | UUID | FK |
| `product_id` | UUID | FK |
| `stripe_session_id` | VARCHAR(255) | Unique |
| `status` | VARCHAR(20) | `pending`, `paid`, `failed`, `expired` |
| `amount` | NUMERIC(12,2) | |
| `currency` | VARCHAR(3) | |
| `customer_email` | VARCHAR(255) | |
| `checkout_url` | TEXT | Stripe hosted URL |

#### `funnel_orders`
Confirmed paid orders, created by webhook.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `organization_id` | UUID | FK |
| `stripe_session_id` | VARCHAR(255) | Unique, for idempotency |
| `status` | VARCHAR(20) | `pending`, `paid`, `refunded`, `cancelled` |
| `total_amount` | NUMERIC(12,2) | |
| `customer_email` | VARCHAR(255) | |
| `paid_at` | TIMESTAMP | |

#### `delivery_access`
Secure download tokens granting access to assets.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `organization_id` | UUID | FK |
| `order_id` | UUID | FK → funnel_orders |
| `product_id` | UUID | FK → digital_products |
| `token` | VARCHAR(255) | Unique, signed |
| `status` | VARCHAR(20) | `active`, `consumed`, `expired` |
| `expires_at` | TIMESTAMP | Default: 7 days |
| `downloads_remaining` | INTEGER | Default: 5 |

#### `conversion_events`
Funnel analytics event log.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `organization_id` | UUID | FK |
| `event_type` | VARCHAR(50) | `page_view`, `lead_capture`, `checkout_start`, `checkout_success`, `purchase`, `delivery_opened` |
| `product_id` | UUID | Optional FK |
| `contact_id` | UUID | Optional FK |
| `order_id` | UUID | Optional FK |
| `session_id` | VARCHAR(255) | Browser session |
| `source` | VARCHAR(100) | Traffic source |
| `medium` | VARCHAR(100) | Traffic medium |
| `campaign` | VARCHAR(100) | UTM campaign |
| `occurred_at` | TIMESTAMP | |

---

## API Reference

### Base URL
```
/api/v1/funnel/
```

### Authentication
All admin endpoints require a JWT Bearer token in the `Authorization` header.
Public endpoints (prefixed with `/public/`) require no authentication.

---

### Products API

#### `POST /api/v1/funnel/products` — Create product
```json
{
  "name": "AI Starter Kit",
  "slug": "ai-starter-kit",
  "description": "Full description...",
  "price_amount": "499.00",
  "currency": "THB",
  "product_type": "kit",
  "stripe_price_id": "price_xxxxxxxx"
}
```
Response: `201 Created` → DigitalProduct object

#### `GET /api/v1/funnel/products` — List products
Query params: `include_archived=false`, `limit=50`, `offset=0`

#### `GET /api/v1/funnel/products/{id}` — Get product

#### `PATCH /api/v1/funnel/products/{id}` — Update product

#### `POST /api/v1/funnel/products/{id}/publish` — Publish product
Validates: name, price > 0, slug, at least 1 active asset. Returns `400` if validation fails.

#### `POST /api/v1/funnel/products/{id}/archive` — Archive product

#### `DELETE /api/v1/funnel/products/{id}` — Delete product

---

### Delivery Assets API

#### `POST /api/v1/funnel/products/{product_id}/assets` — Add asset
```json
{
  "asset_type": "content",
  "title": "Module 1 Guide",
  "content_body": "# Welcome\n..."
}
```
Asset types: `file` | `video` | `url` | `content`

#### `GET /api/v1/funnel/products/{product_id}/assets` — List assets
#### `GET /api/v1/funnel/assets/{asset_id}` — Get asset
#### `PATCH /api/v1/funnel/assets/{asset_id}` — Update asset
#### `POST /api/v1/funnel/assets/{asset_id}/deactivate` — Deactivate asset

---

### Checkout API

#### `POST /api/v1/funnel/products/{id}/checkout` — Create checkout (admin/auth)
```json
{
  "customer_email": "buyer@example.com",
  "success_url": "https://yoursite.com/success?session_id={CHECKOUT_SESSION_ID}",
  "cancel_url": "https://yoursite.com/cancel"
}
```

#### `GET /api/v1/funnel/public/products/{org_id}/{slug}` — Get public product by slug
Public. Returns product info for rendering the sales page.

#### `POST /api/v1/funnel/public/products/{product_id}/checkout` — Create public checkout
Public. `organization_id` must match product's org.
```json
{
  "organization_id": "uuid",
  "customer_email": "buyer@example.com",
  "success_url": "https://yourapp.com/checkout/success",
  "cancel_url": "https://yourapp.com/cancel"
}
```

---

### Stripe Webhook

#### `POST /api/v1/funnel/webhooks/stripe`
Handles `checkout.session.completed` events.

**Required Stripe metadata on checkout session:**
```json
{
  "product_id": "<uuid>",
  "organization_id": "<uuid>"
}
```

**What happens on a successful webhook:**
1. Verifies Stripe signature (`STRIPE_WEBHOOK_SECRET`)
2. Checks idempotency (skips if order already exists for `stripe_session_id`)
3. Creates `FunnelOrder` with status `paid`
4. Creates `FunnelOrderItem` linked to product
5. Grants `DeliveryAccess` with signed token (7-day expiry)
6. Triggers delivery email to buyer

---

### Delivery API

#### `GET /api/v1/funnel/delivery/{token}` — View delivery payload
Public. Returns asset info without consuming a download.
```json
{
  "product_name": "AI Starter Kit",
  "asset_title": "Complete Guide PDF",
  "asset_type": "content",
  "content_body": "# Welcome...",
  "expires_at": "2025-06-01T00:00:00",
  "downloads_remaining": 5
}
```

#### `POST /api/v1/funnel/delivery/{token}/consume` — Consume delivery
Decrements `downloads_remaining`. Returns `404` if token expired or exhausted.

**Error cases:**
- `404` if token not found
- `404` if token expired (`expires_at` in the past)
- `404` if `downloads_remaining` ≤ 0

---

### Analytics API

#### `GET /api/v1/funnel/analytics/summary` — Summary metrics
Query params: `product_id` (optional), `start_date`, `end_date`

Response:
```json
{
  "views": 1250,
  "unique_visitors": 980,
  "leads": 62,
  "checkout_starts": 38,
  "purchases": 22,
  "delivery_opened": 18,
  "lead_conversion_rate": 4.96,
  "checkout_rate": 3.04,
  "purchase_conversion_rate": 1.76,
  "checkout_to_purchase_rate": 57.89,
  "sales_count": 22,
  "total_revenue": 10978.00,
  "average_order_value": 498.9
}
```

#### `GET /api/v1/funnel/analytics/daily` — Daily breakdown
Query params: `start_date`, `end_date`

#### `POST /api/v1/funnel/events` — Log public event
Public.
```json
{
  "organization_id": "uuid",
  "event_type": "page_view",
  "product_id": "uuid",
  "session_id": "sess-xxx",
  "source": "google",
  "medium": "organic"
}
```
Event types: `page_view` | `lead_capture` | `checkout_start` | `checkout_success` | `purchase` | `delivery_opened`

---

### Lead Magnets API

#### `POST /api/v1/funnel/lead-magnets` — Create lead magnet
#### `GET /api/v1/funnel/lead-magnets` — List
#### `GET /api/v1/funnel/lead-magnets/{id}` — Get
#### `PUT /api/v1/funnel/lead-magnets/{id}` — Update
#### `DELETE /api/v1/funnel/lead-magnets/{id}` — Delete

#### `POST /api/v1/public/funnel/lead-magnets/{slug}/capture` — Capture lead (public)
```json
{
  "organization_id": "uuid",
  "email": "user@example.com",
  "name": "Jane Doe",
  "source": "blog",
  "medium": "organic"
}
```
Response:
```json
{
  "contact_id": "uuid",
  "raw_token": "tok_xxx",        // if free product delivery configured
  "delivery_url": "/delivery/tok_xxx"
}
```

---

### AI Recommendations API

#### `GET /api/v1/funnel/ai/recommendations` — Get funnel recommendations
Query params: `product_id` (optional), `days_back=30`, `max_recommendations=10`

Response:
```json
{
  "health_score": {
    "overall": 42,
    "conversion": 35,
    "traffic": 25,
    "revenue": 0,
    "delivery": 70,
    "label": "Needs Work",
    "summary": "Several critical issues need attention before scaling."
  },
  "recommendations": [
    {
      "id": "no-stripe-abc12345",
      "title": "'AI Starter Kit' has no Stripe price linked",
      "description": "This product is published but has no Stripe price ID...",
      "action": "Create a product and price in your Stripe dashboard...",
      "priority": "critical",
      "category": "product",
      "impact_estimate": "Required for checkout to function",
      "effort": "low",
      "metric_trigger": "stripe_price_id",
      "product_id": "uuid",
      "product_name": "AI Starter Kit"
    }
  ],
  "metrics_snapshot": { ... },
  "analysis_period_days": 30,
  "generated_at": "2025-05-22T18:00:00",
  "total_recommendations": 4
}
```

**Priority levels:** `critical` → `high` → `medium` → `low`
**Categories:** `conversion`, `pricing`, `traffic`, `delivery`, `email`, `product`, `retention`

#### `GET /api/v1/funnel/ai/recommendations/products/{product_id}` — Product-scoped recommendations

---

## Frontend Pages

| Route | Component | Description |
|---|---|---|
| `/products` | `ProductList.tsx` | Admin product catalog with status, revenue, quick actions |
| `/products/new` | `ProductEditor.tsx` | Create/edit product with asset management |
| `/products/:id` | `ProductEditor.tsx` | Edit product |
| `/funnel/analytics` | `FunnelAnalytics.tsx` | Revenue dashboard, conversion funnel, daily chart |
| `/f/:org_id/:slug` | `PublicProductPage.tsx` | Public sales landing page |
| `/checkout/success` | `CheckoutSuccess.tsx` | Post-purchase confirmation |
| `/delivery/:token` | `DeliveryAccessPage.tsx` | Secure asset download page |

---

## Stripe Configuration

### Environment Variables
```env
STRIPE_SECRET_KEY=sk_live_xxxx         # or sk_test_xxxx for testing
STRIPE_WEBHOOK_SECRET=whsec_xxxx       # from Stripe dashboard → Webhooks
STRIPE_PUBLISHABLE_KEY=pk_live_xxxx    # used by frontend
```

### Stripe Dashboard Setup
1. Create a Product for each digital product
2. Create a Price (one-time) for each product
3. Copy `price_id` into the `stripe_price_id` field of the DigitalProduct
4. Create a Webhook endpoint pointing to: `https://yourdomain.com/api/v1/funnel/webhooks/stripe`
5. Select event: `checkout.session.completed`
6. Copy the webhook signing secret to `STRIPE_WEBHOOK_SECRET`

### Checkout Session Metadata (Required)
When creating checkout sessions, the webhook handler requires these metadata fields:
```python
metadata={
    "product_id": str(product.id),
    "organization_id": str(product.organization_id),
}
```
This is automatically set by `FunnelCheckoutService`.

---

## Launch Checklist

Before going live, verify every item:

### Backend
- [ ] `STRIPE_SECRET_KEY` set to live key (`sk_live_`)
- [ ] `STRIPE_WEBHOOK_SECRET` configured from Stripe dashboard
- [ ] Database migrations run (`alembic upgrade head`)
- [ ] At least 1 product published with `stripe_price_id` set
- [ ] At least 1 delivery asset added to published product
- [ ] Email service configured (SMTP or SendGrid/Resend)
- [ ] `FRONTEND_URL` set for correct delivery email links
- [ ] All 65 existing tests pass

### Stripe
- [ ] Stripe account in live mode
- [ ] Webhook endpoint created and verified
- [ ] Test checkout works end-to-end in test mode first
- [ ] Price IDs match between Stripe and database

### Frontend
- [ ] `VITE_API_URL` points to production backend
- [ ] `VITE_STRIPE_PUBLISHABLE_KEY` set
- [ ] Public sales page URL works: `/f/{org_id}/{slug}`
- [ ] Checkout success page displays correctly
- [ ] Delivery access page loads assets for valid tokens

---

## Conversion Benchmarks

The AI recommendation engine uses these industry benchmarks:

| Metric | Benchmark | Notes |
|---|---|---|
| Lead conversion rate | 2.5% | Views → Lead captures |
| Checkout rate | 3.0% | Views → Checkout starts |
| Checkout → Purchase | 60% | Checkout starts → Paid |
| Overall purchase rate | 1.5% | Views → Purchases |
| Delivery open rate | 70% | Buyers who open delivery |
| Minimum traffic | 50 views | Before conversion analysis |

---

## Security Model

### Delivery Token Security
- Tokens are UUID-based, cryptographically random
- 7-day expiry by default
- 5 downloads allowed by default
- Tokens are validated against: `organization_id`, `expires_at`, `status`, `downloads_remaining`

### Webhook Security
- Stripe signature is verified using `stripe.Webhook.construct_event`
- Idempotency: duplicate webhooks for the same `stripe_session_id` are ignored

### Multi-tenant Isolation
- Every model has `organization_id`
- All service methods require `organization_id` — cross-org queries return `None` / `404`
- Tests validate cross-org isolation for every endpoint

---

## Testing

### Run all funnel tests
```bash
$env:APP_ENV="testing"; $env:TESTING="true"; $env:DATABASE_URL="sqlite+aiosqlite:///./test_funnel.db"; $env:REDIS_ENABLED="false"
python -m pytest backend/tests/ -k "funnel or lead_magnet or e2e" -v
```

### Test files

| File | Coverage |
|---|---|
| `test_funnel_foundation.py` | Model constraints, relationships |
| `test_funnel_product_api.py` | CRUD, publish, archive, asset management |
| `test_funnel_checkout_api.py` | Checkout creation, public endpoints |
| `test_funnel_webhook_order.py` | Webhook → order creation |
| `test_funnel_webhook_delivery.py` | Webhook → delivery access |
| `test_funnel_delivery.py` | Token lookup, consumption, expiry |
| `test_funnel_delivery_email.py` | Email service, error handling |
| `test_funnel_analytics.py` | Event logging, metrics, tenant isolation |
| `test_lead_magnet_api.py` | Lead magnet CRUD, public capture |
| `test_funnel_ai_recommendations.py` | AI engine, health score, API |
| `test_funnel_e2e_flow.py` | Complete buyer journey |

---

## Revenue Optimization Playbook

### Week 1: Foundation
1. Publish your first product with a compelling sales page
2. Add all delivery assets and test the download link
3. Configure Stripe and do a test purchase
4. Verify the delivery email arrives

### Week 2: Traffic
1. Share your product URL in 2-3 relevant communities
2. Create a lead magnet to start building your email list
3. Track your first 50 page views in the analytics dashboard

### Week 3: Conversion
1. Check AI recommendations dashboard for blockers
2. Improve CTA button visibility and copy
3. Add social proof (testimonials, purchase count)
4. Set up abandoned checkout email sequence

### Week 4: Scale
1. Analyze top traffic sources, double down on the best
2. Create a higher-tier bundle (2-3x price point)
3. Set up email nurture for leads who haven't purchased
4. Target: 1%+ overall conversion rate = $X/month predictable revenue
