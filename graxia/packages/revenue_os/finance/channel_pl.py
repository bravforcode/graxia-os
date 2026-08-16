"""Channel P&L — per-platform revenue, est fees, est COGS, est margin."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels.marketplace_sync import fee_rate_for
from ..enums import OrderStatus
from ..models import Order, Product

REVENUE_STATUSES = [OrderStatus.PAID, OrderStatus.PROCESSING, OrderStatus.FULFILLED]


async def channel_pl(db: AsyncSession) -> list[dict]:
    """Per-platform P&L: revenue (PAID/PROCESSING/FULFILLED orders), estimated
    platform fee (fee_rate_for), estimated COGS (supplier_cost_cents), margin."""
    rows = (await db.execute(
        select(Order.platform.label("platform"),
               func.count(Order.id).label("orders"),
               func.sum(Order.amount_cents).label("revenue_cents"),
               func.coalesce(func.sum(Product.supplier_cost_cents), 0).label("cost_cents"))
        .join(Product, Product.id == Order.product_id)
        .where(Order.status.in_(REVENUE_STATUSES))
        .group_by(Order.platform)
        .order_by(Order.platform))).all()
    out: list[dict] = []
    for platform, orders, revenue, cost in rows:
        revenue = revenue or 0
        cost = int(cost or 0)
        fee_rate = await fee_rate_for(db, platform)
        fee = int(revenue * fee_rate)
        out.append({
            "platform": platform,
            "orders": orders,
            "revenue_cents": revenue,
            "est_fee_cents": fee,
            "est_cost_cents": cost,
            "est_margin_cents": revenue - fee - cost,
        })
    return out
