# Autonomous Ecommerce Phase 3 Implementation Plan (2026-08-16)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 3 — Southeast-Asian marketplace connectors (Shopee, Lazada, TikTok Shop), Amazon SP-API connector, marketplace inventory/price sync, and a policy-gated affiliate/KOL program — all on top of the Phase 1/2 autonomy machinery (policy engine, staged rollout, locks, HMAC webhooks, idempotent import, shared price-write path).

**Architecture:** Extend the Phase 2 `channels/` layer with three marketplace adapters + one Amazon adapter, all implementing the existing `ChannelAdapter` ABC. Marketplace auth is **signed-request** (Shopee/Lazada HMAC-over-params, TikTok app auth) and Amazon uses **LWA tokens + role ARN** — a new `channels/platform_auth.py` holds the signing helpers. Order import/fulfillment/reconcile reuse the Phase 2 idempotent patterns; inventory sync adds per-channel stock buffers; price sync reuses the Phase 2 shared price-write path with **per-platform currency caps**. Affiliate program adds an `AFFILIATE` policy action (commission caps) + attribution tracking on top of existing AttributionEvent/RevenueExperiment models.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2 async, Celery + Redis, httpx, pytest (asyncio). Phase 1/2 test infra reused unchanged.

---

## ⚠️ Pre-Implementation Risk Audit (Phase 3)

| # | Finding | Severity | Where fixed |
|---|---|---|---|
| 1 | Marketplace **webhooks are not reliably HMAC-signed** (Shopee callback signature formats vary, some platforms have none). Trusting a webhook = forged orders/free product. Policy: **polling is the source of truth** for order import on all marketplaces; webhooks (where supported) only trigger a poll, never directly import. | Critical | Task 2-5 (all adapters) |
| 2 | Signed-request auth is per-platform and easy to get wrong (Shopee: `SHA256(key + sorted params + url)`; Lazada: `sign = HMAC-SHA256(app_secret, sorted params)`. A wrong signature silently 401s — but a *missing* signature check on inbound callbacks is the dangerous direction. All outbound calls go through `PlatformSignedClient` with the exact per-platform spec; tests use sandbox fixtures. | High | Task 1, Tasks 2-5 |
| 3 | Multi-currency caps: Phase 1/2 absolute caps are seeded in **THB cents** but Shopee/Lazada orders arrive in VND/MYR/SGD. Applying a THB cap to a MYR amount is wrong. Fix: `context["currency"]` already flows to `PolicyEngine.check` — new `currency_cap_map` in policy evaluation converts ABSOLUTE caps via stored FX rates (`ChannelConnection.config["fx_rates"]`, updated by a daily FX job). Until FX rates exist, ABSOLUTE caps apply only to orders in THB; others use PERCENT caps only. | High | Task 1 (policy), Task 6 |
| 4 | Platform fees (Shopee ~5-8%, Lazada ~4-10%, Amazon ~15%) shrink real margin. The Phase 2 supplier margin gate (≥20%) must be evaluated **after platform fee**: `margin_after_fee = (price - cost - fee) / price`. Fee rate stored per channel; gate stays on the same SUPPLIER_PURCHASE rules. | High | Task 6 |
| 5 | Inventory overselling: same physical product listed on N channels, each with its own stock count → oversell without reconciliation. Fix: per-channel `stock_buffer` (safety stock) + inventory reconcile job (local = sum(channel stock) − buffer) with a lock; never negative. | High | Task 6 |
| 6 | Affiliate fraud (self-referral, fake clicks, commission stacking). Fix: `AFFILIATE` policy action with PERCENT+ABSOLUTE caps, payout requires a confirmed sale (`AttributionEvent` with `conversion`), manual review flag above threshold (IncidentEvent MEDIUM), 30-day attribution window. | High | Task 7 |
| 7 | Amazon SP-API is the strictest: LWA token refresh, role ARN assume, throttling per operation, and **data protection policies** (no PII in logs). Client must cache tokens, back off 429s (with `x-amzn-RateLimit-*`), and never log order PII. | Medium | Task 5 |
| 8 | Platform sandbox vs live split: tests and first deployment MUST run against sandbox (Shopee open platform sandbox, Lazada pre-production, Amazon SP-API sandbox). A live credential in a test env = real orders/charges. `ChannelConnection.config["mode"]="sandbox|live"` gates which endpoints the adapter hits; fail-closed in production when mode is unset. | Critical | Tasks 2-5 |
| 9 | Marketplace order cancellation/return windows differ (Shopee 15-day return, Lazada 7-day). Reconcile direction rules from Phase 2 need per-platform status maps (their "cancelled"/"returned"/"refunded" → our OrderStatus) — a wrong map either double-ships or never refunds. Keep map per adapter, tested. | Medium | Tasks 2-5 |

---

## Global Constraints

- All Phase 1/2 Global Constraints apply (policy fail-closed, dual caps, AutonomyMode staging, locks, verification codes, no secrets in logs, existing tests green)
- **Polling is the source of truth** for marketplace order import — webhooks only trigger polls, never import directly
- Every adapter implements `ChannelAdapter` and is testable with a **sandbox-mode** fixture; `mode` lives in `ChannelConnection.config`, fail-closed in production
- All outbound marketplace calls go through `PlatformSignedClient` (or LWA client for Amazon) — no raw httpx outside those
- New money actions seed dual PERCENT+ABSOLUTE rules; `context["currency"]` must be passed; ABSOLUTE caps convert via `fx_rates` when the order currency ≠ THB (PERCENT-only fallback until rates exist)
- Supplier margin gates (Task 6) evaluate `margin_after_fee` using per-channel fee rates
- Every new beat job lock-wrapped (TTL ≥ 600); SHADOW never calls external APIs
- Keep existing suites green (Phase 1+2 regression floor)

**Gate legend:** each task ends with a Gate line.

---

## Architecture

```
                     ┌──────────────────────────────────────────────┐
                     │            REVENUE OS API (FastAPI)           │
                     │  channels router (extended: per-platform      │
                     │  webhook-trigger + admin status/sync)         │
                     └──────────────┬───────────────────────────────┘
                                    │
        ┌───────────────────────────▼───────────────────────────────┐
        │            CHANNEL LAYER (Phase 2, extended)              │
        │  ChannelAdapter ABC (exists)                              │
        │  ├── ShopifyAdapter (exists)                              │
        │  ├── ShopeeAdapter  ├── LazadaAdapter  ├── TikTokAdapter  │
        │  ├── AmazonAdapter                                        │
        │  └── PlatformSignedClient (NEW auth helpers)              │
        └───────┬──────────────────────────┬────────────────────────┘
                │                          │
   ┌────────────▼─────────────┐  ┌─────────▼──────────────────────────┐
   │  MARKETPLACE SYNC (NEW)  │  │  AFFILIATE (NEW)                   │
   │  inventory reconcile      │  │  AFFILIATE policy action          │
   │  (per-channel buffer)     │  │  attribution tracking (existing   │
   │  price sync (shared path, │  │  AttributionEvent models)         │
   │  FX-aware caps)           │  │  payout review flag               │
   └────────────┬─────────────┘  └─────────┬──────────────────────────┘
                │                          │
   ┌────────────▼──────────────────────────▼──────────────────────────┐
   │         POLICY ENGINE (exists — add AFFILIATE rules + FX)        │
   │  PRICE_CHANGE/DISCOUNT/REFUND/SUPPLIER_PURCHASE/AD_BUDGET/AFFILIATE│
   └──────────────────────────────────────────────────────────────────┘
```

---

## File Map

### Backend — package (`graxia/packages/revenue_os/`)

| File | Action | Purpose |
|---|---|---|
| `enums.py` | MODIFY | Add `ChannelType.SHOPEE/LAZADA/TIKTOK_SHOP/AMAZON`; `AffiliateStatus` |
| `models.py` | MODIFY | Add `Affiliate` (code, commission_pct, status), `AffiliatePayout` (amount, status, review flag), `ChannelInventory` (channel, product, stock, buffer); extend `ActionType` with AFFILIATE="affiliate" |
| `constants.py` | MODIFY | FX refresh cadence, stock buffer default, attribution window days, affiliate payout review threshold |
| `channels/platform_auth.py` | **NEW** | `PlatformSignedClient` (Shopee/Lazada/TikTok signing helpers), `AmazonTokenCache` (LWA) — the ONLY place auth/signing lives |
| `channels/shopee.py` | **NEW** | `ShopeeAdapter(ChannelAdapter)`: poll orders (source of truth), sandbox/live switch, status map, fulfillment push |
| `channels/lazada.py` | **NEW** | `LazadaAdapter(ChannelAdapter)` same pattern |
| `channels/tiktok_shop.py` | **NEW** | `TikTokShopAdapter(ChannelAdapter)` same pattern |
| `channels/amazon.py` | **NEW** | `AmazonAdapter(ChannelAdapter)`: LWA client, orders, MFN fulfillment, sandbox endpoints |
| `channels/marketplace_sync.py` | **NEW** | `inventory_reconcile(db)` (buffers, lock), `price_sync(db)` (shared write path, FX-aware), `fx_refresh(db)` (daily rates into channel config) |
| `affiliate/service.py` | **NEW** | `create_affiliate`, `record_attribution`, `review_payouts` (policy-gated, threshold flag) |
| `core/policy_engine.py` | MODIFY | FX-aware ABSOLUTE cap conversion; seed `AFFILIATE` dual caps |
| `celery/tasks/marketplace_poll.py` | **NEW** | Poll all marketplace adapters (lock) — or one task per platform |
| `celery/tasks/inventory_sync.py` | **NEW** | inventory + price sync (locked) |
| `celery/tasks/fx_refresh.py` | **NEW** | daily FX rates (locked) |
| `celery/tasks/affiliate_review.py` | **NEW** | daily payout review (locked) |
| `tests/test_shopee_adapter.py` etc. | **NEW** | per-platform suites (sandbox fixtures, signed-request tests) |

### Backend — API (`graxia/services/revenue_os_api/routers/`)

| File | Action |
|---|---|
| `channels.py` | MODIFY — per-platform webhook-trigger endpoints (poll-trigger only), admin status/sync for marketplaces |
| `affiliate.py` | **NEW** — `POST /api/affiliate/create` (admin), `GET /api/affiliate/overview` (admin) |

### Docs

| File | Action |
|---|---|
| `docs/runbooks/marketplace-onboarding.md` | **NEW** — sandbox vs live, per-platform credential setup, fee rates, status maps |
| `docs/runbooks/affiliate-program.md` | **NEW** — commission caps, payout review, fraud signals |
| spec `2026-08-16-autonomous-ecommerce-design.md` | MODIFY — Phase 3 status |

---

### Task 1: Platform auth helpers + model/enum extensions + FX-aware caps

**Files:**
- Modify: `enums.py`, `models.py`, `constants.py`, `core/policy_engine.py`
- Create: `channels/platform_auth.py`
- Create: `tests/test_platform_auth.py`

**Interfaces:**
- Produces:
  - `ChannelType` += SHOPEE="shopee", LAZADA="lazada", TIKTOK_SHOP="tiktok_shop", AMAZON="amazon"
  - `class AffiliateStatus(StrEnum)`: ACTIVE, PAUSED, BANNED
  - `class Affiliate(Base)` — table `revenue_os_affiliates`: `id UUID PK`, `code str(50) unique`, `email str(320)`, `commission_percent float`, `status AffiliateStatus default ACTIVE`, `created_at/updated_at`
  - `class AffiliatePayout(Base)` — table `revenue_os_affiliate_payouts`: `id UUID PK`, `affiliate_id UUID FK`, `order_id UUID FK`, `amount_cents int`, `status str(30) default "pending"` (pending|approved|paid|rejected), `needs_review bool default False`, timestamps
  - `class ChannelInventory(Base)` — table `revenue_os_channel_inventory`: `channel ChannelType`, `product_id UUID FK`, `channel_stock int default 0`, `stock_buffer int default 0`, PK(channel, product_id)
  - `ActionType` += `AFFILIATE = "affiliate"`
  - `channels/platform_auth.py`:
    - `class PlatformSignedClient` — `async get_json(path, params)`, `async post_json(path, json)`; subclasses implement `_sign(method, path, params) -> dict` (adds `sign`/`signature` per platform). Shopee: `SHA256(secret + sorted_url_query)`; Lazada: `HMAC-SHA256(app_secret, sorted_params_str)`; TikTok: app_key+secret signing. Rate-limit aware (429 backoff like ShopifyClient). Sandbox/live base-URL switch via `mode`.
    - `class AmazonTokenCache` — LWA client-credentials token (cached, refresh on expiry), `assume_role` for SP-API.
  - `PolicyEngine._evaluate` ABSOLUTE cap: if `rule.value_type == ABSOLUTE` and `context.get("currency")` != "THB" and `context.get("fx_rate")` present → compare `value_cents / fx_rate` against cap (converted); if currency != THB and no fx_rate → **skip ABSOLUTE rule** (PERCENT-only), logged via reason string. THB always uses raw cents.
  - `seed_default_rules` += `(AFFILIATE, MAX, PERCENT, 20.0, "max affiliate commission %")`, `(AFFILIATE, MAX, ABSOLUTE, 20_000_00, "max affiliate payout, THB cents")`
  - constants: `FX_REFRESH_DAYS=1`, `DEFAULT_STOCK_BUFFER=3`, `ATTRIBUTION_WINDOW_DAYS=30`, `AFFILIATE_REVIEW_THRESHOLD_CENTS=50_000_00`

- [ ] **Step 1: Write failing tests** — `tests/test_platform_auth.py` (Shopee signature known-vector, Lazada signature known-vector, FX-aware cap: MYR order with fx_rate converts; MYR without fx_rate skips ABSOLUTE rule but PERCENT still applies; AFFILIATE rules seed)
- [ ] **Step 2: Run to confirm fail**
- [ ] **Step 3: Implement** per Interfaces (copy the ShopifyClient 429 pattern; keep signing in ONE place)
- [ ] **Step 4: Run to pass** — expected ≥ 5 PASSED
- [ ] **Step 5: Commit** — `feat(revenue-os): platform auth helpers, FX-aware caps, affiliate/inventory models`

**Gate (Task 1):** signature tests pass against known vectors; FX conversion test proves MYR-without-rate → PERCENT-only.

---

### Task 2: Shopee adapter (poll-first, sandbox gate)

**Files:**
- Create: `channels/shopee.py`, `tests/test_shopee_adapter.py`

**Interfaces:**
- Consumes: `PlatformSignedClient`, `import_shopify_orders`-style idempotent import (extract a shared `import_channel_orders(db, platform, orders)` helper into `channels/base.py` — refactor Task 2 of P2 to use it, keep behavior), `ChannelAdapter`
- Produces: `class ShopeeAdapter(ChannelAdapter)`:
  - `name=SHOPEE`; reads `SHOPEE_PARTNER_ID`, `SHOPEE_PARTNER_KEY`, `SHOPEE_SHOP_ID` from env; `mode` from `ChannelConnection.config` (sandbox default in dev, **fail-closed in production if unset**)
  - `import_orders(since)` → poll `/orders.get_order_list` (status=READY_TO_SHIP) — **source of truth; webhook only triggers this**
  - `sync_products` → `/product.add_item`/`update_item` (sandbox ids)
  - `push_fulfillment(order, tracking)` → `/logistics.ship_order`
  - `reconcile` → status map: `CANCELLED/IN_CANCEL → CANCELLED`, `COMPLETED → FULFILLED`, `RETURNED → REFUNDED` (per-platform map, tested)
  - shared `import_channel_orders` helper: idempotent (platform+platform_order_id unique), PAID→fulfill, unmappable→IncidentEvent LOW
- [ ] **Step 1: Write failing tests** — sandbox fixture: order poll parse, status map rows, idempotent import via shared helper, webhook-trigger never imports directly (assert it calls poll)
- [ ] **Step 2: Run to confirm fail**
- [ ] **Step 3: Implement** per Interfaces; refactor `channels/base.py` with `import_channel_orders`; update P2 shopify import to use it (regression: existing shopify tests must stay green)
- [ ] **Step 4: Run to pass** — ≥ 4 PASSED + shopify suite green
- [ ] **Step 5: Commit** — `feat(revenue-os): shopee adapter - poll-first import, sandbox gate, status map`

**Gate (Task 2):** no direct webhook import path exists; shopify suite still green after shared-helper refactor.

---

### Task 3: Lazada adapter

**Files:**
- Create: `channels/lazada.py`, `tests/test_lazada_adapter.py`

**Interfaces:**
- Same contract as ShopeeAdapter (poll-first, sandbox gate, status map: `shipped → FULFILLED`, `canceled → CANCELLED`, `returned → REFUNDED`)
- Reads `LAZADA_APP_KEY`, `LAZADA_APP_SECRET`, `LAZADA_SELLER_ID` from env; Lazada signature via `PlatformSignedClient._sign`
- `import_orders(since)` → `/orders/get` (status filter), `push_fulfillment` → `/order/pack` + `/order/ship`
- [ ] **Step 1: Write failing tests** (sandbox fixtures; signature via shared client; status map; idempotent import)
- [ ] **Step 2: Run to confirm fail**
- [ ] **Step 3: Implement** per Interfaces (mirror ShopeeAdapter; DO NOT copy-paste signing logic — use PlatformSignedClient)
- [ ] **Step 4: Run to pass** — ≥ 4 PASSED
- [ ] **Step 5: Commit** — `feat(revenue-os): lazada adapter - poll-first import, sandbox gate, status map`

**Gate (Task 3):** adapter uses only shared auth helpers; suite green.

---

### Task 4: TikTok Shop adapter

**Files:**
- Create: `channels/tiktok_shop.py`, `tests/test_tiktok_shop_adapter.py`

**Interfaces:**
- `TikTokShopAdapter(ChannelAdapter)`: reads `TIKTOK_SHOP_APP_KEY`, `TIKTOK_SHOP_APP_SECRET`, `TIKTOK_SHOP_SHOP_ID`; auth = app_key+secret signed requests (PlatformSignedClient); poll orders `/order/search`; push fulfillment `/fulfillment/ship`; status map (`CANCELLED`, `SHIPPED`, `FULFILLED`)
- Sandbox endpoint gate identical to Tasks 2-3
- [ ] **Step 1: Write failing tests** (poll parse, status map, idempotent import, webhook-trigger → poll only)
- [ ] **Step 2-5: implement/pass/commit** — `feat(revenue-os): tiktok shop adapter - poll-first import, sandbox gate`

**Gate (Task 4):** suite green; no direct webhook import.

---

### Task 5: Amazon SP-API adapter

**Files:**
- Create: `channels/amazon.py`, `tests/test_amazon_adapter.py`

**Interfaces:**
- `AmazonAdapter(ChannelAdapter)`: reads `AMAZON_LWA_CLIENT_ID`, `AMAZON_LWA_CLIENT_SECRET`, `AMAZON_SP_API_ROLE_ARN`, `AMAZON_SELLER_ID`; token via `AmazonTokenCache` (LWA client-credentials + role assume, cached, refresh on 401)
- Sandbox: SP-API sandbox endpoints (`/orders/v0/orders` with `x-amzn-marketplace-id`); **throttle-aware**: honor `x-amzn-RateLimit-*` headers on 429
- `import_orders(since)` → `GET /orders/v0/orders` (MFN only filter); `push_fulfillment` → `POST /orders/v0/orders/{id}/shipment` (tracking); `reconcile` → status map (`CancelPending/Canceled → CANCELLED`, `Shipped → FULFILLED`, `Pending → PENDING`)
- **PII rule:** never log customer names/emails/addresses from Amazon payloads (log order id only)
- [ ] **Step 1: Write failing tests** (token cache refresh, throttle backoff, order parse with PII-redaction assertion, status map, idempotent import)
- [ ] **Step 2-5: implement/pass/commit** — `feat(revenue-os): amazon SP-API adapter - LWA tokens, throttle-aware, PII-safe`

**Gate (Task 5):** PII-redaction test asserts no name/email in logs; throttle test passes.

---

### Task 6: Marketplace inventory + price sync (buffers, fees, FX)

**Files:**
- Create: `channels/marketplace_sync.py`, `celery/tasks/inventory_sync.py`, `celery/tasks/fx_refresh.py`, `tests/test_marketplace_sync.py`

**Interfaces:**
- Produces:
  - `inventory_reconcile(db) -> dict`: for each ChannelInventory row: local_available = channel_stock − stock_buffer (never negative); pushes `available` to each channel via adapter.sync_products (or dedicated stock endpoint); logs changes
  - `price_sync(db) -> dict`: for each channel product: use shared `DynamicPricingEngine.apply`-style path with FX-aware caps (Task 1); push new price to channel; 24h lock applies
  - `margin_after_fee(db, order, product) -> float`: `(amount − cost − fee) / amount`, fee rate from `ChannelConnection.config["fee_rate"]` per channel (defaults: shopee 0.07, lazada 0.06, tiktok 0.08, amazon 0.15) — used by the SUPPLIER_PURCHASE gate in the supplier adapter (P2 Task 3) via a shared helper
  - `fx_refresh(db) -> int`: fetch rates (configurable `FX_SOURCE_URL`, e.g. open.er-api.com free tier), store `{"THB": {"MYR": 0.12, ...}}` into `ChannelConnection.config["fx_rates"]` (global row channel="fx")
  - celery tasks `inventory_sync()` (lock, 15 min), `fx_refresh()` (lock, daily)
- [ ] **Step 1: Write failing tests** (buffer math never negative, fee-aware margin gate, FX refresh stores rates, price sync respects 24h lock)
- [ ] **Step 2-5: implement/pass/commit** — `feat(revenue-os): marketplace inventory/price sync - buffers, fee-aware margins, FX rates`

**Gate (Task 6):** buffer test proves no negative stock; margin gate uses fee-aware math.

---

### Task 7: Affiliate/KOL program (policy-gated)

**Files:**
- Create: `affiliate/service.py`, `celery/tasks/affiliate_review.py`, `services/revenue_os_api/routers/affiliate.py`, `tests/test_affiliate.py`

**Interfaces:**
- Produces:
  - `create_affiliate(db, email, commission_percent) -> Affiliate` — rejects commission > AFFILIATE PERCENT cap (policy check with `ActionType.AFFILIATE`, value=commission %, value_cents=0)
  - `record_attribution(db, affiliate_code, order_id) -> bool` — validates affiliate ACTIVE + order within `ATTRIBUTION_WINDOW_DAYS` of first touch (AttributionEvent reuse); creates `AffiliatePayout(amount = order.amount_cents × commission%)` status pending; if amount ≥ `AFFILIATE_REVIEW_THRESHOLD_CENTS` → `needs_review=True` + IncidentEvent MEDIUM
  - `review_payouts(db) -> dict` — daily: pays approved payouts via `refund_executor`-style external call? **No** — payouts are manual/processed by operator for Phase 3 (status pending→approved only after human review); task flags `needs_review` rows + Telegram summary
  - router: `POST /api/affiliate/create` (admin), `GET /api/affiliate/overview` (admin)
- [ ] **Step 1: Write failing tests** (create rejects over-cap commission; attribution creates payout with correct amount; threshold flags review + incident; review task skips below threshold)
- [ ] **Step 2-5: implement/pass/commit** — `feat(revenue-os): affiliate program - policy-gated commissions, attribution tracking, payout review`

**Gate (Task 7):** over-cap creation denied; threshold row flagged for review.

---

### Task 8: Celery beat wiring + full regression

**Files:**
- Modify: `celery/celery_app.py`, `celery/tasks/__init__.py`

- [ ] **Step 1: Add beat entries** (copy existing style):

```python
    "marketplace-poll": {
        "task": "graxia.packages.revenue_os.celery.tasks.marketplace_poll",
        "schedule": 600.0,  # every 10 min
        "options": {"queue": "default"},
    },
    "inventory-sync": {
        "task": "graxia.packages.revenue_os.celery.tasks.inventory_sync",
        "schedule": 900.0,  # every 15 min
        "options": {"queue": "default"},
    },
    "fx-refresh": {
        "task": "graxia.packages.revenue_os.celery.tasks.fx_refresh",
        "schedule": 86400.0,  # daily
        "options": {"queue": "reporting"},
    },
    "affiliate-review": {
        "task": "graxia.packages.revenue_os.celery.tasks.affiliate_review",
        "schedule": 86400.0,  # daily
        "options": {"queue": "reporting"},
    },
```

- [ ] **Step 2: Task registry** — add `marketplace_poll`, `inventory_sync`, `fx_refresh`, `affiliate_review` to `tasks/__init__.py` (mind the module/function shadowing from P2 — use unique function names if needed)
- [ ] **Step 3: Import smoke + full suite** — `python -c "from graxia.packages.revenue_os.celery.tasks import ...; print('ok')"`; `pytest .../tests/ -q` → Phase 1+2 baseline (14 pre-existing) + new tests green, ZERO errors
- [ ] **Step 4: Commit** — `feat(revenue-os): celery beat - marketplace poll, inventory sync, fx refresh, affiliate review`

**Gate (Task 8):** import smoke ok; suite matches baseline + new tests.

---

### Task 9: Runbooks + spec update

**Files:**
- Create: `docs/runbooks/marketplace-onboarding.md` — per-platform: seller central signup, sandbox app creation (Shopee open platform sandbox, Lazada pre-production, TikTok sandbox, Amazon SP-API sandbox), env vars, fee rate defaults, status maps, sandbox→live promotion checklist (incl. `ChannelConnection.config["mode"]="live"` + fee re-verify)
- Create: `docs/runbooks/affiliate-program.md` — commission caps (20%/20k THB), attribution window 30 days, payout review threshold 50k THB, fraud signals (self-referral, stacking), kill switch reference
- Modify: spec `2026-08-16-autonomous-ecommerce-design.md` — Phase 3 status section

- [ ] **Step 1: Write runbooks + spec section** (patterns from Phase 1/2 runbooks; no literal keys)
- [ ] **Step 2: Commit** — `docs: phase 3 runbooks (marketplaces, affiliate) + spec status`

**Gate (Task 9):** runbooks reference only env-var names; spec updated.

---

## Self-Review Notes

- **Spec coverage:** auth/FX/models (T1), Shopee (T2), Lazada (T3), TikTok (T4), Amazon (T5), inventory/price/fees/FX (T6), affiliate (T7), beat+regression (T8), docs (T9). KOL *discovery* tooling deferred (manual onboarding of affiliates for now).
- **Reuse over rebuild:** all adapters implement the existing `ChannelAdapter` ABC; order import shares ONE idempotent helper; price changes go through the shared P2 write path; policy dual caps + FX conversion are the only engine change; P2 `_ads_optimization`/`_price_optimization` untouched.
- **Consistency:** `PlatformSignedClient` is the only place auth lives (no per-adapter signing copies); `import_channel_orders` is the only import path (webhook-trigger → poll only); ABSOLUTE caps always check `context["currency"]`; every beat task locked TTL ≥ 600.
- **Verification risks:** per-platform signature known-vectors must come from official docs at implementation time (vector tests written against the doc examples); Amazon SP-API throttling headers format varies by region; `MetricDaily` schema for FX/impact reuse; `ChannelConnection` config keys shared with the P2 `shopify_sync` cursor — do not collide.
- **Type consistency:** `ChannelAdapter.name` returns the new `ChannelType` values; `import_channel_orders(db, platform, orders)` shared signature; `AffiliatePayout.amount_cents` in cents; FX rates dict shape `{"THB": {"MYR": 0.12, ...}}`.
