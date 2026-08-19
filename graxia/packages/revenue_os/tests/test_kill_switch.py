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