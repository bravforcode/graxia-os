"""Customer identity + delivery SLA + fraud signal tests."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..affiliate.service import create_affiliate, fraud_signals, record_attribution
from ..celery.tasks.delivery_sla import delivery_sla_with_db
from ..core.policy_engine import PolicyEngine
from ..enums import DeliveryStatus, IncidentSeverity, ProductStatus
from ..models import AttributionEvent, DeliveryEvent, IncidentEvent, Order, Product
from ..services.customer_identity import customer_profile


_slug_seq = {"n": 0}


async def _product(db_session: AsyncSession) -> Product:
    _slug_seq["n"] += 1
    product = Product(name="Test Product", slug=f"test-product-{_slug_seq['n']}",
                      price_cents=9900, status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    return product


async def _order(db_session: AsyncSession, platform="shopee", oid="o1",
                 email="buyer@example.com", amount=9900, purchased_at=None,
                 status=None):
    from ..services.order_service import OrderService
    order = await OrderService.create_order(
        db_session, platform=platform, platform_order_id=f"{oid}-{id(db_session)}",
        customer_email=email, product_id=(await _product(db_session)).id, amount_cents=amount,
    )
    if status is not None:
        order.status = status
    if purchased_at is not None:
        order.purchased_at = purchased_at
    if status is not None or purchased_at is not None:
        await db_session.commit()
    return order


# ── B9: cross-platform customer identity ─────────────────────────────────────

@pytest.mark.asyncio
async def test_customer_profile_unifies_channels(db_session: AsyncSession):
    email = "alice@example.com"
    await _order(db_session, platform="shopee", oid="a", email=email)
    await _order(db_session, platform="shopee", oid="b", email=email)
    await _order(db_session, platform="amazon", oid="c", email=email)
    await _order(db_session, platform="lazada", oid="d", email="other@example.com")

    profile = await customer_profile(db_session, email)
    assert profile is not None
    assert profile["total_orders"] == 3
    assert profile["total_spend_cents"] == 3 * 9900
    platforms = {p["platform"]: p for p in profile["platforms"]}
    assert platforms["shopee"]["orders"] == 2
    assert platforms["amazon"]["orders"] == 1
    assert profile["first_purchase_at"] is not None


@pytest.mark.asyncio
async def test_customer_profile_unknown_email(db_session: AsyncSession):
    assert await customer_profile(db_session, "nobody@example.com") is None


# ── B10: delivery SLA ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stale_paid_order_flags_incident_once(db_session: AsyncSession):
    old = datetime.now(timezone.utc) - timedelta(days=10)
    from ..enums import OrderStatus
    order = await _order(db_session, purchased_at=old, status=OrderStatus.PAID)
    await db_session.refresh(order)
    first = await delivery_sla_with_db(db_session)
    assert first["checked"] == 1 and first["flagged"] == 1
    incident = await db_session.scalar(select(IncidentEvent))
    assert incident.severity == IncidentSeverity.MEDIUM
    assert incident.affected_order_id == order.id
    second = await delivery_sla_with_db(db_session)
    assert second["flagged"] == 0  # once per order
    assert (await db_session.execute(select(IncidentEvent))).scalars().all().__len__() == 1


@pytest.mark.asyncio
async def test_delivered_order_not_flagged(db_session: AsyncSession):
    from ..enums import OrderStatus
    order = await _order(db_session, status=OrderStatus.PAID,
                         purchased_at=datetime.now(timezone.utc) - timedelta(days=10))
    db_session.add(DeliveryEvent(order_id=order.id, event_type="delivery",
                                 status=DeliveryStatus.DELIVERED))
    await db_session.commit()
    result = await delivery_sla_with_db(db_session)
    assert result["flagged"] == 0


@pytest.mark.asyncio
async def test_fresh_order_not_flagged(db_session: AsyncSession):
    await _order(db_session, purchased_at=datetime.now(timezone.utc))
    result = await delivery_sla_with_db(db_session)
    assert result == {"skipped": False, "checked": 0, "flagged": 0}


# ── B12: affiliate fraud signals ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fraud_signal_self_referral(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    aff = await create_affiliate(db_session, "alice@example.com", 10.0)
    product = await _product(db_session)
    order = await _order(db_session, email="alice@example.com")  # own order!
    db_session.add(AttributionEvent(event_id="t1", event_type="click",
                                    source=aff.code, order_id=order.id))
    await db_session.commit()
    assert await record_attribution(db_session, aff.code, order.id) is True
    signals = await fraud_signals(db_session)
    assert any(s["type"] == "self_referral" for s in signals)


@pytest.mark.asyncio
async def test_fraud_signal_stacking_multiple_sources(db_session: AsyncSession):
    order = await _order(db_session)
    db_session.add_all([
        AttributionEvent(event_id="s1", event_type="click", source="alice", order_id=order.id),
        AttributionEvent(event_id="s2", event_type="click", source="bob", order_id=order.id),
    ])
    await db_session.commit()
    signals = await fraud_signals(db_session)
    stacking = [s for s in signals if s["type"] == "stacking"]
    assert len(stacking) == 1
    assert stacking[0]["distinct_sources"] == 2


@pytest.mark.asyncio
async def test_no_signals_clean(db_session: AsyncSession):
    await _order(db_session)
    assert await fraud_signals(db_session) == []
