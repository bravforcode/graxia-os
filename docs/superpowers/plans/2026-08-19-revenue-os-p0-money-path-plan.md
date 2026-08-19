# Revenue OS P0 — Money-Path Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Graxia Revenue OS able to accept real money — subscription checkout, new plan tiers, kill switch, deployed API — verified by a full Stripe test-mode payment flow.

**Architecture:** Extend the existing FastAPI revenue_os_api (checkout/billing routers) with subscription-mode checkout + webhook lifecycle mirroring, re-seed plan tiers (Starter/Growth/Scale/Enterprise), add a JSON-file-backed money kill switch (quant_os pattern) guarding all money paths, and deploy the API to Render so Stripe webhooks can reach it. Legacy Vercel funnel remains the customer-facing money path.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async + asyncpg, Stripe (Checkout/Subscriptions/Billing Portal), PostgreSQL (Supabase), Render (deploy), pytest + real test DB.

**Spec:** `docs/superpowers/specs/2026-08-19-revenue-roadmap-design.md` (P0 section, T1–T7 + G4 bridge)

## Global Constraints

- Money paths fail-closed: no silent PROCESSING orders, no client-supplied amounts, no irreversible action without guard.
- All Stripe calls go through module-level monkeypatch targets (`stripe_checkout`, `stripe_subscriptions`, `stripe_refunds`, `stripe_billing_portal`) — tests never hit the Stripe API.
- Tests use the real Postgres test DB via `graxia/packages/revenue_os/tests/conftest.py` fixtures (`db_session`). No mock DB.
- Run tests from repo root: `pytest graxia/packages/revenue_os/tests/<file>.py -v`.
- Plan tiers (THB/month, from spec/pricing doc): starter ฿499 (49_900), growth ฿1,490 (149_000), scale ฿4,900 (490_000), enterprise = custom quote (sales-led, not self-serve).
- LeadStatus enum (spec G4): base `new → contacted → responded → qualified → proposal_sent → negotiating → converted → lost` + new `demo`/`trial`/`paid`.
- No new dependencies. No `.env` secrets committed. `.env.graxia` is loaded by `app.py` (override=False) — never log its values.
- Every task ends with a commit. Commit messages follow repo style (`feat(scope): ...`, `test(scope): ...`).

---

### Task 1: Subscription checkout mode

**Files:**
- Modify: `graxia/packages/revenue_os/schemas.py:322-327` (CheckoutSessionCreate)
- Modify: `graxia/services/revenue_os_api/routers/checkout.py:71-98` (create_checkout_session)
- Test: `graxia/packages/revenue_os/tests/test_checkout.py`

**Interfaces:**
- Consumes: `Product` model (`price_cents`, `currency`, `name`, `status`, `stripe_price_id` — models.py:183-214), `ProductStatus.PUBLISHED`, `CheckoutSessionCreate`
- Produces: `CheckoutSessionCreate.mode: Literal["payment","subscription"]` (default `"payment"`); checkout uses `price=product.stripe_price_id` when set, else `price_data` (+ `recurring: {"interval": "month"}` when mode=subscription); metadata gains `"mode"`.

- [ ] **Step 1: Write the failing tests**

Add to `test_checkout.py` (after existing tests, ~line 80):

```python
@pytest.mark.asyncio
async def test_create_checkout_session_subscription_mode(
    db_session: AsyncSession, published_product: Product, monkeypatch
):
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeSession()

    monkeypatch.setattr(stripe_checkout, "create", fake_create)

    payload = CheckoutSessionCreate(
        product_id=published_product.id,
        customer_email="buyer@example.com",
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
        mode="subscription",
    )
    resp = await create_checkout_session(payload, db_session)

    assert resp.session_id == "cs_test_123"
    assert captured["mode"] == "subscription"
    assert captured["line_items"][0]["price_data"]["recurring"] == {"interval": "month"}
    assert captured["metadata"]["mode"] == "subscription"


@pytest.mark.asyncio
async def test_create_checkout_session_uses_stripe_price_id(
    db_session: AsyncSession, published_product: Product, monkeypatch
):
    published_product.stripe_price_id = "price_123"
    await db_session.flush()
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeSession()

    monkeypatch.setattr(stripe_checkout, "create", fake_create)

    payload = CheckoutSessionCreate(
        product_id=published_product.id,
        customer_email="buyer@example.com",
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
    )
    await create_checkout_session(payload, db_session)

    assert captured["line_items"][0]["price"] == "price_123"
    assert "price_data" not in captured["line_items"][0]


@pytest.mark.asyncio
async def test_create_checkout_session_rejects_invalid_mode(
    db_session: AsyncSession, published_product: Product
):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CheckoutSessionCreate(
            product_id=published_product.id,
            customer_email="buyer@example.com",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
            mode="bogus",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest graxia/packages/revenue_os/tests/test_checkout.py -v`
Expected: FAIL — `ValidationError` on `mode` (extra field not allowed) and `mode` key missing from captured kwargs.

- [ ] **Step 3: Implement**

`schemas.py` — add `Literal` import if missing (`from typing import Literal` at top) and extend the model:

```python
class CheckoutSessionCreate(BaseModel):
    """Payload for creating a Stripe Checkout session (customer-facing)."""
    product_id: UUID
    customer_email: EmailStr
    success_url: str = Field(..., min_length=1, max_length=2000)
    cancel_url: str = Field(..., min_length=1, max_length=2000)
    mode: Literal["payment", "subscription"] = "payment"
```

`checkout.py` — replace the `stripe_checkout.create(...)` block (lines 71-92) with:

```python
    stripe.api_key = _get_stripe_secret_key()

    # Line item: prefer Stripe-managed price (Price ID) when wired, else
    # inline price_data. Subscription mode adds monthly recurring.
    if product.stripe_price_id:
        line_item = {"price": product.stripe_price_id, "quantity": 1}
    else:
        price_data: dict = {
            "currency": (product.currency or "THB").lower(),
            "unit_amount": product.price_cents,
            "product_data": {"name": product.name},
        }
        if payload.mode == "subscription":
            price_data["recurring"] = {"interval": "month"}
        line_item = {"price_data": price_data, "quantity": 1}

    try:
        session = stripe_checkout.create(
            mode=payload.mode,
            success_url=payload.success_url,
            cancel_url=payload.cancel_url,
            line_items=[line_item],
            metadata={"product_id": str(product.id), "mode": payload.mode},
            customer_email=payload.customer_email,
        )
    except stripe.error.StripeError as exc:
        logger.error("Stripe checkout session creation failed: %s", exc)
        raise HTTPException(status_code=502, detail="Payment provider error")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_checkout.py -v`
Expected: PASS (all tests incl. existing 3).

- [ ] **Step 5: Commit**

```bash
git add graxia/packages/revenue_os/schemas.py graxia/services/revenue_os_api/routers/checkout.py graxia/packages/revenue_os/tests/test_checkout.py
git commit -m "feat(revenue-os): subscription checkout mode + Stripe Price ID path"
```

---

### Task 2: Subscription lifecycle webhook mirror + billing portal

**Files:**
- Modify: `graxia/packages/revenue_os/services/billing_service.py` (add `handle_subscription_created`, `create_portal_session`, `stripe_billing_portal` target)
- Modify: `graxia/services/revenue_os_api/routers/checkout.py:166-179` (webhook branch)
- Modify: `graxia/services/revenue_os_api/routers/billing.py` (portal endpoint)
- Test: `graxia/packages/revenue_os/tests/test_billing.py`

**Interfaces:**
- Consumes: `Subscription` model (models.py:151-176), `Customer.stripe_customer_id`, `BillingService` (existing), `require_stripe_hmac` webhook dependency
- Produces: `BillingService.handle_subscription_created(db, stripe_sub: dict) -> Optional[Subscription]` (idempotent by `stripe_subscription_id`); `BillingService.create_portal_session(db, customer_email: str) -> str` (raises `ValueError` when no Stripe customer); `POST /api/billing/portal-session {customer_email} -> {url}`.

- [ ] **Step 1: Write the failing tests**

Add to `test_billing.py`:

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Customer, Subscription
from ..services.billing_service import BillingService, stripe_billing_portal


@pytest.mark.asyncio
async def test_handle_subscription_created_creates_mirror_row(db_session: AsyncSession):
    stripe_sub = {
        "id": "sub_test_1",
        "metadata": {"plan": "starter", "customer_email": "buyer@example.com"},
        "items": {"data": [{"price": {"unit_amount": 49900}}]},
    }
    sub = await BillingService.handle_subscription_created(db_session, stripe_sub)
    assert sub is not None
    assert sub.plan == "starter"
    assert sub.price_cents == 49900
    assert sub.status == "active"

    # Idempotent: same event again returns the same row, no duplicate
    sub2 = await BillingService.handle_subscription_created(db_session, stripe_sub)
    rows = (await db_session.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == "sub_test_1")
    )).scalars().all()
    assert len(rows) == 1
    assert sub2.id == sub.id


@pytest.mark.asyncio
async def test_create_portal_session_returns_url(db_session: AsyncSession, monkeypatch):
    customer = Customer(email="buyer@example.com", name="Buyer", stripe_customer_id="cus_test_1")
    db_session.add(customer)
    await db_session.flush()

    class _FakePortalSession:
        url = "https://billing.stripe.com/session/test"

    monkeypatch.setattr(stripe_billing_portal, "create", lambda **kwargs: _FakePortalSession())

    url = await BillingService.create_portal_session(db_session, "buyer@example.com")
    assert url == "https://billing.stripe.com/session/test"


@pytest.mark.asyncio
async def test_create_portal_session_no_customer_raises(db_session: AsyncSession):
    with pytest.raises(ValueError):
        await BillingService.create_portal_session(db_session, "nobody@example.com")
```

Note: add `from sqlalchemy import select` to test imports if not already present.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest graxia/packages/revenue_os/tests/test_billing.py -v`
Expected: FAIL — `AttributeError: module 'graxia.packages.revenue_os.services.billing_service' has no attribute 'handle_subscription_created'` (and `stripe_billing_portal`).

- [ ] **Step 3: Implement**

`billing_service.py` — add module-level target after `stripe_subscriptions` (line 23):

```python
stripe_billing_portal = stripe.billing_portal.Session  # monkeypatch target for tests
```

Add methods to `BillingService` (after `handle_subscription_deleted`):

```python
    @staticmethod
    async def handle_subscription_created(db: AsyncSession, stripe_sub: dict) -> Optional[Subscription]:
        """Webhook: customer.subscription.created → mirror row (idempotent)."""
        sid = stripe_sub.get("id")
        if not sid:
            return None
        existing = await db.scalar(
            select(Subscription).where(Subscription.stripe_subscription_id == sid)
        )
        if existing:
            return existing
        metadata = stripe_sub.get("metadata", {}) or {}
        items = stripe_sub.get("items", {}).get("data", []) or []
        price_cents = 0
        if items:
            price_cents = items[0].get("price", {}).get("unit_amount") or 0
        sub = Subscription(
            customer_email=metadata.get("customer_email") or "",
            plan=metadata.get("plan") or "starter",
            status="active",
            stripe_subscription_id=sid,
            price_cents=price_cents,
            currency="THB",
            current_period_end=datetime.utcnow(),
        )
        db.add(sub)
        await db.commit()
        logger.info("subscription_created_webhook", stripe_subscription_id=sid)
        return sub

    @staticmethod
    async def create_portal_session(db: AsyncSession, customer_email: str) -> str:
        """Create a Stripe billing portal session URL for a customer."""
        customer = await db.scalar(
            select(Customer).where(Customer.email == customer_email)
        )
        if customer is None or not customer.stripe_customer_id:
            raise ValueError(f"no Stripe customer for {customer_email}")
        stripe.api_key = _get_stripe_secret_key()
        session = stripe_billing_portal.create(customer=customer.stripe_customer_id)
        return session.url
```

`checkout.py` webhook — add branch after `customer.subscription.deleted` (line 176):

```python
        elif event_type == "customer.subscription.created":
            from ....packages.revenue_os.services.billing_service import BillingService
            await BillingService.handle_subscription_created(db, event["data"]["object"])
            logger.info("customer.subscription.created processed")
```

`billing.py` — add portal endpoint (after `create_subscription`):

```python
class PortalSessionRequest(BaseModel):
    customer_email: EmailStr


class PortalSessionResponse(BaseModel):
    url: str


@router.post(
    "/portal-session",
    response_model=PortalSessionResponse,
    summary="Create Stripe billing portal session",
)
async def create_portal_session(
    payload: PortalSessionRequest,
    db: AsyncSession = Depends(get_db),
) -> PortalSessionResponse:
    try:
        url = await BillingService.create_portal_session(db, payload.customer_email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return PortalSessionResponse(url=url)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_billing.py -v`
Expected: PASS (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add graxia/packages/revenue_os/services/billing_service.py graxia/services/revenue_os_api/routers/checkout.py graxia/services/revenue_os_api/routers/billing.py graxia/packages/revenue_os/tests/test_billing.py
git commit -m "feat(revenue-os): subscription webhook mirror + billing portal session"
```

---

### Task 3: New plan tiers (Starter/Growth/Scale)

**Files:**
- Modify: `graxia/packages/revenue_os/services/billing_service.py:26-29` (PLAN_PRICES_CENTS)
- Modify: `graxia/services/revenue_os_api/routers/billing.py:16` (plan pattern)
- Modify: `scripts/seed_revenue_os_demo.py:50-86` (product seeds)
- Test: `graxia/packages/revenue_os/tests/test_billing.py`

**Interfaces:**
- Consumes: `BillingService.create_subscription(db, customer_email, plan)` (existing signature)
- Produces: `PLAN_PRICES_CENTS = {"starter": 49_900, "growth": 149_000, "scale": 490_000}`; billing API accepts `^(starter|growth|scale)$`; seed creates 4 subscription products (starter/growth/scale fixed price, enterprise custom-quote price_cents=0).

- [ ] **Step 1: Write the failing tests**

Add to `test_billing.py`:

```python
from ..services.billing_service import PLAN_PRICES_CENTS


def test_plan_prices_match_pricing_doc():
    assert PLAN_PRICES_CENTS == {"starter": 49_900, "growth": 149_000, "scale": 490_000}


@pytest.mark.asyncio
async def test_create_subscription_starter_price(db_session: AsyncSession, monkeypatch):
    from ..services.billing_service import stripe_subscriptions

    class _FakeSub:
        id = "sub_test_starter"

    monkeypatch.setattr(stripe_subscriptions, "create", lambda **kwargs: _FakeSub())

    sub = await BillingService.create_subscription(db_session, "buyer@example.com", "starter")
    assert sub.plan == "starter"
    assert sub.price_cents == 49_900


@pytest.mark.asyncio
async def test_create_subscription_unknown_plan_raises(db_session: AsyncSession):
    with pytest.raises(ValueError):
        await BillingService.create_subscription(db_session, "buyer@example.com", "standard")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest graxia/packages/revenue_os/tests/test_billing.py -v`
Expected: FAIL — `PLAN_PRICES_CENTS` still `{"standard": 490_000, "enterprise": 1_990_000}`.

- [ ] **Step 3: Implement**

`billing_service.py`:

```python
# THB cents — matches pricing strategy (docs/strategy/2026-08-17-pricing-strategy.md)
PLAN_PRICES_CENTS: dict[str, int] = {
    "starter": 49_900,    # 499 THB/mo
    "growth": 149_000,    # 1,490 THB/mo
    "scale": 490_000,     # 4,900 THB/mo
    # enterprise = custom quote / % uplift (sales-led, not self-serve)
}
```

`billing.py` line 16:

```python
    plan: str = Field(..., pattern="^(starter|growth|scale)$")
```

`seed_revenue_os_demo.py` — replace the two CORE products (lines ~68-77) with four subscription products:

```python
    db.add(Product(
        name="Revenue OS Starter",
        slug="revenue-os-starter",
        type=ProductType.CORE,
        price_cents=49900,  # 499 THB/mo
        currency="THB",
        status=ProductStatus.PUBLISHED,
        promise="1 channel, orders, fulfillment, basic email, 1 user",
        target_audience="SMB <1M THB/yr",
    ))
    db.add(Product(
        name="Revenue OS Growth",
        slug="revenue-os-growth",
        type=ProductType.CORE,
        price_cents=149000,  # 1,490 THB/mo
        currency="THB",
        status=ProductStatus.PUBLISHED,
        promise="All channels, campaigns, approvals, AI ops agent, 5 users",
        target_audience="SMB 1-5M THB/yr",
    ))
    db.add(Product(
        name="Revenue OS Scale",
        slug="revenue-os-scale",
        type=ProductType.CORE,
        price_cents=490000,  # 4,900 THB/mo
        currency="THB",
        status=ProductStatus.PUBLISHED,
        promise="Everything + SLA 99.5% + onboarding + premium support",
        target_audience="Mid-market 5-20M THB/yr",
    ))
    db.add(Product(
        name="Revenue OS Enterprise (Custom Quote)",
        slug="revenue-os-enterprise",
        type=ProductType.CORE,
        price_cents=0,  # sales-led — checkout guard blocks price_cents<=0
        currency="THB",
        status=ProductStatus.PUBLISHED,
        promise="Full stack, dedicated ops, SLA 99.9%, % uplift model",
        target_audience="20M+ THB/yr",
    ))
```

Keep the existing lead magnet (0), low ticket (99000), and service (2500000) products unchanged. Match the exact `Product(...)` constructor style already used in the file (check surrounding lines for extra fields like `deliverables` and mirror them).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_billing.py -v`
Expected: PASS.

Then verify the seed script still parses and runs against a dev DB (not the test DB):

Run: `python -c "import ast; ast.parse(open('scripts/seed_revenue_os_demo.py', encoding='utf-8').read())"`
Expected: no syntax errors.

- [ ] **Step 5: Commit**

```bash
git add graxia/packages/revenue_os/services/billing_service.py graxia/services/revenue_os_api/routers/billing.py scripts/seed_revenue_os_demo.py graxia/packages/revenue_os/tests/test_billing.py
git commit -m "feat(revenue-os): new plan tiers starter/growth/scale + enterprise custom quote"
```

---

### Task 4: Stripe Price ID wiring (founder ops + verification)

**Files:**
- Modify: `scripts/seed_revenue_os_demo.py` (add `stripe_price_id` fields — empty by default)
- Docs: `docs/runbooks/` (new: `revenue-os-stripe-wiring.md`)

**Interfaces:**
- Consumes: `Product.stripe_price_id` (models.py:208), checkout `price=` path (Task 1)
- Produces: runbook with exact dashboard steps + SQL to wire Price IDs; seed products carry `stripe_price_id` column values.

- [ ] **Step 1: Add `stripe_price_id` to seeded subscription products**

In `seed_revenue_os_demo.py`, add `stripe_price_id=""` to the four subscription products added in Task 3 (placeholder — real IDs are set via SQL after dashboard creation, see Step 3).

- [ ] **Step 2: Write the runbook**

Create `docs/runbooks/revenue-os-stripe-wiring.md`:

```markdown
# Revenue OS — Stripe Price ID Wiring

## 1. Stripe dashboard (founder action)
1. Stripe Dashboard → Products → Create product for each tier:
   - Revenue OS Starter — ฿499/month (recurring)
   - Revenue OS Growth — ฿1,490/month (recurring)
   - Revenue OS Scale — ฿4,900/month (recurring)
2. Copy each Price ID (`price_...`) — one per tier.

## 2. Wire into DB (run against the deployed revenue_os DB)
```sql
UPDATE revenue_os_products SET stripe_price_id = 'price_STARTER' WHERE slug = 'revenue-os-starter';
UPDATE revenue_os_products SET stripe_price_id = 'price_GROWTH' WHERE slug = 'revenue-os-growth';
UPDATE revenue_os_products SET stripe_price_id = 'price_SCALE' WHERE slug = 'revenue-os-scale';
```

## 3. Verify
- Checkout with a wired product uses `price=` (Stripe-managed) — covered by
  `test_create_checkout_session_uses_stripe_price_id`.
- Stripe dashboard → Payment links / Checkout test: complete a test payment.
```

- [ ] **Step 3: Verify wiring end-to-end (founder, after dashboard IDs exist)**

Run: `pytest graxia/packages/revenue_os/tests/test_checkout.py::test_create_checkout_session_uses_stripe_price_id -v`
Expected: PASS (proves the `price=` path).

- [ ] **Step 4: Commit**

```bash
git add scripts/seed_revenue_os_demo.py docs/runbooks/revenue-os-stripe-wiring.md
git commit -m "docs(revenue-os): Stripe Price ID wiring runbook + seed placeholders"
```

---

### Task 5: Production URL verification

**Files:**
- Verify: `.env.production:64-70`, `vercel.json`, `frontend/src/**` (no `127.0.0.1` API base)

**Interfaces:**
- Consumes: nothing
- Produces: verified production frontend → API wiring; any stale localhost reference fixed.

- [ ] **Step 1: Grep for stale localhost API references**

Run: `rg -n "127\.0\.0\.1|localhost:8000" frontend/src .env.production vercel.json`
Expected: `.env.production` lines 65-70 already point at `https://graxia-os-funnel.vercel.app/api/v1` (fixed 2026-08-17, comment `P0-4`). Any hit in `frontend/src` must be fixed (replace with `import.meta.env.VITE_API_BASE_URL`).

- [ ] **Step 2: Verify Vercel rewrite target**

Run: `Get-Content vercel.json`
Expected: `/api/*` rewrites to `api/store_main.py` (legacy funnel = money path per pricing doc §4). No change needed.

- [ ] **Step 3: Fix if any hit found**

If Step 1 found a hardcoded localhost in `frontend/src`, replace it with the env var and rebuild. If nothing found, skip.

- [ ] **Step 4: Commit (only if a fix was needed)**

```bash
git add frontend/src/...
git commit -m "fix(frontend): replace hardcoded localhost API base with env var"
```

---

### Task 6: Deploy revenue_os to Render

**Files:**
- Modify: `render.yaml` (add revenue_os web service)
- Docs: `docs/runbooks/revenue-os-deploy.md` (new)

**Interfaces:**
- Consumes: `Dockerfile.revenue-os` (entrypoint `uvicorn graxia.services.revenue_os_api.app:app`, healthcheck `/api/system/readiness`), `graxia/services/revenue_os_api/app.py` (loads `.env.graxia`, override=False)
- Produces: deployed `https://graxia-revenue-os.onrender.com` with `POST /api/checkout/stripe-webhook` reachable by Stripe.

- [ ] **Step 1: Add Render service to `render.yaml`**

Append a second web service (keep existing `graxia-backend` untouched):

```yaml
  # ── Revenue OS API (money path — Stripe webhook target) ────────────────
  - type: web
    name: graxia-revenue-os
    runtime: docker
    repo: https://github.com/bravforcode/graxia-os.git
    branch: main
    dockerfilePath: ./Dockerfile.revenue-os
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: graxia-db
          property: connectionString
      - { key: APP_ENV, value: production }
      - { key: REQUIRE_SUPABASE, value: "false" }
      - { key: ALLOWED_ORIGINS, value: "https://graxia-os-funnel.vercel.app" }
      - { key: RATE_LIMIT_RPM, value: "60" }
      # Manual env vars (fill in Render dashboard)
      - { key: STRIPE_SECRET_KEY, sync: false }
      - { key: STRIPE_WEBHOOK_SECRET, sync: false }
      - { key: ADMIN_API_KEY, sync: false }
    healthCheckPath: /api/system/readiness
    autoDeploy: true
```

- [ ] **Step 2: Write the deploy runbook**

Create `docs/runbooks/revenue-os-deploy.md`:

```markdown
# Revenue OS — Deploy Runbook (Render)

## 1. Deploy
1. Push `render.yaml` change to GitHub main.
2. Render Dashboard → Blueprint → Connect repo (or "Update" existing blueprint).
3. Fill manual env vars in Render dashboard:
   - `STRIPE_SECRET_KEY` — live key (from `.env.graxia`, never commit)
   - `STRIPE_WEBHOOK_SECRET` — from Stripe webhook endpoint (Step 3)
   - `ADMIN_API_KEY` — strong random value
4. Deploy. Wait for healthcheck `/api/system/readiness` to go green.

## 2. Verify API
```bash
curl -s https://graxia-revenue-os.onrender.com/api/system/readiness
# Expected: {"status":"ready", ...} (200)
```

## 3. Register Stripe webhook (founder action)
1. Stripe Dashboard → Developers → Webhooks → Add endpoint:
   - URL: `https://graxia-revenue-os.onrender.com/api/checkout/stripe-webhook`
   - Events: `checkout.session.completed`, `charge.refunded`,
     `customer.subscription.created`, `customer.subscription.deleted`
2. Copy the signing secret (`whsec_...`) into Render env `STRIPE_WEBHOOK_SECRET`.
3. Send a test event from the dashboard → confirm 200 + `"status":"success"`.

## 4. Money-path smoke (Stripe test mode)
1. Create a test checkout session (Starter product) via the API.
2. Complete payment with Stripe test card `4242 4242 4242 4242`.
3. Confirm webhook received → order PAID + subscription mirror row created.
```

- [ ] **Step 3: Commit**

```bash
git add render.yaml docs/runbooks/revenue-os-deploy.md
git commit -m "feat(deploy): revenue_os Render service + deploy runbook"
```

- [ ] **Step 4: Deploy + register webhook (founder action — outside code)**

Follow the runbook. This task is complete when `/api/system/readiness` returns 200 on Render and Stripe test events return 200.

---

### Task 7: Money kill switch

**Files:**
- Create: `graxia/packages/revenue_os/services/kill_switch.py`
- Modify: `graxia/services/revenue_os_api/routers/checkout.py:51-63` (guard)
- Modify: `graxia/packages/revenue_os/services/billing_service.py` (guards)
- Modify: `graxia/packages/revenue_os/services/refund_executor.py:26` (guard)
- Modify: `graxia/services/revenue_os_api/routers/system.py` (admin endpoints)
- Test: `graxia/packages/revenue_os/tests/test_kill_switch.py` (new)

**Interfaces:**
- Consumes: `require_admin_api_key` (dependencies.py), `UnifiedTelegramNotifier` module-level `notifier` (graxia/services/telegram_notifier.py:217)
- Produces: `MoneyKillSwitch(path=None)` with `is_triggered()/get_status()/trigger(reason)/reset(reason)`; `ensure_money_ops_allowed()` raising `MoneyKillSwitchError`; `GET /api/system/kill-switch`, `POST /api/system/kill-switch/trigger`, `POST /api/system/kill-switch/reset` (admin auth); state file `data/revenue_os_kill_switch.json` (override `REVENUE_OS_KILL_SWITCH_FILE`).

- [ ] **Step 1: Write the failing tests**

Create `test_kill_switch.py`:

```python
"""Money kill switch tests (P0 T6) — fail-closed on corrupt state."""
import json

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from graxia.services.revenue_os_api.routers.checkout import (
    create_checkout_session,
    stripe_checkout,
)
from ..enums import ProductStatus, ProductType
from ..models import Product
from ..schemas import CheckoutSessionCreate
from ..services.kill_switch import (
    MoneyKillSwitch,
    MoneyKillSwitchError,
    ensure_money_ops_allowed,
)


class _FakeSession:
    def __init__(self, session_id="cs_test_123", url="https://checkout.stripe.com/c/pay/cs_test_123"):
        self.id = session_id
        self.url = url


@pytest.fixture
def kill_switch_path(tmp_path):
    return tmp_path / "kill_switch.json"


def test_not_triggered_when_file_missing(kill_switch_path):
    assert MoneyKillSwitch(str(kill_switch_path)).is_triggered() is False


def test_trigger_then_reset(kill_switch_path):
    switch = MoneyKillSwitch(str(kill_switch_path))
    switch.trigger("test reason")
    assert switch.is_triggered() is True
    assert switch.get_status()["reason"] == "test reason"
    switch.reset("all clear")
    assert switch.is_triggered() is False


def test_corrupt_file_fail_closed(kill_switch_path):
    kill_switch_path.write_text("{not valid json", encoding="utf-8")
    assert MoneyKillSwitch(str(kill_switch_path)).is_triggered() is True


def test_ensure_money_ops_allowed_raises_when_triggered(kill_switch_path):
    switch = MoneyKillSwitch(str(kill_switch_path))
    switch.trigger("emergency")
    with pytest.raises(MoneyKillSwitchError):
        ensure_money_ops_allowed(switch)


@pytest.mark.asyncio
async def test_checkout_blocked_when_kill_switch_active(
    db_session: AsyncSession, monkeypatch, kill_switch_path
):
    product = Product(
        name="Test Product",
        slug="test-product-killswitch",
        type=ProductType.LOW_TICKET,
        price_cents=9900,
        currency="THB",
        status=ProductStatus.PUBLISHED,
    )
    db_session.add(product)
    await db_session.flush()

    # Guard constructs MoneyKillSwitch() from env var — exercise the real path
    monkeypatch.setenv("REVENUE_OS_KILL_SWITCH_FILE", str(kill_switch_path))
    MoneyKillSwitch(str(kill_switch_path)).trigger("test")

    payload = CheckoutSessionCreate(
        product_id=product.id,
        customer_email="buyer@example.com",
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
    )
    with pytest.raises(HTTPException) as exc:
        await create_checkout_session(payload, db_session)
    assert exc.value.status_code == 503
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest graxia/packages/revenue_os/tests/test_kill_switch.py -v`
Expected: FAIL — `ModuleNotFoundError: ... kill_switch`.

- [ ] **Step 3: Implement**

Create `kill_switch.py`:

```python
"""Money kill switch (P0 T6, IMF best practice).

JSON-file backed (quant_os pattern). Fail-closed: corrupt/unreadable state
file blocks ALL money operations. Missing file = normal operation.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class MoneyKillSwitchError(RuntimeError):
    """Raised when a money operation is attempted while the kill switch is active."""


class MoneyKillSwitch:
    def __init__(self, path: Optional[str] = None) -> None:
        self.path = Path(
            path or os.getenv("REVENUE_OS_KILL_SWITCH_FILE", "data/revenue_os_kill_switch.json")
        )

    def is_triggered(self) -> bool:
        if not self.path.exists():
            return False
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
            return bool(state.get("triggered", False))
        except (json.JSONDecodeError, OSError):
            return True  # fail-closed

    def get_status(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"triggered": False, "reason": None, "triggered_at": None}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"triggered": True, "reason": "corrupt state file (fail-closed)", "triggered_at": None}

    def trigger(self, reason: str) -> dict[str, Any]:
        state = {
            "triggered": True,
            "reason": reason,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return state

    def reset(self, reason: str) -> dict[str, Any]:
        state = {
            "triggered": False,
            "reason": reason,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return state


def ensure_money_ops_allowed(switch: Optional[MoneyKillSwitch] = None) -> None:
    """Fail-closed guard for money operations. Raises MoneyKillSwitchError when active."""
    if (switch or MoneyKillSwitch()).is_triggered():
        raise MoneyKillSwitchError("Money operations disabled (kill switch active)")
```

`checkout.py` — add import + guard at top of `create_checkout_session` (after `product = await db.get(...)` is NOT enough — guard FIRST, before any Stripe call; put it as the first statement of the handler):

```python
from ....packages.revenue_os.services.kill_switch import (
    MoneyKillSwitch,
    MoneyKillSwitchError,
    ensure_money_ops_allowed,
)
```

```python
    try:
        ensure_money_ops_allowed()
    except MoneyKillSwitchError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
```

`billing_service.py` — add import + guard at top of `create_subscription` and `cancel_subscription`:

```python
from ..services.kill_switch import ensure_money_ops_allowed
```

```python
        ensure_money_ops_allowed()
```

`refund_executor.py` — add import + guard at top of `process_pending_refunds`:

```python
from ..services.kill_switch import ensure_money_ops_allowed
```

```python
        ensure_money_ops_allowed()
```

`system.py` — add admin endpoints (keep existing public readiness/metrics):

```python
from pydantic import BaseModel, Field
from ....packages.revenue_os.services.kill_switch import MoneyKillSwitch
from ..dependencies import require_admin_api_key


class KillSwitchRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


@router.get("/kill-switch", dependencies=[Depends(require_admin_api_key)])
async def get_kill_switch_status() -> dict:
    return MoneyKillSwitch().get_status()


@router.post("/kill-switch/trigger", dependencies=[Depends(require_admin_api_key)])
async def trigger_kill_switch(payload: KillSwitchRequest) -> dict:
    state = MoneyKillSwitch().trigger(payload.reason)
    try:
        from graxia.services.telegram_notifier import notifier
        await notifier.notify_kill_switch_triggered(payload.reason)
    except Exception:
        logger.exception("kill switch telegram notification failed (non-blocking)")
    return state


@router.post("/kill-switch/reset", dependencies=[Depends(require_admin_api_key)])
async def reset_kill_switch(payload: KillSwitchRequest) -> dict:
    return MoneyKillSwitch().reset(payload.reason)
```

Check `system.py` imports `Depends` and `APIRouter` already; add `logger = logging.getLogger(__name__)` if missing.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_kill_switch.py -v`
Expected: PASS (6 tests).

Then run the full revenue_os suite to catch regressions:

Run: `pytest graxia/packages/revenue_os/tests/ -q`
Expected: no new failures (existing suite baseline).

- [ ] **Step 5: Commit**

```bash
git add graxia/packages/revenue_os/services/kill_switch.py graxia/services/revenue_os_api/routers/checkout.py graxia/packages/revenue_os/services/billing_service.py graxia/packages/revenue_os/services/refund_executor.py graxia/services/revenue_os_api/routers/system.py graxia/packages/revenue_os/tests/test_kill_switch.py
git commit -m "feat(revenue-os): money kill switch — fail-closed guard on all money paths"
```

---

### Task 8: P0 E2E test suite + exit gate

**Files:**
- Create: `graxia/packages/revenue_os/tests/test_e2e_subscription_flow.py`
- Docs: `docs/runbooks/revenue-os-p0-exit-gate.md` (new)

**Interfaces:**
- Consumes: everything from Tasks 1-3, 7 (checkout subscription mode, webhook mirror, portal, kill switch)
- Produces: full-flow test proving checkout → webhook → subscription active → portal → kill-switch block; manual exit-gate checklist.

- [ ] **Step 1: Write the E2E test**

Create `test_e2e_subscription_flow.py`:

```python
"""P0 E2E: subscription checkout → webhook → mirror row → portal → kill switch."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from graxia.services.revenue_os_api.routers.checkout import (
    create_checkout_session,
    stripe_checkout,
    stripe_webhook,
)
from ..enums import ProductStatus, ProductType
from ..models import Product, Subscription
from ..schemas import CheckoutSessionCreate
from ..services.billing_service import BillingService, stripe_billing_portal


class _FakeSession:
    def __init__(self, session_id="cs_test_e2e", url="https://checkout.stripe.com/c/pay/cs_test_e2e"):
        self.id = session_id
        self.url = url


class _FakePortalSession:
    url = "https://billing.stripe.com/session/e2e"


@pytest.mark.asyncio
async def test_full_subscription_flow(db_session: AsyncSession, monkeypatch):
    # 1. Product (Starter tier)
    product = Product(
        name="Revenue OS Starter",
        slug="revenue-os-starter-e2e",
        type=ProductType.CORE,
        price_cents=49900,
        currency="THB",
        status=ProductStatus.PUBLISHED,
    )
    db_session.add(product)
    await db_session.flush()

    # 2. Checkout session (subscription mode)
    captured = {}
    monkeypatch.setattr(stripe_checkout, "create", lambda **kwargs: (captured.update(kwargs) or _FakeSession()))
    payload = CheckoutSessionCreate(
        product_id=product.id,
        customer_email="buyer@example.com",
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
        mode="subscription",
    )
    resp = await create_checkout_session(payload, db_session)
    assert resp.session_id == "cs_test_e2e"
    assert captured["mode"] == "subscription"

    # 3. Webhook: checkout.session.completed → order PAID (existing path)
    checkout_event = {
        "id": "evt_checkout_e2e",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_test_e2e",
            "customer_email": "buyer@example.com",
            "metadata": {"product_id": str(product.id), "mode": "subscription"},
            "payment_intent": "pi_test_e2e",
            "amount_total": 49900,
            "currency": "thb",
        }},
    }
    # 4. Webhook: customer.subscription.created → mirror row
    sub_event = {
        "id": "evt_sub_e2e",
        "type": "customer.subscription.created",
        "data": {"object": {
            "id": "sub_test_e2e",
            "metadata": {"plan": "starter", "customer_email": "buyer@example.com"},
            "items": {"data": [{"price": {"unit_amount": 49900}}]},
        }},
    }
    # Call handlers directly (HMAC is covered by require_stripe_hmac tests)
    from ..services.webhook_processor import WebhookProcessor
    order = await WebhookProcessor.process_stripe_checkout_completed(checkout_event["data"]["object"], db_session)
    assert order is not None
    sub = await BillingService.handle_subscription_created(db_session, sub_event["data"]["object"])
    assert sub is not None and sub.status == "active"

    # 5. Billing portal session
    from ..models import Customer
    customer = Customer(email="buyer@example.com", name="Buyer", stripe_customer_id="cus_test_e2e")
    db_session.add(customer)
    await db_session.flush()
    monkeypatch.setattr(stripe_billing_portal, "create", lambda **kwargs: _FakePortalSession())
    url = await BillingService.create_portal_session(db_session, "buyer@example.com")
    assert url == "https://billing.stripe.com/session/e2e"

    # 6. Kill switch blocks new checkout
    from fastapi import HTTPException
    from ..services.kill_switch import MoneyKillSwitch
    import tempfile, os
    ks_path = os.path.join(tempfile.mkdtemp(), "ks.json")
    monkeypatch.setenv("REVENUE_OS_KILL_SWITCH_FILE", ks_path)
    MoneyKillSwitch(ks_path).trigger("e2e test")
    with pytest.raises(HTTPException) as exc:
        await create_checkout_session(payload, db_session)
    assert exc.value.status_code == 503
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest graxia/packages/revenue_os/tests/test_e2e_subscription_flow.py -v`
Expected: PASS. If `WebhookProcessor.process_stripe_checkout_completed` signature differs (check `webhook_processor.py`), adapt the call to the real signature — the test must exercise the real handler.

- [ ] **Step 3: Write the exit-gate checklist**

Create `docs/runbooks/revenue-os-p0-exit-gate.md`:

```markdown
# Revenue OS P0 — Exit Gate Checklist

All items must pass before P1 (Launch + warm leads) starts.

## Automated (CI)
- [ ] `pytest graxia/packages/revenue_os/tests/ -q` — no new failures
- [ ] `test_e2e_subscription_flow.py` — full flow green

## Manual (Stripe test mode — founder)
- [ ] Checkout session created for Starter (฿499) via API
- [ ] Complete payment with test card `4242 4242 4242 4242`
- [ ] Webhook `checkout.session.completed` received → order PAID
- [ ] Webhook `customer.subscription.created` received → Subscription row active
- [ ] Billing portal session returns a working URL
- [ ] Kill switch trigger → new checkout returns 503; reset → works again
- [ ] Stripe dashboard test events all return 200

## Deploy
- [ ] `https://graxia-revenue-os.onrender.com/api/system/readiness` → 200
- [ ] Stripe webhook endpoint registered with production URL
```

- [ ] **Step 4: Commit**

```bash
git add graxia/packages/revenue_os/tests/test_e2e_subscription_flow.py docs/runbooks/revenue-os-p0-exit-gate.md
git commit -m "test(revenue-os): P0 E2E subscription flow + exit gate checklist"
```

---

### Task 9: LeadStatus extension (P1/G4 bridge)

**Files:**
- Modify: `graxia/packages/revenue_os/enums.py:43-51` (LeadStatus)
- Create: `graxia/migrations/versions/0011_lead_status_demo_trial_paid.sql`
- Test: `graxia/packages/revenue_os/tests/test_lead_status_extension.py` (new)

**Interfaces:**
- Consumes: `Lead` model (`status: Mapped[LeadStatus] = SAEnum(LeadStatus)` — models.py:277)
- Produces: `LeadStatus.DEMO/TRIAL/PAID`; PG enum `leadstatus` extended (migration); leads can be created with `status=paid`.

- [ ] **Step 1: Write the failing tests**

Create `test_lead_status_extension.py`:

```python
"""LeadStatus extension (spec G4): demo/trial/paid for lead→paid KPI."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import LeadStatus
from ..models import Lead


def test_lead_status_has_new_states():
    assert LeadStatus.DEMO == "demo"
    assert LeadStatus.TRIAL == "trial"
    assert LeadStatus.PAID == "paid"


@pytest.mark.asyncio
async def test_lead_accepts_paid_status(db_session: AsyncSession):
    lead = Lead(
        email="lead@example.com",
        name="Test Lead",
        source="organic_search",
        score=50,
        status=LeadStatus.PAID,
    )
    db_session.add(lead)
    await db_session.flush()
    assert lead.status == LeadStatus.PAID
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest graxia/packages/revenue_os/tests/test_lead_status_extension.py -v`
Expected: FAIL — `AttributeError: DEMO` (enum lacks the values).

- [ ] **Step 3: Implement**

`enums.py` — extend LeadStatus:

```python
class LeadStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    RESPONDED = "responded"
    QUALIFIED = "qualified"
    PROPOSAL_SENT = "proposal_sent"
    NEGOTIATING = "negotiating"
    CONVERTED = "converted"
    LOST = "lost"
    DEMO = "demo"
    TRIAL = "trial"
    PAID = "paid"
```

Create `graxia/migrations/versions/0011_lead_status_demo_trial_paid.sql`:

```sql
-- Extend LeadStatus enum with demo/trial/paid (spec G4 — lead→paid KPI)
-- PostgreSQL 12+ supports ADD VALUE IF NOT EXISTS.
ALTER TYPE leadstatus ADD VALUE IF NOT EXISTS 'demo';
ALTER TYPE leadstatus ADD VALUE IF NOT EXISTS 'trial';
ALTER TYPE leadstatus ADD VALUE IF NOT EXISTS 'paid';
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_lead_status_extension.py -v`
Expected: PASS.

Note: if the test DB was created before this migration, `create_all` in conftest may not add enum values to an existing `leadstatus` type — if the enum test fails with `invalid input value for enum leadstatus`, run the migration SQL against the test DB once:

Run: `psql "$env:DATABASE_URL" -c "ALTER TYPE leadstatus ADD VALUE IF NOT EXISTS 'demo'; ALTER TYPE leadstatus ADD VALUE IF NOT EXISTS 'trial'; ALTER TYPE leadstatus ADD VALUE IF NOT EXISTS 'paid';"` (or via Supabase SQL editor for the real DB).

- [ ] **Step 5: Commit**

```bash
git add graxia/packages/revenue_os/enums.py graxia/migrations/versions/0011_lead_status_demo_trial_paid.sql graxia/packages/revenue_os/tests/test_lead_status_extension.py
git commit -m "feat(revenue-os): LeadStatus demo/trial/paid states + migration (P1 G4)"
```

---

## Self-Review Notes

- **Spec coverage:** T1→Task 1, T2→Task 3, T3→Task 4, T4→Task 5, T5→Task 6, T6→Task 7, T7→Tasks 2+8, G4→Task 9. All P0 items mapped.
- **Deferred (per spec):** Sentry real, backup real, alembic full migration, PromptPay — P2/P3.
- **Founder actions outside code:** Stripe Price IDs (Task 4), Render deploy + webhook registration (Task 6), exit-gate manual payment test (Task 8).