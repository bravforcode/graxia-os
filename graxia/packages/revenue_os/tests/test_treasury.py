"""Treasury tests — ledger balances + FX conversion."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels.marketplace_sync import fx_refresh
from ..enums import ChannelType, LedgerEntryType, ProductStatus
from ..finance.treasury import treasury_summary
from ..models import ChannelConnection, LedgerEntry, Product


async def _order(db_session: AsyncSession, platform="shopee", oid="t1") -> None:
    product = Product(name="Test Product", slug="test-product",
                      price_cents=9900, status=ProductStatus.PUBLISHED)
    db_session.add(product)
    await db_session.commit()
    from ..services.order_service import OrderService
    order = await OrderService.create_order(
        db_session, platform=platform, platform_order_id=oid,
        customer_email="c@example.com", product_id=product.id, amount_cents=10000,
    )
    # add an extra PAYOUT in MYR against the order
    db_session.add(LedgerEntry(order_id=order.id, entry_type=LedgerEntryType.PAYOUT,
                               amount_cents=9207, currency="MYR",
                               description="shopee payout"))
    await db_session.commit()


@pytest.mark.asyncio
async def test_treasury_converts_with_fx_rates(db_session: AsyncSession):
    from datetime import datetime
    import httpx
    from httpx import MockTransport, Response

    def handler(request):
        return Response(200, json={"rates": {"MYR": 0.12, "VND": 7750.0}})

    transport = MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        await fx_refresh(db_session, http_client=client)
    await _order(db_session)  # 10000 THB CHARGE + 9207 MYR PAYOUT

    summary = await treasury_summary(db_session)
    by_cur = {b["currency"]: b for b in summary["balances"]}
    assert by_cur["THB"]["cents"] == 10000
    assert by_cur["MYR"]["cents"] == 9207
    assert by_cur["MYR"]["thb_equivalent_cents"] == int(9207 / 0.12)  # 76725
    assert summary["total_thb_cents"] == 10000 + int(9207 / 0.12)
    assert summary["missing_rates"] == []


@pytest.mark.asyncio
async def test_treasury_reports_missing_rates(db_session: AsyncSession):
    await _order(db_session)  # no fx rates stored
    summary = await treasury_summary(db_session)
    assert summary["missing_rates"] == ["MYR"]
    assert summary["total_thb_cents"] == 10000  # THB side only


@pytest.mark.asyncio
async def test_treasury_empty_ledger(db_session: AsyncSession):
    summary = await treasury_summary(db_session)
    assert summary == {"balances": [], "total_thb_cents": 0, "missing_rates": []}
