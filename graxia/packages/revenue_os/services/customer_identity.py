"""Cross-platform customer identity — unify buyers across channels by email."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Order


async def customer_profile(db: AsyncSession, email: str) -> Optional[dict]:
    """All orders for an email across platforms: totals + per-platform split."""
    orders = (await db.execute(
        select(Order).where(Order.customer_email == email)
        .order_by(Order.purchased_at))).scalars().all()
    if not orders:
        return None
    platforms: dict[str, dict] = {}
    for o in orders:
        p = platforms.setdefault(o.platform, {"orders": 0, "spend_cents": 0})
        p["orders"] += 1
        p["spend_cents"] += o.amount_cents
    return {
        "email": email,
        "total_orders": len(orders),
        "total_spend_cents": sum(o.amount_cents for o in orders),
        "platforms": [{"platform": k, **v} for k, v in sorted(platforms.items())],
        "first_purchase_at": orders[0].purchased_at,
        "last_purchase_at": orders[-1].purchased_at,
    }
