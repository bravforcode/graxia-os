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
async def test_submit_order_denied_without_policy(db_session: AsyncSession, sample_product_data, sample_customer_data):
    """Policy fail-closed: no seeded SUPPLIER_PURCHASE rules -> denied, no SupplierOrder."""
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
    assert so is None  # denied
    rows = (await db_session.execute(select(SupplierOrder))).scalars().all()
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_parse_status_webhook_verifies_hmac(monkeypatch):
    import hashlib
    import hmac
    monkeypatch.setenv("SUPPLIER_WEBHOOK_SECRET", "sec")
    payload = b'{"order_id": "x", "status": "shipped", "tracking": "TRK1"}'
    sig = hmac.new(b"sec", payload, hashlib.sha256).hexdigest()
    result = parse_status_webhook(payload, sig)
    assert result["status"] == "shipped"
    assert result["tracking"] == "TRK1"
    bad = parse_status_webhook(payload, "wrong")
    assert bad is None
