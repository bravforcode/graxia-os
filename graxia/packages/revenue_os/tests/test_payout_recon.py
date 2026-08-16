"""Payout reconciliation tests — settlement -> ledger entries, idempotency."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..finance.payout_recon import reconcile_payouts
from ..enums import LedgerEntryType, ProductStatus
from ..models import LedgerEntry, Order, Product


async def _order(db_session: AsyncSession, platform="shopee", oid="o1", amount=9900) -> Order:
    product = Product(name="Test Product", slug="test-product",
                      price_cents=9900, status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    from ..services.order_service import OrderService
    return await OrderService.create_order(
        db_session, platform=platform, platform_order_id=oid,
        customer_email="c@example.com", product_id=product.id, amount_cents=amount,
    )


@pytest.mark.asyncio
async def test_reconcile_books_fee_and_payout(db_session: AsyncSession):
    order = await _order(db_session)
    result = await reconcile_payouts(db_session, "shopee", [{
        "order_id": "o1", "payout_cents": 9207, "fee_cents": 693,
        "currency": "MYR", "ref": "st-1",
    }])
    assert result == {"matched": 1, "created": 1, "skipped": 0}
    entries = (await db_session.execute(
        select(LedgerEntry).where(LedgerEntry.order_id == order.id)
        .order_by(LedgerEntry.entry_type))).scalars().all()
    recon = [e for e in entries if e.entry_type in (LedgerEntryType.FEE, LedgerEntryType.PAYOUT)]
    assert len(recon) == 2  # order create already booked a CHARGE entry
    fee = next(e for e in recon if e.entry_type == LedgerEntryType.FEE)
    payout = next(e for e in recon if e.entry_type == LedgerEntryType.PAYOUT)
    assert fee.amount_cents == -693 and fee.currency == "MYR"
    assert payout.amount_cents == 9207 and payout.currency == "MYR"
    assert payout.metadata_["settlement_ref"] == "st-1"


@pytest.mark.asyncio
async def test_reconcile_idempotent_per_ref(db_session: AsyncSession):
    order = await _order(db_session)
    settlements = [{"order_id": "o1", "payout_cents": 9207, "fee_cents": 693,
                    "ref": "st-1"}]
    first = await reconcile_payouts(db_session, "shopee", settlements)
    second = await reconcile_payouts(db_session, "shopee", settlements)
    assert first["created"] == 1
    assert second == {"matched": 0, "created": 0, "skipped": 1}
    entries = (await db_session.execute(
        select(LedgerEntry).where(LedgerEntry.order_id == order.id))).scalars().all()
    recon = [e for e in entries if e.entry_type in (LedgerEntryType.FEE, LedgerEntryType.PAYOUT)]
    assert len(recon) == 2  # no duplicates


@pytest.mark.asyncio
async def test_reconcile_skips_unknown_order(db_session: AsyncSession):
    result = await reconcile_payouts(db_session, "shopee", [{
        "order_id": "no-such-order", "payout_cents": 1000, "ref": "st-x",
    }])
    assert result == {"matched": 0, "created": 0, "skipped": 1}
    assert (await db_session.execute(select(LedgerEntry))).scalars().all() == []


@pytest.mark.asyncio
async def test_reconcile_zero_fee_books_payout_only(db_session: AsyncSession):
    order = await _order(db_session, platform="amazon")
    await reconcile_payouts(db_session, "amazon", [{
        "order_id": "o1", "payout_cents": 9900, "ref": "st-0",
    }])
    entries = (await db_session.execute(
        select(LedgerEntry).where(LedgerEntry.order_id == order.id))).scalars().all()
    recon = [e for e in entries if e.entry_type in (LedgerEntryType.FEE, LedgerEntryType.PAYOUT)]
    assert len(recon) == 1
    assert recon[0].entry_type == LedgerEntryType.PAYOUT
    assert recon[0].amount_cents == 9900
