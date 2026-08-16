"""Refund automation tests — RETURNED reconcile books Refund + ledger entry."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels.lazada import reconcile_lazada
from ..channels.shopee import reconcile_shopee
from ..enums import ChannelType, LedgerEntryType, OrderStatus, ProductStatus, RefundStatus
from ..finance.refund_sync import ensure_refund_record
from ..models import LedgerEntry, Order, Product, Refund


async def _order(db_session: AsyncSession, platform="shopee", oid="o1") -> Order:
    product = Product(name="Test Product", slug="test-product",
                      price_cents=9900, status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    from ..services.order_service import OrderService
    return await OrderService.create_order(
        db_session, platform=platform, platform_order_id=oid,
        customer_email="c@example.com", product_id=product.id, amount_cents=9900,
    )


@pytest.mark.asyncio
async def test_reconcile_returned_books_refund_and_ledger(db_session: AsyncSession):
    order = await _order(db_session)
    result = await reconcile_shopee(db_session, {"o1": "RETURNED"})
    assert result["updated"] == 1
    await db_session.refresh(order)
    assert order.status == OrderStatus.REFUNDED
    refund = await db_session.scalar(select(Refund).where(Refund.order_id == order.id))
    assert refund is not None
    assert refund.status == RefundStatus.PROCESSED  # marketplace handled the money
    assert refund.platform_refund_id == "shopee-o1"
    entry = await db_session.scalar(select(LedgerEntry).where(
        LedgerEntry.order_id == order.id, LedgerEntry.entry_type == LedgerEntryType.REFUND))
    assert entry is not None
    assert entry.amount_cents == -9900  # HR-16: refund books a ledger entry


@pytest.mark.asyncio
async def test_reconcile_refund_is_idempotent(db_session: AsyncSession):
    order = await _order(db_session)
    await reconcile_shopee(db_session, {"o1": "RETURNED"})
    # second reconcile: local REFUNDED wins -> skip, no duplicate refund row
    again = await reconcile_shopee(db_session, {"o1": "COMPLETED"})
    assert again["updated"] == 0 and again["skipped"] == 1
    refunds = (await db_session.execute(select(Refund))).scalars().all()
    assert len(refunds) == 1
    entries = (await db_session.execute(select(LedgerEntry).where(
        LedgerEntry.entry_type == LedgerEntryType.REFUND))).scalars().all()
    assert len(entries) == 1


@pytest.mark.asyncio
async def test_ensure_refund_record_direct_idempotent(db_session: AsyncSession):
    order = await _order(db_session)
    assert await ensure_refund_record(db_session, order) is True
    assert await ensure_refund_record(db_session, order) is False  # once only
    await db_session.commit()
    assert (await db_session.execute(select(Refund))).scalars().all().__len__() == 1


@pytest.mark.asyncio
async def test_lazada_returned_books_refund(db_session: AsyncSession):
    order = await _order(db_session, platform="lazada")
    result = await reconcile_lazada(db_session, {"o1": "returned"})
    assert result["updated"] == 1
    refund = await db_session.scalar(select(Refund).where(Refund.order_id == order.id))
    assert refund is not None and refund.platform == "lazada"
