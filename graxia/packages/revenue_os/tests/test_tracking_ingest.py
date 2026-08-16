"""Tracking ingestion tests."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels.tracking_ingest import ingest_tracking
from ..enums import ProductStatus, SupplierStatus
from ..models import AuditLog, Product, SupplierOrder


async def _supplier_order(db_session: AsyncSession) -> SupplierOrder:
    product = Product(name="Test Product", slug="test-product",
                      price_cents=9900, status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    from ..services.order_service import OrderService
    order = await OrderService.create_order(
        db_session, platform="shopify", platform_order_id="trk_o1",
        customer_email="c@example.com", product_id=product.id, amount_cents=9900,
    )
    so = SupplierOrder(order_id=order.id, supplier="printful",
                       idempotency_key="po-trk1", status=SupplierStatus.SUBMITTED)
    db_session.add(so)
    await db_session.commit()
    return so


@pytest.mark.asyncio
async def test_ingest_tracking_updates_and_audits(db_session: AsyncSession):
    so = await _supplier_order(db_session)
    assert await ingest_tracking(db_session, so.id, "TRK-123", carrier="dhl") is True
    await db_session.refresh(so)
    assert so.tracking_number == "TRK-123"
    assert so.raw["carrier"] == "dhl"
    log = await db_session.scalar(select(AuditLog).where(
        AuditLog.event_type == "supplier.tracking.ingested"))
    assert log is not None and log.metadata_["tracking_number"] == "TRK-123"


@pytest.mark.asyncio
async def test_ingest_tracking_unknown_order(db_session: AsyncSession):
    import uuid
    assert await ingest_tracking(db_session, uuid.uuid4(), "TRK-X") is False
