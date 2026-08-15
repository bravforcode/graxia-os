# Autonomous Ecommerce Phase 2 Implementation Plan (2026-08-16)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 2 — multi-channel commerce on top of Phase 1 autonomy: Shopify connector, paid-ads management (Meta first, Google/TikTok interfaces), POD/dropship fulfillment, rule-based dynamic pricing, and a backtest harness — all gated by the same policy engine + staged autonomy rollout.

**Architecture:** Extend `graxia/packages/revenue_os` with a `channels/` package (ChannelAdapter ABC + Shopify adapter + supplier adapter), an `ads/` package (AdPlatformClient ABC + Meta client + policy-gated budget agent job), a `pricing/` module (rule-based dynamic pricing), and a `simulation/` backtest harness. External order/fulfillment events reuse the Phase 1 Order model (`platform`, `platform_order_id` unique = idempotency) and the fulfillment/refund pipeline. Every new money-moving action (AD_BUDGET, SUPPLIER_PURCHASE, PRICE_CHANGE realtime) gets dual PERCENT+ABSOLUTE policy rules; all new beat jobs are lock-wrapped; SHADOW mode logs without executing (Phase 1 machinery reused as-is).

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2 async, Celery + Redis, httpx (external APIs), pytest (asyncio). Phase 1 test infra (conftest clean-slate, pytest-asyncio 1.x, test DB `graxia-test-db` port 5433) is reused unchanged.

---

## ⚠️ Pre-Implementation Risk Audit (Phase 2)

| # | Finding | Severity | Where fixed |
|---|---|---|---|
| 1 | Shopify webhooks arrive unverified unless HMAC-checked — a forged `orders/paid` webhook would import a fake paid order into the fulfillment pipeline (free product). Must verify `X-Shopify-Hmac-Sha256` before parsing. | Critical | Task 2 |
| 2 | Shopify API rate limits (2 req/s core, 4 req/s bulk) — a naive product-sync loop gets 429s and poisons retries. All client calls need limit-aware backoff + dedicated queue. | High | Task 2 |
| 3 | Ads = **real money outflow**. An agent misreading ROAS could burn budget. `AD_BUDGET` must be dual-capped (percent of daily budget + absolute cents), LIMITED multiplier applies, and the ads job must never run above the mode the rollout gate allows. | Critical | Task 4, Task 5, Task 12-reuse |
| 4 | POD supplier order submission is a one-way external side effect — retry after a timeout could double-order physical goods. Supplier calls need a per-order idempotency key (supplier API `idempotency_key` where supported) + persisted `supplier_order_ref` before/after state machine. | Critical | Task 3 |
| 5 | Dynamic pricing racing the Phase 1 price job — two jobs editing the same `price_cents` produce lost updates. Must share one price-write path with a per-product lock/check-and-set. | High | Task 6 |
| 6 | Reconciliation drift: Shopify/Marketplace orders cancelled/refunded externally never reflect locally without a periodic reconcile job that applies platform status changes (careful: don't overwrite local REFUNDED with platform PAID). | High | Task 2, Task 7 |
| 7 | Backtest results are seductive — a sim that ignores policy caps overstates agent performance. The harness MUST replay through the real `PolicyEngine.check` with the real ruleset. | Medium | Task 7 |
| 8 | Supplier webhooks (POD status) are untrusted third-party POSTs — verify configured shared secret per supplier; never trust payload fields for amounts. | High | Task 3 |
| 9 | Multi-channel money in one ledger: a Shopify order paid in USD flows through THB-absolute caps incorrectly (Phase 1 note). Phase 2 keeps caps currency-aware per order currency; document conversion policy (store rates in order metadata). | Medium | Global Constraints |
| 10 | Secrets: Shopify API token, Meta access token, supplier API keys — same rule as Phase 1: env/secrets-manager only, never logged/returned; each client reads its own env var with fail-closed production behavior. | Medium | Tasks 2-4 |

---

## Global Constraints

- All Phase 1 Global Constraints still apply (policy engine fail-closed, dual caps, AutonomyMode staging, locks on beat jobs, verification codes, no secrets in logs, existing tests green)
- New money-moving actions MUST seed BOTH a PERCENT and an ABSOLUTE (cents) `PolicyRule`, and callers MUST pass `context["value"]` + `context["value_cents"]` + `context["currency"]`
- Every new celery beat job MUST be lock-wrapped (`acquire_automation_lock`, TTL ≥ 600s) — copy the Phase 1 task wrapper pattern
- External webhook routers (Shopify, suppliers) MUST verify HMAC/shared-secret BEFORE deserialization, mirroring `require_stripe_hmac`
- All external HTTP uses `httpx.AsyncClient` with timeouts + retry-with-backoff; no bare `requests` in new code
- SHADOW mode: new agents compute + log proposals, never call external APIs (no Shopify writes, no Meta budget changes, no supplier orders in shadow)
- Keep existing tests green — Phase 1 suite is the regression floor

**Gate legend:** each task ends with a Gate line.

---

## Architecture

```
                    ┌──────────────────────────────────────────────┐
                    │            REVENUE OS API (FastAPI)           │
                    │  checkout/support/policy/autonomy + NEW:      │
                    │  channels (webhooks+status)  ads (status)     │
                    └──────────────┬───────────────────────────────┘
                                   │
        ┌──────────────────────────▼──────────────────────────────┐
        │                 CHANNEL LAYER (new)                     │
        │  ChannelAdapter ABC ── ShopifyAdapter ── SupplierAdapter │
        │  order import (idempotent)  product sync  fulfillment   │
        │  reconciliation job                                      │
        └───────┬───────────────────────────┬─────────────────────┘
                │                           │
   ┌────────────▼────────────┐   ┌──────────▼──────────────────────┐
   │       ADS (new)         │   │       PRICING (new)             │
   │  AdPlatformClient ABC   │   │  DynamicPricingEngine           │
   │  MetaAdsClient          │   │  (rule-based, policy-gated,     │
   │  agent job: budget per  │   │   per-product check-and-set)    │
   │  ROAS within AD_BUDGET  │   └──────────┬──────────────────────┘
   └───────────┬─────────────┘              │
               │                            │
   ┌───────────▼────────────────────────────▼──────────────────────┐
   │            POLICY ENGINE (Phase 1, extended rules)            │
   │  AD_BUDGET, SUPPLIER_PURCHASE, PRICE_CHANGE (realtime)        │
   └───────────────────────────────────────────────────────────────┘
        │
   ┌────▼──────────────────────────────────────────────────────────┐
   │        BACKTEST HARNESS (new) — replay history through       │
   │        the REAL PolicyEngine + agents; output report         │
   └───────────────────────────────────────────────────────────────┘
```

**Channel order lifecycle (Shopify example):** Shopify webhook (HMAC) → import order (platform=shopify, platform_order_id=webhook id — unique ⇒ idempotent) → status PAID → existing digital fulfillment OR physical branch (POD supplier order) → DeliveryEvent chain → WISMO answers from local state; reconcile job syncs external cancellations/refunds.

---

## File Map

### Backend — package (`graxia/packages/revenue_os/`)

| File | Action | Purpose |
|---|---|---|
| `enums.py` | MODIFY | Add `ChannelType` (shopify, pod_supplier), `SupplierStatus`, extend `ActionType` with AD_BUDGET, SUPPLIER_PURCHASE |
| `models.py` | MODIFY | Add `ChannelConnection` (platform creds refs), `SupplierOrder` (supplier ref, status, tracking, idempotency), `AdCampaignSync` (platform campaign mirror), `PriceChangeLock` (check-and-set) |
| `constants.py` | MODIFY | Rate limits, supplier idempotency TTL, ads sync window |
| `channels/base.py` | **NEW** | `ChannelAdapter` ABC: `import_orders`, `sync_products`, `push_fulfillment`, `reconcile`, `verify_webhook` |
| `channels/shopify.py` | **NEW** | Shopify REST/GraphQL client (limit-aware), webhook HMAC, product/order mapping, fulfillment push |
| `channels/supplier_pod.py` | **NEW** | Printful-style client: submit order (idempotency_key), poll/parse status webhook, tracking sync |
| `channels/reconciler.py` | **NEW** | Cross-platform reconciliation: status/refund sync with direction rules |
| `ads/base.py` | **NEW** | `AdPlatformClient` ABC: `list_campaigns`, `get_metrics`, `set_budget`, `set_status` |
| `ads/meta.py` | **NEW** | Meta Marketing API client (access token, rate-limit aware) |
| `pricing/dynamic.py` | **NEW** | Rule engine: time/stock/demand signals → proposed delta; writes via shared price path |
| `simulation/backtest.py` | **NEW** | Replay MetricDaily+orders through real PolicyEngine+agents; report |
| `agents/commerce_ops.py` | MODIFY | Add `_ads_optimization(db, shadow)`, `_supplier_poll(db, shadow)` jobs; share price-write path |
| `agents/pricing_agent.py` | **NEW** | Runs dynamic pricing cycle (or fold into commerce_ops job — see Task 6) |
| `celery/tasks/shopify_sync.py` | **NEW** | Product sync + order import + reconcile (locked) |
| `celery/tasks/supplier_poll.py` | **NEW** | POD status polling (locked) |
| `celery/tasks/ads_sync.py` | **NEW** | Ads metrics + budget agent (locked) |
| `celery/tasks/backtest_runner.py` | **NEW** | Nightly backtest on accumulated history |
| `tests/test_shopify_adapter.py` etc. | **NEW** | Per-component suites (mock httpx) |

### Backend — API (`graxia/services/revenue_os_api/routers/`)

| File | Action | Purpose |
|---|---|---|
| `channels.py` | **NEW** | `POST /api/channels/{platform}/webhook` (HMAC), `GET /api/channels` (status), `POST /api/channels/{platform}/sync` (admin) |
| `ads.py` | **NEW** | `GET /api/ads/overview` (admin), `POST /api/ads/refresh` |
| `router.py` | MODIFY | register new routers |

### Docs

| File | Action |
|---|---|
| `docs/runbooks/channel-onboarding.md` | **NEW** — Shopify app install, tokens, webhook subscription, supplier setup |
| `docs/runbooks/ads-budgets.md` | **NEW** — budget policy, ROAS rules, kill procedure |
| `docs/superpowers/specs/2026-08-16-autonomous-ecommerce-design.md` | MODIFY — Phase 2 status |

---

### Task 1: Channel framework + model extensions

**Files:**
- Modify: `graxia/packages/revenue_os/enums.py` (add `ChannelType`, `SupplierStatus`, extend `ActionType` with AD_BUDGET="ad_budget", SUPPLIER_PURCHASE="supplier_purchase")
- Modify: `graxia/packages/revenue_os/models.py` (add `ChannelConnection`, `SupplierOrder`, `AdCampaignSync`, `PriceChangeLock`)
- Modify: `graxia/packages/revenue_os/constants.py` (add `CHANNEL_ORDER_IMPORT_LIMIT=200`, `SUPPLIER_POLL_INTERVAL_MIN=15`, `ADS_METRICS_WINDOW_DAYS=7`)
- Create: `graxia/packages/revenue_os/channels/__init__.py`, `graxia/packages/revenue_os/channels/base.py`
- Create: `graxia/packages/revenue_os/tests/test_channel_framework.py`

**Interfaces:**
- Produces:
  - `class ChannelType(StrEnum)`: SHOPIFY="shopify", POD_SUPPLIER="pod_supplier"
  - `class SupplierStatus(StrEnum)`: SUBMITTED, IN_PRODUCTION, SHIPPED, DELIVERED, FAILED
  - `class ChannelConnection(Base)` — table `revenue_os_channel_connections`: `id UUID PK`, `channel ChannelType`, `name str`, `enabled bool default True`, `config JSONB` (never secrets — store secret refs), `created_at/updated_at`
  - `class SupplierOrder(Base)` — table `revenue_os_supplier_orders`: `id UUID PK`, `order_id UUID FK`, `supplier str`, `supplier_order_ref Optional[str]`, `idempotency_key str unique`, `status SupplierStatus default SUBMITTED`, `tracking_number Optional[str]`, `raw JSONB`, timestamps
  - `class AdCampaignSync(Base)` — table `revenue_os_ad_campaign_syncs`: `id UUID PK`, `platform str`, `platform_campaign_id str`, `name str`, `status str`, `daily_budget_cents int`, `spend_cents int default 0`, `revenue_cents int default 0`, `roas float default 0`, `last_synced_at`, `metadata JSONB`, unique(platform, platform_campaign_id)
  - `class PriceChangeLock(Base)` — table `revenue_os_price_change_locks`: `product_id UUID PK`, `last_change_at datetime`, `last_delta_percent float`
  - `class ChannelAdapter` ABC (channels/base.py): `verify_webhook(request) -> bool`, `import_orders(since) -> list[dict]`, `sync_products() -> int`, `push_fulfillment(order, tracking=None)`, `reconcile()` — all `async`, all raise `ChannelError` on failure; every concrete adapter implements `@property name -> ChannelType`

- [ ] **Step 1: Write failing tests** — `tests/test_channel_framework.py`

```python
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels.base import ChannelAdapter, ChannelError
from ..enums import ChannelType, SupplierStatus
from ..models import ChannelConnection, SupplierOrder, AdCampaignSync, PriceChangeLock


@pytest.mark.asyncio
async def test_channel_connection_crud(db_session: AsyncSession):
    conn = ChannelConnection(channel=ChannelType.SHOPIFY, name="main-store")
    db_session.add(conn)
    await db_session.commit()
    got = await db_session.scalar(select(ChannelConnection).where(ChannelConnection.channel == ChannelType.SHOPIFY))
    assert got is not None and got.enabled is True


@pytest.mark.asyncio
async def test_supplier_order_idempotency_key_unique(db_session: AsyncSession):
    so = SupplierOrder(order_id="00000000-0000-0000-0000-000000000001", supplier="printful",
                       idempotency_key="ord-123")
    db_session.add(so)
    await db_session.commit()
    so2 = SupplierOrder(order_id="00000000-0000-0000-0000-000000000002", supplier="printful",
                        idempotency_key="ord-123")  # duplicate key must violate unique
    db_session.add(so2)
    with pytest.raises(Exception):
        await db_session.commit()


@pytest.mark.asyncio
async def test_ad_campaign_sync_unique_per_platform(db_session: AsyncSession):
    a = AdCampaignSync(platform="meta", platform_campaign_id="act_1")
    db_session.add(a)
    await db_session.commit()
    b = AdCampaignSync(platform="meta", platform_campaign_id="act_1")
    db_session.add(b)
    with pytest.raises(Exception):
        await db_session.commit()


@pytest.mark.asyncio
async def test_price_change_lock_singleton_per_product(db_session: AsyncSession):
    lock = PriceChangeLock(product_id="00000000-0000-0000-0000-000000000001", last_delta_percent=10.0)
    db_session.add(lock)
    await db_session.commit()
    got = await db_session.get(PriceChangeLock, "00000000-0000-0000-0000-000000000001")
    assert got.last_delta_percent == 10.0
```

- [ ] **Step 2: Run to confirm fail** — `pytest graxia/packages/revenue_os/tests/test_channel_framework.py -v` → FAIL import
- [ ] **Step 3: Add enums** — append to `enums.py`:

```python
class ChannelType(StrEnum):
    SHOPIFY = "shopify"
    POD_SUPPLIER = "pod_supplier"


class SupplierStatus(StrEnum):
    SUBMITTED = "submitted"
    IN_PRODUCTION = "in_production"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    FAILED = "failed"
```

Add to `ActionType`: `AD_BUDGET = "ad_budget"` and `SUPPLIER_PURCHASE = "supplier_purchase"` (append, don't reorder).

- [ ] **Step 4: Add models** — append to `models.py` following existing style (see Interfaces for exact columns; use `UniqueConstraint` for SupplierOrder.idempotency_key and AdCampaignSync(platform, platform_campaign_id); `PriceChangeLock.product_id` is the PK)
- [ ] **Step 5: Add constants** — `constants.py`:

```python
CHANNEL_ORDER_IMPORT_LIMIT = 200
SUPPLIER_POLL_INTERVAL_MIN = 15
ADS_METRICS_WINDOW_DAYS = 7
```

- [ ] **Step 6: Create channels package + base** — `channels/base.py`:

```python
"""Channel adapter framework — one adapter per external commerce surface."""
from __future__ import annotations

import abc
from typing import Any, Optional

from ..enums import ChannelType


class ChannelError(Exception):
    """Raised when an external channel call fails (network, auth, 4xx/5xx)."""


class ChannelAdapter(abc.ABC):
    """Contract every channel must implement. All methods are async."""

    @property
    @abc.abstractmethod
    def name(self) -> ChannelType:
        ...

    @abc.abstractmethod
    async def verify_webhook(self, request: Any) -> bool:
        """Verify the inbound webhook signature BEFORE deserialization."""

    @abc.abstractmethod
    async def import_orders(self, since: Optional[str] = None) -> list[dict]:
        """Return normalized orders: {platform_order_id, customer_email,
        amount_cents, currency, product_id (if mappable), status, metadata}."""

    @abc.abstractmethod
    async def sync_products(self) -> int:
        """Push local published products to the channel; return count."""

    @abc.abstractmethod
    async def push_fulfillment(self, order, tracking: Optional[str] = None) -> None:
        """Mark order fulfilled (or push tracking number)."""

    @abc.abstractmethod
    async def reconcile(self) -> dict:
        """Apply external status changes to local orders; return {updated, skipped}."""
```

- [ ] **Step 7: Run tests to pass** — expected 4 PASSED
- [ ] **Step 8: Commit** — `feat(revenue-os): channel framework - adapters ABC + channel/supplier/ad/pricing models`

**Gate (Task 1):** 4 tests pass; `channels/base.py` imports cleanly.

---

### Task 2: Shopify connector (client, webhook HMAC, sync jobs)

**Files:**
- Create: `graxia/packages/revenue_os/channels/shopify.py`
- Create: `graxia/packages/revenue_os/celery/tasks/shopify_sync.py`
- Create: `graxia/services/revenue_os_api/routers/channels.py`
- Modify: `graxia/services/revenue_os_api/router.py`
- Create: `graxia/packages/revenue_os/tests/test_shopify_adapter.py`

**Interfaces:**
- Consumes: `ChannelAdapter` ABC (Task 1), `Order`/`Product`/`FulfillmentService` (Phase 1), `require_admin_api_key`, `get_db`
- Produces:
  - `class ShopifyAdapter(ChannelAdapter)` — `name=SHOPIFY`; reads `SHOPIFY_STORE_DOMAIN`, `SHOPIFY_ACCESS_TOKEN` from env (fail-closed in production if missing); `verify_webhook` = HMAC-SHA256 over raw body with `SHOPIFY_WEBHOOK_SECRET` (constant-time compare, mirrors `require_stripe_hmac`); `import_orders(since)` uses `GET /admin/api/2024-01/orders.json?status=any&updated_at_min=...`; `sync_products` POST/PUT products; `push_fulfillment` POST `/fulfillments.json`; `reconcile` maps external `cancelled`/`refunded` → local status with direction rules (never downgrade local REFUNDED)
  - `class ShopifyClient` (internal, used by adapter): `async def get_json(path, params)` / `post_json(path, json)` with rate-limit aware backoff (on 429: sleep `Retry-After` or 1s×attempt) — **every request through this client, no raw httpx outside it**
  - `import_shopify_orders(db, since) -> int` — idempotent insert via existing Order unique (platform, platform_order_id); product mapping via `metadata.product_id` on Shopify product (store `graxia_product_id` metafield), else skip with IncidentEvent LOW
  - `sync_shopify_products(db) -> int`
  - `reconcile_shopify(db) -> dict`
  - celery task `shopify_sync()` (lock `shopify_sync`, TTL 600) running import+reconcile (products sync manual via admin endpoint)
  - router: `POST /api/channels/shopify/webhook` (public, adapter.verify_webhook gate), `GET /api/channels` (admin), `POST /api/channels/shopify/sync-products` (admin)

- [ ] **Step 1: Write failing tests** — `tests/test_shopify_adapter.py` (mock httpx via `httpx.MockTransport`; keys: HMAC verify ok/bad, order import idempotent, rate-limit backoff retries once, reconcile direction rules)

```python
import hashlib
import hmac
import json
import pytest
from httpx import AsyncClient, MockTransport, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels.shopify import ShopifyAdapter, ShopifyClient, import_shopify_orders, reconcile_shopify
from ..enums import OrderStatus, ProductStatus
from ..models import Order, Product


def _hmac(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class _FakeRequest:
    def __init__(self, body: bytes, sig: str):
        self._body = body
        self._headers = {"x-shopify-hmac-sha256": sig}

    async def body(self):
        return self._body

    @property
    def headers(self):
        return self._headers


@pytest.mark.asyncio
async def test_verify_webhook_ok(monkeypatch):
    monkeypatch.setenv("SHOPIFY_WEBHOOK_SECRET", "sec")
    payload = b'{"id": 1}'
    req = _FakeRequest(payload, _hmac(payload, "sec"))
    assert await ShopifyAdapter().verify_webhook(req) is True


@pytest.mark.asyncio
async def test_verify_webhook_bad(monkeypatch):
    monkeypatch.setenv("SHOPIFY_WEBHOOK_SECRET", "sec")
    req = _FakeRequest(b'{"id": 1}', "deadbeef")
    assert await ShopifyAdapter().verify_webhook(req) is False


@pytest.mark.asyncio
async def test_client_retries_on_429(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return Response(429, headers={"Retry-After": "0"})
        return Response(200, json={"orders": []})

    transport = MockTransport(handler)
    async with AsyncClient(transport=transport) as client:
        shopify = ShopifyClient(domain="test.myshopify.com", token="t", http_client=client)
        data = await shopify.get_json("/admin/api/2024-01/orders.json")
    assert calls["n"] == 2
    assert data == {"orders": []}


@pytest.mark.asyncio
async def test_import_shopify_orders_idempotent(db_session: AsyncSession, sample_product_data):
    from ..models import Product as P
    product = P(name=sample_product_data["name"], slug=sample_product_data["slug"],
                price_cents=sample_product_data["price_cents"], status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    orders = [{
        "platform_order_id": "shop_1",
        "customer_email": "buyer@example.com",
        "amount_cents": 9900,
        "currency": "THB",
        "product_id": str(product.id),
        "status": "paid",
        "metadata": {"shopify_id": 1001},
    }]
    imported = await import_shopify_orders(db_session, orders)
    assert imported == 1
    again = await import_shopify_orders(db_session, orders)
    assert again == 0  # idempotent
    rows = (await db_session.execute(select(Order).where(Order.platform == "shopify"))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_reconcile_does_not_downgrade_local_refunded(db_session: AsyncSession, sample_product_data, sample_customer_data):
    from ..models import Product as P
    product = P(name=sample_product_data["name"], slug=sample_product_data["slug"],
                price_cents=sample_product_data["price_cents"], status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    from ..services.order_service import OrderService
    order = await OrderService.create_order(
        db_session, platform="shopify", platform_order_id="shop_ref_1",
        customer_email=sample_customer_data["email"], product_id=product.id, amount_cents=9900,
    )
    order.status = OrderStatus.REFUNDED  # local truth
    await db_session.commit()
    # external says 'paid' — must NOT downgrade
    external = {"shop_ref_1": "paid"}
    result = await reconcile_shopify(db_session, external)
    assert result["updated"] == 0
    await db_session.refresh(order)
    assert order.status == OrderStatus.REFUNDED
```

- [ ] **Step 2: Run to confirm fail** — import error
- [ ] **Step 3: Implement `channels/shopify.py`** — ShopifyClient (429-aware backoff, max 3 attempts, `raise ChannelError` on non-2xx after retries) + ShopifyAdapter (verify_webhook with `hmac.compare_digest`; import_orders/sync_products/push_fulfillment/reconcile) + module functions `import_shopify_orders(db, normalized)` (idempotent insert, set PAID, trigger `FulfillmentService.fulfill_order` for digital products, create `SupplierOrder` placeholder for physical) and `reconcile_shopify(db, external_status_map)` (direction rules: external cancelled/refunded → local; NEVER downgrade local REFUNDED or CANCELLED)
- [ ] **Step 4: Create `celery/tasks/shopify_sync.py`** — locked wrapper (`LOCK_NAME="shopify_sync"`, TTL 600): fetch orders since last sync (persist cursor in ChannelConnection config), import, reconcile; separate `sync_products_with_db(db)` for the admin-triggered path
- [ ] **Step 5: Create `routers/channels.py`** — webhook endpoint public with `Depends(verify via adapter)` (read raw body → verify → import), status/sync endpoints admin (`Depends(require_admin_api_key)`); register in `router.py` (prefix `/channels`)
- [ ] **Step 6: Run tests to pass** — 5 PASSED
- [ ] **Step 7: Commit** — `feat(revenue-os): shopify connector - hmac webhooks, rate-limited client, idempotent import, reconcile`

**Gate (Task 2):** 5 tests pass incl. HMAC ok/bad, 429 retry, idempotent import, no-downgrade reconcile.

---

### Task 3: POD/dropship supplier adapter

**Files:**
- Create: `graxia/packages/revenue_os/channels/supplier_pod.py`
- Create: `graxia/packages/revenue_os/celery/tasks/supplier_poll.py`
- Modify: `graxia/packages/revenue_os/services/fulfillment_service.py` (physical branch)
- Create: `graxia/packages/revenue_os/tests/test_supplier_pod.py`

**Interfaces:**
- Consumes: `SupplierOrder` model (Task 1), `FulfillmentService`, `PolicyEngine.check` with `ActionType.SUPPLIER_PURCHASE`, `Product` supplier fields
- Produces:
  - Product model gains (additive): `supplier Optional[str]`, `supplier_cost_cents Optional[int]`, `is_physical bool default False`
  - `class SupplierPODAdapter` — `submit_order(db, order, product) -> SupplierOrder`: policy check `SUPPLIER_PURCHASE` with `value`=margin %, `value_cents`=supplier_cost_cents, `currency`; creates SupplierOrder with `idempotency_key=f"po-{order.id}"`; calls supplier POST `/orders` with `idempotency_key` header where supported; persists `supplier_order_ref` + status SUBMITTED; on network timeout → leave SUBMITTED without ref (re-poll, never duplicate because unique idempotency_key)
  - `parse_status_webhook(payload, secret) -> (order_id, SupplierStatus, tracking)` — HMAC via `SUPPLIER_WEBHOOK_SECRET`
  - `poll_supplier_orders(db) -> dict` — for SUBMITTED/IN_PRODUCTION without ref → skip (retry later); with ref → GET status, update, push tracking to channel via `push_fulfillment`
  - celery task `supplier_poll()` (lock `supplier_poll`, TTL 600)
  - physical fulfillment branch: in `fulfill_order`, when `product.is_physical` → create SupplierOrder (do NOT email download link; queue "order in production" email instead)

- [ ] **Step 1: Write failing tests** — `tests/test_supplier_pod.py`:

```python
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels.supplier_pod import SupplierPODAdapter, parse_status_webhook
from ..core.policy_engine import PolicyEngine
from ..enums import AutonomyMode, ProductStatus, SupplierStatus
from ..models import Product, SupplierOrder


@pytest.mark.asyncio
async def test_submit_order_requires_policy_and_creates_supplier_order(
    db_session: AsyncSession, sample_product_data, sample_customer_data, monkeypatch
):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    product = Product(name=sample_product_data["name"], slug=sample_product_data["slug"],
                      price_cents=sample_product_data["price_cents"], status=ProductStatus.PUBLISHED,
                      supplier="printful", supplier_cost_cents=3000, is_physical=True)
    db_session.add(product)
    await db_session.commit()
    from ..services.order_service import OrderService
    order = await OrderService.create_order(
        db_session, platform="shopify", platform_order_id="pod_1",
        customer_email=sample_customer_data["email"], product_id=product.id, amount_cents=9900,
    )

    class FakeSupplier:
        @staticmethod
        async def submit(order_id: str, idempotency_key: str):
            return {"id": "sup_123", "status": "submitted"}

    adapter = SupplierPODAdapter(client=FakeSupplier())
    so = await adapter.submit_order(db_session, order, product)
    assert so.supplier_order_ref == "sup_123"
    assert so.status == SupplierStatus.SUBMITTED
    got = await db_session.scalar(select(SupplierOrder).where(SupplierOrder.order_id == order.id))
    assert got is not None


@pytest.mark.asyncio
async def test_submit_order_denied_without_autonomy(db_session: AsyncSession, sample_product_data, sample_customer_data, monkeypatch):
    """Policy fail-closed: no seeded rules for SUPPLIER_PURCHASE -> denied."""
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    product = Product(name=sample_product_data["name"], slug=sample_product_data["slug"],
                      price_cents=sample_product_data["price_cents"], status=ProductStatus.PUBLISHED,
                      supplier="printful", supplier_cost_cents=3000, is_physical=True)
    db_session.add(product)
    await db_session.commit()
    from ..services.order_service import OrderService
    order = await OrderService.create_order(
        db_session, platform="shopify", platform_order_id="pod_2",
        customer_email=sample_customer_data["email"], product_id=product.id, amount_cents=9900,
    )
    adapter = SupplierPODAdapter(client=object())
    so = await adapter.submit_order(db_session, order, product)
    assert so is None  # denied — no incident-based refund; callers surface IncidentEvent
```

- [ ] **Step 2: Run to confirm fail**
- [ ] **Step 3: Add Product supplier fields** (additive columns) + **extend `seed_default_rules`** with SUPPLIER_PURCHASE dual caps (PERCENT max 50.0 "max margin %", ABSOLUTE max 100_000_00 cents)
- [ ] **Step 4: Implement `channels/supplier_pod.py`** per Interfaces (submit → policy check → SupplierOrder(idempotency_key) → external call → ref+status; parse webhook; poll with ref)
- [ ] **Step 5: Modify `fulfillment_service.fulfill_order`** — physical branch: instead of download email, queue "in production" email + create SupplierOrder placeholder (status SUBMITTED, no ref yet) so the poll job can retry; keep DeliveryEvent chain (delivery_type="physical")
- [ ] **Step 6: Create `celery/tasks/supplier_poll.py`** — locked wrapper
- [ ] **Step 7: Run tests to pass** — 2 PASSED (submit ok + deny)
- [ ] **Step 8: Commit** — `feat(revenue-os): POD supplier adapter - policy-gated orders, status webhooks, poll task`

**Gate (Task 3):** 2 tests pass; physical orders never email a download link; duplicate submission impossible via unique idempotency_key.

---

### Task 4: Ads platform client (Meta first, interfaces for Google/TikTok)

**Files:**
- Create: `graxia/packages/revenue_os/ads/__init__.py`, `graxia/packages/revenue_os/ads/base.py`, `graxia/packages/revenue_os/ads/meta.py`
- Create: `graxia/packages/revenue_os/tests/test_ads_meta.py`

**Interfaces:**
- Produces:
  - `class AdPlatformError(Exception)`
  - `class AdPlatformClient` ABC: `list_campaigns() -> list[dict]` (platform_campaign_id, name, status, daily_budget_cents), `get_metrics(ids) -> dict[id, {spend_cents, revenue_cents, roas}]`, `set_budget(campaign_id, daily_budget_cents)`, `set_status(campaign_id, active: bool)` — all async
  - `class MetaAdsClient(AdPlatformClient)` — reads `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID` env; `list_campaigns` = GET `/v19.0/act_{id}/campaigns?fields=id,name,status,daily_budget`; `get_metrics` = insights with `date_preset=last_7d` (spend, purchase_roas, purchases); `set_budget` = POST `/campaigns/{id}` daily_budget (cents); `set_status` = POST status; 429-aware backoff like ShopifyClient
  - `sync_ads_metrics(db) -> int` — upsert `AdCampaignSync` rows (unique per platform+campaign) with spend/revenue/roas; never touches budgets (agent job does that, policy-gated)
  - `class MetaAdsClient` constructor takes optional `http_client` for tests

- [ ] **Step 1: Write failing tests** — `tests/test_ads_meta.py` (MockTransport):

```python
import pytest
from httpx import AsyncClient, MockTransport, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..ads.meta import MetaAdsClient, sync_ads_metrics
from ..models import AdCampaignSync


def _client_with(handler):
    return MetaAdsClient(access_token="tok", ad_account_id="act_1",
                         http_client=AsyncClient(transport=MockTransport(handler)))


@pytest.mark.asyncio
async def test_list_campaigns_maps_budget_to_cents():
    def handler(request):
        assert "/campaigns" in request.url.path
        return Response(200, json={"data": [
            {"id": "2384", "name": "Launch", "status": "ACTIVE", "daily_budget": "1500"},
        ]})

    async with _client_with(handler) as client:
        camps = await client.list_campaigns()
    assert camps[0]["daily_budget_cents"] == 1500  # Meta daily_budget is already cents


@pytest.mark.asyncio
async def test_sync_ads_metrics_upserts(db_session: AsyncSession):
    metrics = {"2384": {"spend_cents": 500, "revenue_cents": 1500, "roas": 3.0}}
    await sync_ads_metrics(db_session, platform="meta", metrics=metrics)
    row = await db_session.get(AdCampaignSync, "00000000-0000-0000-0000-000000000000")
    # look up by platform+campaign instead:
    from sqlalchemy import select
    row = (await db_session.execute(
        select(AdCampaignSync).where(AdCampaignSync.platform_campaign_id == "2384")
    )).scalar_one()
    assert row.roas == 3.0
    # upsert again
    await sync_ads_metrics(db_session, platform="meta", metrics={"2384": {"spend_cents": 900, "revenue_cents": 2700, "roas": 3.0}})
    rows = (await db_session.execute(select(AdCampaignSync))).scalars().all()
    assert len(rows) == 1
    assert rows[0].spend_cents == 900
```

- [ ] **Step 2: Run to confirm fail**
- [ ] **Step 3: Implement `ads/base.py` + `ads/meta.py`** per Interfaces; `sync_ads_metrics(db, platform, metrics)` upserts AdCampaignSync (never budgets)
- [ ] **Step 4: Run tests to pass** — 2 PASSED
- [ ] **Step 5: Commit** — `feat(revenue-os): meta ads client - campaigns, metrics sync, budget/status setters`

**Gate (Task 4):** 2 tests pass; metrics sync upserts without touching budgets.

---

### Task 5: Ads optimization agent job (policy-gated, shadow-aware)

**Files:**
- Modify: `graxia/packages/revenue_os/agents/commerce_ops.py` (add `_ads_optimization` job)
- Modify: `graxia/packages/revenue_os/core/policy_engine.py` (seed AD_BUDGET dual caps)
- Create: `graxia/packages/revenue_os/celery/tasks/ads_sync.py`
- Create: `graxia/packages/revenue_os/tests/test_ads_agent.py`

**Interfaces:**
- Consumes: `AdCampaignSync` rows, `PolicyEngine.check` with `ActionType.AD_BUDGET`, `MetaAdsClient`, commerce_ops cycle
- Produces:
  - `seed_default_rules` adds: `(AD_BUDGET, MAX, PERCENT, 10.0, "max daily budget change %")`, `(AD_BUDGET, MAX, ABSOLUTE, 50_000_00, "max daily budget change, THB cents")`
  - `CommerceOpsAgent._ads_optimization(db, shadow) -> tuple[actions, denials, proposals]`:
    - for each AdCampaignSync with roas > 0: target budget = spend × (target_roas / roas); clamp delta to ±10% (percent) and ±50,000 cents; policy check AD_BUDGET with value=delta%, value_cents=abs(delta cents), currency
    - ROAS < 1.0 → propose pause (ActionType.CAMPAIGN_PAUSE policy, allow seeded) instead of budget cut
    - SHADOW → proposals only; LIMITED → budget changes capped by engine multiplier automatically
    - every action/denial logged to AuditLog; denials → IncidentEvent MEDIUM
  - `sync_and_optimize_ads(db) -> dict` — metrics sync then run `_ads_optimization`; celery task `ads_sync()` lock `ads_sync` TTL 600
  - `_ads_optimization` also wired into `run_cycle` (runs after campaign check)

- [ ] **Step 1: Write failing tests** — `tests/test_ads_agent.py`:

```python
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.commerce_ops import CommerceOpsAgent
from ..core.policy_engine import PolicyEngine
from ..enums import AutonomyMode
from ..models import AdCampaignSync


@pytest.mark.asyncio
async def test_ads_job_cuts_budget_for_low_roas_within_policy(db_session: AsyncSession, monkeypatch):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    db_session.add(AdCampaignSync(platform="meta", platform_campaign_id="c1", name="C1",
                                  status="ACTIVE", daily_budget_cents=10000,
                                  spend_cents=5000, revenue_cents=4000, roas=0.8))
    await db_session.commit()

    calls = []
    class FakeClient:
        async def set_budget(self, campaign_id, daily_budget_cents):
            calls.append((campaign_id, daily_budget_cents))

    monkeypatch.setattr("graxia.packages.revenue_os.agents.commerce_ops.ads_client", FakeClient())
    actions, denials, proposals = await CommerceOpsAgent._ads_optimization(db_session, shadow=False)
    assert any("ad_budget" in a for a in actions)
    assert len(calls) == 1
    # 10% cut of 10,000 cents
    assert calls[0][1] == 9000


@pytest.mark.asyncio
async def test_ads_job_shadow_proposes_without_calling_api(db_session: AsyncSession, monkeypatch):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.SHADOW)
    db_session.add(AdCampaignSync(platform="meta", platform_campaign_id="c2", name="C2",
                                  status="ACTIVE", daily_budget_cents=10000,
                                  spend_cents=5000, revenue_cents=4000, roas=0.8))
    await db_session.commit()

    called = {"n": 0}
    class FakeClient:
        async def set_budget(self, campaign_id, daily_budget_cents):
            called["n"] += 1

    monkeypatch.setattr("graxia.packages.revenue_os.agents.commerce_ops.ads_client", FakeClient())
    actions, denials, proposals = await CommerceOpsAgent._ads_optimization(db_session, shadow=True)
    assert actions == []
    assert any("ad_budget" in p for p in proposals)
    assert called["n"] == 0
```

- [ ] **Step 2: Run to confirm fail**
- [ ] **Step 3: Implement** — seed rules addition; `_ads_optimization` per Interfaces; module-level `ads_client = MetaAdsClient()` in commerce_ops (monkeypatch target); wire into `run_cycle`; create `ads_sync` task
- [ ] **Step 4: Run tests to pass** — 2 PASSED
- [ ] **Step 5: Commit** — `feat(revenue-os): ads optimization agent - policy-gated budget changes, shadow-aware`

**Gate (Task 5):** 2 tests pass; SHADOW never calls Meta API; budget delta capped by policy in both modes.

---

### Task 6: Dynamic pricing engine (shared price-write path)

**Files:**
- Create: `graxia/packages/revenue_os/pricing/dynamic.py`
- Modify: `graxia/packages/revenue_os/agents/commerce_ops.py` (extract shared `_apply_price_change(db, product, delta_percent)` used by both jobs)
- Modify: `graxia/packages/revenue_os/celery/celery_app.py` (pricing cadence)
- Create: `graxia/packages/revenue_os/tests/test_dynamic_pricing.py`

**Interfaces:**
- Produces:
  - `class DynamicPricingEngine`:
    - `@staticmethod async def propose(db, product) -> Optional[float]` — rule-based delta%: stale product (>14d no sales) → −10; high demand (sales in last 3d ≥ threshold) → +5; weekend boost config; returns None if no signal
    - `@staticmethod async def apply(db, product, delta_percent) -> bool` — **shared price-write path**: check `PriceChangeLock` (last change < 24h → skip, log); policy check PRICE_CHANGE (value=abs(delta%), value_cents=abs cents delta, product_id, currency); on allow → update price + upsert PriceChangeLock; SHADOW → log proposal only
  - commerce_ops `_price_optimization` refactored to call `_apply_price_change` (one write path, no lost updates)
  - pricing beat job (fold into commerce_ops run_cycle after price optimization — no separate task needed; remove plan's separate pricing task to avoid double-writers)

- [ ] **Step 1: Write failing tests** — `tests/test_dynamic_pricing.py` (propose signals, apply respects PriceChangeLock 24h, apply denied by tight policy, apply shadow no-op)
- [ ] **Step 2: Run to confirm fail**
- [ ] **Step 3: Implement** per Interfaces; refactor commerce_ops price job through `_apply_price_change`; keep `run_cycle` ordering: price optimization → dynamic pricing → campaign check → ads → stale orders → report
- [ ] **Step 4: Run tests to pass** — 4 PASSED; full commerce_ops suite still green (7)
- [ ] **Step 5: Commit** — `feat(revenue-os): dynamic pricing engine - shared policy-gated price path with change lock`

**Gate (Task 6):** 4 new tests + existing commerce_ops suite green; single price-write path (no concurrent price jobs).

---

### Task 7: Backtest harness

**Files:**
- Create: `graxia/packages/revenue_os/simulation/__init__.py`, `graxia/packages/revenue_os/simulation/backtest.py`
- Create: `graxia/packages/revenue_os/celery/tasks/backtest_runner.py`
- Create: `graxia/packages/revenue_os/tests/test_backtest.py`

**Interfaces:**
- Produces:
  - `run_backtest(db, days=30, include_agents=(price, dynamic_price, ads)) -> dict` — replay: fetch historical MetricDaily + orders for window; simulate each agent decision through the REAL `PolicyEngine.check` with the REAL seeded ruleset; apply decisions to a copy of product prices (in-memory, never DB); track simulated revenue delta vs actual; output `{window_days, decisions, allowed, denied, est_revenue_impact_cents, report_lines}`
  - `BacktestReport` writer → StrategyLog entry (nightly) + optional Telegram summary
  - celery task `backtest_runner()` lock `backtest_runner` TTL 600 — runs only when autonomy mode != OFF (else skip, since decisions need policy context)
  - `estimate_impact(decisions) -> dict` — per-action-type aggregate (price_change, ad_budget) revenue impact estimate using simple elasticity defaults, clearly labeled ESTIMATE

- [ ] **Step 1: Write failing tests** — `tests/test_backtest.py` (empty history → zeros; decisions respect policy denies — tight rule blocks a simulated price cut; report contains per-action aggregates)
- [ ] **Step 2: Run to confirm fail**
- [ ] **Step 3: Implement** per Interfaces (in-memory replay, real policy)
- [ ] **Step 4: Run tests to pass** — 3 PASSED
- [ ] **Step 5: Commit** — `feat(revenue-os): backtest harness - replay history through real policy engine`

**Gate (Task 7):** 3 tests pass; harness never writes business state; estimates labeled ESTIMATE.

---

### Task 8: Celery beat wiring + full-suite regression

**Files:**
- Modify: `graxia/packages/revenue_os/celery/celery_app.py`

- [ ] **Step 1: Add beat entries** (copy existing style, seconds or crontab):

```python
    "shopify-sync": {
        "task": "graxia.packages.revenue_os.celery.tasks.shopify_sync",
        "schedule": 300.0,  # every 5 min
        "options": {"queue": "default"},
    },
    "supplier-poll": {
        "task": "graxia.packages.revenue_os.celery.tasks.supplier_poll",
        "schedule": 900.0,  # every 15 min
        "options": {"queue": "default"},
    },
    "ads-sync": {
        "task": "graxia.packages.revenue_os.celery.tasks.ads_sync",
        "schedule": 3600.0,  # hourly
        "options": {"queue": "default"},
    },
    "backtest-runner": {
        "task": "graxia.packages.revenue_os.celery.tasks.backtest_runner",
        "schedule": 86400.0,  # nightly
        "options": {"queue": "reporting"},
    },
```

- [ ] **Step 2: Import smoke** — `python -c "from graxia.packages.revenue_os.celery.tasks import shopify_sync, supplier_poll, ads_sync, backtest_runner; print('ok')"` → `ok`
- [ ] **Step 3: Full backend suite** — `pytest graxia/packages/revenue_os/tests/ -q` → Phase 1 baseline (14 documented failures) + all new Phase 2 tests green, ZERO errors
- [ ] **Step 4: Commit** — `feat(revenue-os): celery beat - shopify/supplier/ads/backtest cycles (locked)`

**Gate (Task 8):** import smoke ok; full suite matches documented baseline + new tests.

---

### Task 9: Runbooks + design doc update

**Files:**
- Create: `docs/runbooks/channel-onboarding.md` — Shopify app install (API key/secret, storefront+read_orders+write_products+write_fulfillments scopes), webhook subscription (orders/paid, orders/cancelled, orders/refunded), env vars (`SHOPIFY_STORE_DOMAIN`, `SHOPIFY_ACCESS_TOKEN`, `SHOPIFY_WEBHOOK_SECRET`), supplier setup (API key + webhook secret), Meta app (access token + ad account id), rate-limit notes
- Create: `docs/runbooks/ads-budgets.md` — budget policy defaults (10%/50k THB per change), ROAS rules (pause < 1.0, cut on 1.0-2.0, hold 2.0-4.0, raise > 4.0), kill procedure (`POST /api/autonomy/mode {"mode":"off"}`, `POST /api/ads/refresh` to re-sync), LIMITED-mode expectations
- Modify: `docs/superpowers/specs/2026-08-16-autonomous-ecommerce-design.md` — Phase 2 status section (completed tasks, env vars, deviations)

- [ ] **Step 1: Write both runbooks + update design doc** (patterns from Phase 1 runbook)
- [ ] **Step 2: Commit** — `docs: phase 2 runbooks (channels, ads budgets) + spec status`

**Gate (Task 9):** runbooks reference only env-var secrets (no literal keys); design doc updated.

---

## Self-Review Notes

- **Spec coverage:** channel framework (T1), Shopify (T2), POD supplier (T3), ads client (T4), ads agent (T5), dynamic pricing (T6), backtest (T7), beat+regression (T8), docs (T9). Phase 3 (marketplaces, affiliate) deferred to a later plan as decided in the Phase 1 spec §8.
- **Consistency with Phase 1:** every new money action seeds dual PERCENT+ABSOLUTE rules and passes `value`/`value_cents`/`currency`; all beat tasks lock-wrapped with TTL ≥ 600; SHADOW never calls external APIs; admin endpoints reuse `require_admin_api_key`; webhooks HMAC-verified before deserialization.
- **Verification risks (check before running each task's suite):** exact `httpx` version API (`MockTransport`), Shopify admin API version path (2024-01 assumed — update to current), Meta Graph API version (v19.0 assumed), `Retry-After` header semantics, `SupplierOrder` FK target table names, Product additive columns don't collide with existing ones.
- **Type consistency:** `ChannelAdapter.name -> ChannelType`; `AdPlatformClient` ABC used by Meta; `_apply_price_change(db, product, delta_percent)` shared by both pricing jobs; `ads_client` module-level in commerce_ops for monkeypatching; `sync_ads_metrics(db, platform, metrics)` upsert signature.
