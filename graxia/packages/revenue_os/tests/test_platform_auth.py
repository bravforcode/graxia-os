import hashlib
import hmac
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels.platform_auth import PlatformSignedClient, ShopeeSigner, LazadaSigner
from ..core.policy_engine import PolicyEngine
from ..enums import ActionType, ChannelType, RuleType, ValueType
from ..models import Affiliate, ChannelInventory, PolicyRule


# ── Known-vector signature tests (per platform docs format) ────────────────

def test_shopee_signer_known_vector():
    # Shopee v2: sign = SHA256(partner_key + timestamp + path + partner_id + access_token)
    # Expected is a hand-computed literal (NOT derived from the implementation) so a
    # wrong formula breaks the test.
    signer = ShopeeSigner(partner_id=123, partner_key="testkey")
    sig = signer.sign(timestamp=1712345678, path="/api/v2/order/get_order_list", access_token="atoken")
    assert sig == "608b429b8873cc1a7f0cd0aba2e7469ee418858aeb5505060f84ff967098013b"
    # access_token-less variant (auth endpoints): base ends at partner_id
    sig2 = signer.sign(timestamp=1712345678, path="/api/v2/auth/token", access_token="")
    assert sig2 == hashlib.sha256("testkey1712345678/api/v2/auth/token123".encode()).hexdigest()


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
    # REFUND ABSOLUTE cap = 1_500_00 THB cents. fx = foreign units per 1 THB (0.12 MYR/THB).
    # 100 MYR -> THB equiv 100_00/0.12 = 83_333 -> under cap
    decision = await PolicyEngine.check(
        db_session, ActionType.REFUND,
        {"value": 100.0, "value_cents": 100_00, "currency": "MYR", "fx_rate": 0.12},
    )
    assert decision.allow is True
    # 20_000 MYR -> THB equiv 166_666 -> over cap (raw value also over, both paths deny)
    decision2 = await PolicyEngine.check(
        db_session, ActionType.REFUND,
        {"value": 100.0, "value_cents": 20_000_00, "currency": "MYR", "fx_rate": 0.12},
    )
    assert decision2.allow is False
    # Distinguishing case (catches the divide-both-sides no-op): raw 200 MYR is UNDER the
    # 150_000-cent cap, but THB equiv 166_666 is OVER -> must be denied. If conversion is a
    # no-op this wrongly passes.
    decision3 = await PolicyEngine.check(
        db_session, ActionType.REFUND,
        {"value": 100.0, "value_cents": 200_00, "currency": "MYR", "fx_rate": 0.12},
    )
    assert decision3.allow is False


@pytest.mark.asyncio
async def test_fx_missing_rate_uses_percent_only(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    # No fx_rate -> ABSOLUTE rule inapplicable, PERCENT 100% still allowed
    decision = await PolicyEngine.check(
        db_session, ActionType.REFUND,
        {"value": 100.0, "value_cents": 999_000_00, "currency": "VND"},
    )
    assert decision.allow is True  # PERCENT-only path (ABSOLUTE skipped without fx_rate)


@pytest.mark.asyncio
async def test_fx_missing_rate_fails_closed_without_percent_rule(db_session: AsyncSession):
    # Action guarded ONLY by an ABSOLUTE rule: without fx_rate the rule is inapplicable
    # (applies=False -> excluded from both allow and deny computation) -> no applicable
    # rule -> DENIED, never a silent permit.
    db_session.add(PolicyRule(action="test_fx_only", rule_type=RuleType.MAX,
                              value_type=ValueType.ABSOLUTE, value=150_000, description="test"))
    await db_session.commit()
    denied = await PolicyEngine.check(
        db_session, "test_fx_only",
        {"value_cents": 100_00, "currency": "VND"},
    )
    assert denied.allow is False
    # Same rule WITH fx_rate converts and applies: 100_00/0.12 = 83_333 < 150_000 -> allowed
    ok = await PolicyEngine.check(
        db_session, "test_fx_only",
        {"value_cents": 100_00, "currency": "VND", "fx_rate": 0.12},
    )
    assert ok.allow is True


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
