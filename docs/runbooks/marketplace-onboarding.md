# Marketplace Onboarding Runbook (Phase 3)

Covers Shopee, Lazada, TikTok Shop and Amazon SP-API connectors. All four are
**poll-first**: marketplace webhooks are NOT a reliable import path (signature
formats vary / none exist), so the beat job `marketplace-poll` polls each
connected channel and imports via the shared idempotent helper. Webhooks (where
supported) only ever trigger a poll.

**Mode gate (critical):** every adapter reads `ChannelConnection.config["mode"]`
(`sandbox` | `live`). In production (`APP_ENV=production`) an unset mode raises —
the adapter refuses to run. In dev the default is `sandbox`. NEVER put a live
credential in an environment whose mode is `sandbox`, and never run `live`
before the checklist at the bottom.

---

## Common setup

1. Create a `ChannelConnection` row per platform (`channel` = `shopee` |
   `lazada` | `tiktok_shop` | `amazon`) with `config: {"mode": "sandbox"}` and
   `enabled: true`. The poll job skips missing/disabled rows.
2. Credentials go in the secrets manager as env vars (never in DB config, never
   committed). The adapter factory reads them at call time and fails closed in
   production if any are missing.
3. Fee rates default per platform (see below); override per store with
   `ChannelConnection.config["fee_rate"]` (e.g. `0.07` = 7%).
4. FX rates for non-THB orders: the `fx-refresh` beat job (daily) writes
   `ChannelConnection(channel="fx").config["fx_rates"] = {"THB": {...}}` from
   `FX_SOURCE_URL` (default `https://open.er-api.com/v6/latest/THB`).

## Shopee

### Env vars
```
SHOPEE_PARTNER_ID=<partner id>
SHOPEE_PARTNER_KEY=<partner key>
SHOPEE_SHOP_ID=<shop id>
SHOPEE_ACCESS_TOKEN=<optional; needed for order APIs in live>
```

### Sandbox setup
- Shopee Open Platform → register a test app → use the sandbox environment
  (`openapi.test.shopee.cn`). Partner key + shop id come from the app dashboard.
- Orders are polled from `/order/get_order_list` with status `READY_TO_SHIP`
  (payment captured → local `paid` → auto-fulfill). `last_import_at` cursor is
  kept in the channel config by the poll job.

### Status map (poll → local)
| Shopee status | Local |
|---|---|
| `READY_TO_SHIP` | `paid` (import) |
| `COMPLETED` | `fulfilled` |
| `CANCELLED` / `IN_CANCEL` | `cancelled` |
| `RETURNED` | `refunded` |

Fulfillment: `push_fulfillment` → `/logistics/ship_order` (needs `order_sn` in
order metadata).

## Lazada

### Env vars
```
LAZADA_APP_KEY=<app key>
LAZADA_APP_SECRET=<app secret>
LAZADA_SELLER_ID=<seller/user id>
```

### Sandbox setup
- Lazada Open Platform → pre-production environment (`api.sellercenter.lazada.sandbox.com`).
- Orders polled from `/orders/get` filtered to `shipped|ready_to_ship|packed`;
  signature covers `user_id` like every other param.

### Status map (poll → local)
| Lazada status | Local |
|---|---|
| `shipped` / `delivered` | `fulfilled` |
| `canceled` | `cancelled` |
| `returned` | `refunded` |

Fulfillment: `push_fulfillment` → `/order/pack` then `/order/ship` (needs
`order_id` + `order_item_id` in metadata).

## TikTok Shop

### Env vars
```
TIKTOK_SHOP_APP_KEY=<app key>
TIKTOK_SHOP_APP_SECRET=<app secret>
TIKTOK_SHOP_SHOP_ID=<shop id>
TIKTOK_SHOP_ACCESS_TOKEN=<optional; needed for order APIs in live>
```

### Sandbox setup
- TikTok Shop Partner Center → sandbox app (`open-api-sandbox.tiktokglobalshop.com`).
- Orders polled from `POST /api/order/search` with `order_status=AWAITING_SHIPMENT`;
  POST bodies are part of the signed string (HMAC-SHA256 over
  `app_secret + path + sorted params + body + app_secret`).

### Status map (poll → local)
| TikTok status | Local |
|---|---|
| `CANCELLED` | `cancelled` |
| `SHIPPED` / `FULFILLED` | `fulfilled` |

Fulfillment: `push_fulfillment` → `/api/fulfillment/ship` (needs `order_id`).

## Amazon SP-API

### Env vars
```
AMAZON_LWA_CLIENT_ID=<LWA client id>
AMAZON_LWA_CLIENT_SECRET=<LWA client secret>
AMAZON_SP_API_ROLE_ARN=arn:aws:iam::<acct>:role/<sp-api-role>
AMAZON_SELLER_ID=<seller id>
```

### Sandbox setup
- SP-API sandbox endpoint (`sandbox.sellingpartnerapi-na.amazon.com`) — LWA
  token (scope `sellingpartnerapi`) + STS AssumeRole with the LWA token as
  WebIdentityToken; requests are SigV4-signed with the role credentials.
- Orders polled from `/orders/v0/orders` (status `Unshipped`), **MFN only** —
  FBA orders are filtered out. Throttle: 429s back off using the
  `x-amzn-RateLimit-Limit` header; 401s force a token refresh once.
- **PII rule:** Amazon payloads contain buyer names/emails/addresses. The
  adapter logs order ids only and stores only ids in order metadata. Never add
  PII logging when extending this adapter.

### Status map (poll → local)
| Amazon status | Local |
|---|---|
| `Shipped` | `fulfilled` |
| `CancelPending` / `Canceled` | `cancelled` |
| `Pending` | `pending` |

Fulfillment: `push_fulfillment` → `POST /orders/v0/orders/{id}/shipment`.

---

## Default fee rates (config override wins)

| Platform | Default fee |
|---|---|
| Shopee | 0.07 (7%) |
| Lazada | 0.06 (6%) |
| TikTok Shop | 0.08 (8%) |
| Amazon | 0.15 (15%) |

Fee-aware margin: the SUPPLIER_PURCHASE gate evaluates
`(price − cost − fee) / price` with the per-channel rate — re-verify the fee
rate when promoting a channel to live.

## Sandbox → live promotion checklist

1. [ ] Sandbox app credentials replaced with the **live** seller-central app
   (separate key/secret — never reuse sandbox keys live)
2. [ ] `ChannelConnection.config["mode"] = "live"` for the platform
3. [ ] `fee_rate` verified against the current seller contract (or default accepted)
4. [ ] FX rates present (`ChannelConnection(channel="fx")`) or ABSOLUTE caps
       apply to THB orders only (PERCENT-only for foreign currencies)
5. [ ] `marketplace-poll` beat job observed for ≥ 2 clean cycles (imports +
       reconciles, no `error:` in results)
6. [ ] A small live test order imported, fulfilled, and reconciled end-to-end
7. [ ] Incident LOW noise checked: unmappable orders are expected until product
       mapping (inventory sync) is wired — see `channel-onboarding.md` product
       mapping section

---

## Post-Phase-3 operations

### Listing sync (products → channels)
- The `inventory-sync` beat job pushes local PUBLISHED products to every
  connected marketplace channel (`sync_listings`); adapters store the returned
  channel-side item id on `ChannelInventory.listing_id` so re-pushes update.
- Amazon only patches products whose `ChannelInventory.listing_id` holds the
  seller SKU — create the SKU-mapped inventory rows first.
- Per-channel price multipliers: `ChannelConnection.config["price_multiplier"]`
  (e.g. `1.1` on Amazon to absorb its 15% fee); default `1.0`.

### Admin poll / backfill
- `POST /api/channels/{channel}/poll?since=<ISO>` (admin key) polls one channel
  immediately — `since` backfills missed windows (same poll-first path as the
  beat job). Channel values: `shopee`, `lazada`, `tiktok_shop`, `amazon`.

### Payout reconciliation (settlements → ledger)
- `finance/payout_recon.py` books append-only FEE + PAYOUT ledger entries per
  settlement ref (idempotent). The `payout-recon` beat job (hourly) runs it via
  a `PayoutProvider` seam — wire a provider subclass reading platform
  settlement reports; without one the job reports `no_provider_configured`.
- Returns vs money: marketplace refunds are booked locally (Refund + negative
  REFUND ledger entry) when reconcile observes `RETURNED`/`REFUNDED`; the
  marketplace executes the actual money move.

### Competitor repricing
- `pricing/repricing.py` reacts only when our price is > 5% above the
  competitor, retargets to 2% under, deltas clamped ±20%, and applies through
  the shared policy-gated price path (24h lock + PRICE_CHANGE caps + audit).
  The hourly `repricing` beat job needs a `CompetitorPriceProvider` subclass
  (scraping/API) — without one it reports `no_provider_configured`.

### Channel health
- The hourly `channel-health` beat job raises an IncidentEvent LOW (once) when
  an enabled channel's `last_sync_at` is older than 12h (override per channel:
  `config["health_stale_hours"]`).

### Delivery SLA
- The daily `delivery-sla` beat job flags PAID orders older than 7 days with no
  delivered event (IncidentEvent MEDIUM, once per order).

### Multi-currency treasury + customer identity
- `GET /api/dashboard/treasury` — net ledger position per currency with THB
  equivalents from stored fx rates (missing rates reported, never guessed).
- `GET /api/dashboard/customer/{email}` — cross-platform purchase profile.
- `GET /api/dashboard/channels` — per-channel P&L (revenue, est fees via
  fee_rate, est COGS, est margin).

### Sandbox verification (BEFORE live — the honest gap)
- Tests are mocked; the real payload contract must be proven against each
  platform's sandbox. When sandbox credentials exist:
  `MARKETPLACE_MODE=sandbox python scripts/sandbox_smoke.py` — polls every
  connected sandbox channel with REAL calls, prints first-order previews.
  The script refuses to run unless `MARKETPLACE_MODE=sandbox` and skips any
  channel whose config mode is not `sandbox`.

### Operations toolkit (post-Phase-3 additions)
- **Rate budgets**: `core/rate_budget.py` TokenBucket per platform; pass into
  a signed client (`ShopeeClient(..., rate_budget=get_budget("shopee", 5.0))`)
  to cap request rate before the 429 backoff ever triggers.
- **Tracking ingestion**: `channels/tracking_ingest.py ingest_tracking(db,
  supplier_order_id, tracking, carrier)` — records carrier tracking on the
  SupplierOrder with audit trail (data path; wire the carrier/webhook source).
- **Per-channel agent**: `ChannelOpsAgent.run_cycle(db, channel)` — one
  channel's poll/import/reconcile cycle, autonomy-gated (OFF/SHADOW never
  call external APIs) and per-channel locked.
- **Policy what-if**: `core/policy_sim.simulate_policy_change(db, action,
  candidate_rules, days)` — replay candidate rules against recent orders
  PURELY IN MEMORY (no writes). Supported: `supplier_purchase`; others
  return `supported=False` until a historical context exists.
