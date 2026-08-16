"""Affiliate program tests — policy-gated creation, attribution, review."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..affiliate.service import AffiliateError, create_affiliate, record_attribution, review_payouts
from ..constants import AFFILIATE_REVIEW_THRESHOLD_CENTS
from ..core.policy_engine import PolicyEngine
from ..enums import AffiliateStatus, IncidentSeverity, ProductStatus
from ..models import Affiliate, AffiliatePayout, AttributionEvent, IncidentEvent, Order, Product


async def _product(db_session: AsyncSession) -> Product:
    product = Product(name="Test Product", slug="test-product",
                      price_cents=9900, status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    return product


async def _order(db_session: AsyncSession, product, amount_cents: int,
                 purchased_at=None) -> Order:
    from ..services.order_service import OrderService
    order = await OrderService.create_order(
        db_session, platform="shopee", platform_order_id=f"o-{amount_cents}",
        customer_email="buyer@example.com", product_id=product.id, amount_cents=amount_cents,
    )
    if purchased_at is not None:
        order.purchased_at = purchased_at
        await db_session.commit()
    return order


async def _touch(db_session: AsyncSession, source: str, order: Order, created_at=None) -> AttributionEvent:
    touch = AttributionEvent(event_id=f"touch-{source}-{order.id}", event_type="click",
                             source=source, order_id=order.id)
    db_session.add(touch)
    if created_at is not None:
        touch.created_at = created_at
    await db_session.commit()
    return touch


# ── create: policy-gated ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_affiliate_rejects_over_cap(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    ok = await create_affiliate(db_session, "alice@example.com", 15.0)
    assert ok.status == AffiliateStatus.ACTIVE
    assert ok.code.startswith("alice")
    with pytest.raises(AffiliateError):  # 25% > 20% cap
        await create_affiliate(db_session, "bob@example.com", 25.0)


@pytest.mark.asyncio
async def test_create_affiliate_fails_closed_without_rules(db_session: AsyncSession):
    # no seeded AFFILIATE rules -> fail-closed denial (never a silent permit)
    with pytest.raises(AffiliateError):
        await create_affiliate(db_session, "carol@example.com", 5.0)


@pytest.mark.asyncio
async def test_create_affiliate_with_explicit_code(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    aff = await create_affiliate(db_session, "dave@example.com", 10.0, code="DAVEKOL")
    assert aff.code == "DAVEKOL"


# ── attribution ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_attribution_creates_payout_with_correct_amount(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    aff = await create_affiliate(db_session, "alice@example.com", 10.0)
    product = await _product(db_session)
    order = await _order(db_session, product, amount_cents=50000)  # 500 THB
    await _touch(db_session, aff.code, order)

    assert await record_attribution(db_session, aff.code, order.id) is True
    payout = await db_session.scalar(select(AffiliatePayout))
    assert payout is not None
    assert payout.amount_cents == 5000  # 10% of 50,000 cents
    assert payout.status == "pending"
    assert payout.needs_review is False  # below threshold


@pytest.mark.asyncio
async def test_attribution_rejects_inactive_affiliate(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    aff = await create_affiliate(db_session, "alice@example.com", 10.0)
    aff.status = AffiliateStatus.PAUSED
    await db_session.commit()
    product = await _product(db_session)
    order = await _order(db_session, product, amount_cents=50000)
    await _touch(db_session, aff.code, order)
    assert await record_attribution(db_session, aff.code, order.id) is False
    assert (await db_session.execute(select(AffiliatePayout))).scalars().all() == []


@pytest.mark.asyncio
async def test_attribution_without_touch_rejected(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    aff = await create_affiliate(db_session, "alice@example.com", 10.0)
    product = await _product(db_session)
    order = await _order(db_session, product, amount_cents=50000)
    assert await record_attribution(db_session, aff.code, order.id) is False  # no touch


@pytest.mark.asyncio
async def test_attribution_outside_window_rejected(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    aff = await create_affiliate(db_session, "alice@example.com", 10.0)
    product = await _product(db_session)
    order = await _order(db_session, product, amount_cents=50000,
                         purchased_at=datetime.now(timezone.utc))
    # first touch 40 days BEFORE the purchase -> outside 30-day window
    await _touch(db_session, aff.code, order,
                 created_at=order.purchased_at - timedelta(days=40))
    assert await record_attribution(db_session, aff.code, order.id) is False
    assert (await db_session.execute(select(AffiliatePayout))).scalars().all() == []


@pytest.mark.asyncio
async def test_attribution_within_window_accepted(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    aff = await create_affiliate(db_session, "alice@example.com", 10.0)
    product = await _product(db_session)
    order = await _order(db_session, product, amount_cents=50000,
                         purchased_at=datetime.now(timezone.utc))
    await _touch(db_session, aff.code, order,
                 created_at=order.purchased_at - timedelta(days=29))
    assert await record_attribution(db_session, aff.code, order.id) is True


@pytest.mark.asyncio
async def test_attribution_no_double_payout(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    aff = await create_affiliate(db_session, "alice@example.com", 10.0)
    product = await _product(db_session)
    order = await _order(db_session, product, amount_cents=50000)
    await _touch(db_session, aff.code, order)
    assert await record_attribution(db_session, aff.code, order.id) is True
    assert await record_attribution(db_session, aff.code, order.id) is False  # idempotent
    rows = (await db_session.execute(select(AffiliatePayout))).scalars().all()
    assert len(rows) == 1


# ── threshold -> review flag + incident ──────────────────────────────────────

@pytest.mark.asyncio
async def test_threshold_flags_review_and_incident(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    aff = await create_affiliate(db_session, "alice@example.com", 10.0)
    product = await _product(db_session)
    # payout = 10% of 50,000,100 cents = 5,000,010 >= 5,000,000 threshold
    order = await _order(db_session, product, amount_cents=50_000_100)
    await _touch(db_session, aff.code, order)

    assert await record_attribution(db_session, aff.code, order.id) is True
    payout = await db_session.scalar(select(AffiliatePayout))
    assert payout.needs_review is True
    incident = await db_session.scalar(select(IncidentEvent))
    assert incident is not None
    assert incident.severity == IncidentSeverity.MEDIUM
    assert incident.source == "affiliate"
    assert incident.affected_order_id == order.id


# ── review sweep ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_review_sweep_flags_threshold_rows_only(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    aff = await create_affiliate(db_session, "alice@example.com", 10.0)
    product = await _product(db_session)
    below = await _order(db_session, product, amount_cents=100_000)  # payout 10k < threshold
    above = await _order(db_session, product, amount_cents=60_000_000)  # payout 6M >= threshold
    await _touch(db_session, aff.code, below)
    await _touch(db_session, aff.code, above)
    assert await record_attribution(db_session, aff.code, below.id) is True
    assert await record_attribution(db_session, aff.code, above.id) is True

    rows = (await db_session.execute(select(AffiliatePayout))).scalars().all()
    for p in rows:  # simulate rows created before review existed
        p.needs_review = False
    await db_session.commit()

    result = await review_payouts(db_session)
    assert result["flagged"] == 1  # only the above-threshold row
    await db_session.refresh(rows[0])
    await db_session.refresh(rows[1])
    flags = sorted(p.needs_review for p in rows)
    assert flags == [False, True]


@pytest.mark.asyncio
async def test_review_sweep_sends_telegram_summary_when_flagged(db_session: AsyncSession, monkeypatch):
    sent = {}

    class _FakeNotifier:
        async def send_message(self, text, **kw):
            sent["text"] = text

    await PolicyEngine.seed_default_rules(db_session)
    aff = await create_affiliate(db_session, "alice@example.com", 10.0)
    product = await _product(db_session)
    order = await _order(db_session, product, amount_cents=60_000_000)
    db_session.add(AffiliatePayout(affiliate_id=aff.id, order_id=order.id,
                                   amount_cents=AFFILIATE_REVIEW_THRESHOLD_CENTS,
                                   status="pending"))
    await db_session.commit()
    result = await review_payouts(db_session, notifier=_FakeNotifier)
    assert result["flagged"] == 1
    assert "1 payout(s) flagged" in sent["text"]
