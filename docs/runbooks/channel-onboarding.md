# Channel Onboarding Runbook (Phase 2)

## Shopify

### 1. Create the app
- Shopify admin → Settings → Apps → Develop apps → Create app (or use existing custom app)
- Admin API scopes required: `read_orders`, `write_orders`, `read_products`, `write_products`, `write_fulfillments`
- Install the app on the store; copy the **Admin API access token**

### 2. Env vars
```
SHOPIFY_STORE_DOMAIN=<your-store>.myshopify.com
SHOPIFY_ACCESS_TOKEN=<admin api token>
SHOPIFY_WEBHOOK_SECRET=<random long string>   # used for HMAC verification
```

### 3. Subscribe webhooks (via Shopify admin → Settings → Notifications → Webhooks, or API)
| Topic | URL |
|---|---|
| `orders/paid` | `https://<api-host>/api/channels/shopify/webhook` |
| `orders/create` | `https://<api-host>/api/channels/shopify/webhook` |
| `orders/updated` | `https://<api-host>/api/channels/shopify/webhook` |
| `orders/cancelled` | `https://<api-host>/api/channels/shopify/webhook` |

The webhook endpoint verifies `X-Shopify-Hmac-Sha256` before parsing (fail-closed).

### 4. Product mapping
Add a line-item property `graxia_product_id` = local product UUID when creating products
in Shopify (the sync task reads it back). Orders without it are imported with an
IncidentEvent LOW (unmappable) — fix the property, re-sync.

### 5. Verify
- `POST /api/channels/shopify/sync-products` (admin key) pushes local products
- Wait 5 min for the `shopify-sync` beat job or trigger the import; check
  `GET /api/channels` (admin) for last_sync_at

## POD / dropship supplier (Printful-style)

```
SUPPLIER_API_URL=https://api.printful.com
SUPPLIER_API_KEY=<supplier api key>
SUPPLIER_WEBHOOK_SECRET=<random long string>
```
- Products need `supplier`, `supplier_cost_cents`, `is_physical=true` (DB columns)
- Supplier order submission is policy-gated: margin ≥ 20% and cost ≤ 100,000 THB cents
  (edit via `/api/policy/rules`, admin)
- Status webhook secret must match; tracking numbers flow into the order updates

## Meta Ads

```
META_ACCESS_TOKEN=<long-lived page/system user token>
META_AD_ACCOUNT_ID=<act_...>
```
- Budgets are ONLY changed by the policy-gated ads job (max ±10% / ±50,000 THB cents
  per change, LIMITED mode multiplies the cap). See `docs/runbooks/ads-budgets.md`.

## Rate limits
- Shopify core API: 2 req/s, 40 req/min — the client backs off on 429 (Retry-After)
- Meta Graph: per-app limits — the client retries once on 429
