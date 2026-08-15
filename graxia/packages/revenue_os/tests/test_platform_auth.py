import hashlib
import hmac
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels.platform_auth import PlatformSignedClient, ShopeeSigner, LazadaSigner
from ..core.policy_engine import PolicyEngine
from ..enums import ActionType, ChannelType
from ..models import Affiliate, ChannelInventory


# ── Known-vector signature tests (per platform docs format) ────────────────

def test_shopee_signer_known_vector():
    # Shopee: sign = SHA256(partner_key + url_query_sorted)
    signer = ShopeeSigner(partner_id=123, partner_key="testkey")
    query = "shop_id=111&timestamp=1712345678&version=2"
    sig = signer.sign("GET", "/api/v2/order/get_order_list", query)
    expected = hashlib.sha256(("testkey" + query).encode()).hexdigest()
    assert sig == expected


def test_lazada_signer_known_vector():
    # Lazada: sign = HMAC-SHA256(app_secret, sorted "keyvalue" concatenation)
    signer = LazadaSigner(app_key="12345", app_secret="secret")
    params = {"app_key": "12345", "timestamp": "1712345678", "method": "orders/get"}
    sig = signer.sign("GET", "/rest/orders/get", params)
    base = "app_key12345methodorders/gettimestamp1712345678"
    expected = hmac.new(b"secret", base.encode(), hashlib.sha256).hexdigest().upper()
    assert sig == expected


# ── FX-aware caps ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fx_cap_converts_non_thb_order(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    # REFUND ABSOLUTE cap = 1_500_00 THB cents. MYR order 100_00 MYR with fx 0.12 -> THB equiv 833_33 -> under cap
    decision = await PolicyEngine.check(
        db_session, ActionType.REFUND,
        {"value": 100.0, "value_cents": 100_00, "currency": "MYR", "fx_rate": 0.12},
    )
    assert decision.allow is True
    # Same MYR order at 20_000_00 MYR -> THB equiv 166_666_66 -> over cap
    decision2 = await PolicyEngine.check(
        db_session, ActionType.REFUND,
        {"value": 100.0, "value_cents": 20_000_00, "currency": "MYR", "fx_rate": 0.12},
    )
    assert decision2.allow is False


@pytest.mark.asyncio
async def test_fx_missing_rate_uses_percent_only(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    # No fx_rate -> ABSOLUTE rule skipped, PERCENT 100% allowed
    decision = await PolicyEngine.check(
        db_session, ActionType.REFUND,
        {"value": 100.0, "value_cents": 999_000_00, "currency": "VND"},
    )
    assert decision.allow is True  # PERCENT-only path (ABSOLUTE skipped without fx_rate)


@pytest.mark.asyncio
async def test_affiliate_rules_seeded(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    ok = await PolicyEngine.check(db_session, ActionType.AFFILIATE, {"value": 15.0, "value_cents": 5_000_00, "currency": "THB"})
    assert ok.allow is True
    denied = await PolicyEngine.check(db_session, ActionType.AFFILIATE, {"value": 25.0, "value_cents": 5_000_00, "currency": "THB"})
    assert denied.allow is False  # > 20% cap


# ── Models ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_affiliate_model_unique_code(db_session: AsyncSession):
    db_session.add(Affiliate(code="alice", email="alice@example.com", commission_percent=10.0))
    await db_session.commit()
    db_session.add(Affiliate(code="alice", email="bob@example.com", commission_percent=10.0))
    with pytest.raises(Exception):
        await db_session.commit()


@pytest.mark.asyncio
async def test_channel_inventory_composite_pk(db_session: AsyncSession, sample_product_data):
    from ..models import Product, ProductStatus
    product = Product(name=sample_product_data["name"], slug=sample_product_data["slug"],
                      price_cents=sample_product_data["price_cents"], status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    inv = ChannelInventory(channel=ChannelType.SHOPEE, product_id=product.id, channel_stock=10, stock_buffer=3)
    db_session.add(inv)
    await db_session.commit()
    got = await db_session.get(ChannelInventory, (ChannelType.SHOPEE, product.id))
    assert got.channel_stock == 10
