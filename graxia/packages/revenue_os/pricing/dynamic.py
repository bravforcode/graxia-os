"""Rule-based dynamic pricing — shares ONE policy-gated price-write path with the
commerce agent (PriceChangeLock prevents lost updates / racing writers)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import PRICE_CHANGE_MIN_INTERVAL_HOURS
from ..core.policy_engine import PolicyEngine
from ..enums import ActionType, AutonomyMode, OrderStatus, ProductStatus
from ..models import AuditLog, Order, PriceChangeLock, Product

STALE_DAYS = 14
HOT_WINDOW_DAYS = 3
HOT_SALES = 3


class DynamicPricingEngine:
    """Rule signals -> delta% proposal. apply() is the shared write path."""

    @staticmethod
    async def propose(db: AsyncSession, product: Product) -> Optional[float]:
        """Return a delta% (positive=raise, negative=cut) or None if no signal."""
        now = datetime.utcnow()
        hot_cutoff = now - timedelta(days=HOT_WINDOW_DAYS)
        sales_3d = await db.scalar(
            select(Order.id).where(
                Order.product_id == product.id,
                Order.status == OrderStatus.PAID,
                Order.purchased_at >= hot_cutoff,
            ).limit(HOT_SALES + 1)
        )
        recent_sales = 0
        if sales_3d is not None:
            # count via second query for accuracy
            recent_sales = await db.scalar(
                select(Order.id).where(
                    Order.product_id == product.id,
                    Order.status == OrderStatus.PAID,
                    Order.purchased_at >= hot_cutoff,
                ).count()
            ) or 0
        if recent_sales >= HOT_SALES:
            return 5.0  # high demand -> +5%
        if product.created_at is not None and product.created_at.replace(tzinfo=None) < now - timedelta(days=STALE_DAYS):
            return -10.0  # stale -> -10%
        return None

    @staticmethod
    async def apply(db: AsyncSession, product: Product, delta_percent: float, shadow: bool = False) -> bool:
        """SHARED price-write path. Returns True if the change was applied (or logged in shadow)."""
        lock = await db.get(PriceChangeLock, product.id)
        if lock is not None:
            last = lock.last_change_at
            if last is not None and last.replace(tzinfo=None) > datetime.utcnow() - timedelta(hours=PRICE_CHANGE_MIN_INTERVAL_HOURS):
                return False  # rate-limited
        cut_cents = int((product.price_cents or 0) * abs(delta_percent) / 100)
        decision = await PolicyEngine.check(
            db, ActionType.PRICE_CHANGE,
            {
                "value": abs(delta_percent),
                "value_cents": cut_cents,
                "product_id": str(product.id),
                "currency": product.currency,
            },
        )
        if not decision.allow:
            return False
        if shadow:
            db.add(AuditLog(event_type="agent.price_change.shadow",
                            message=f"SHADOW: dynamic price {product.name} {delta_percent:+.1f}%",
                            metadata_={"product_id": str(product.id), "percent": delta_percent}))
            await db.flush()
            return True
        product.price_cents = max(0, (product.price_cents or 0) + int((product.price_cents or 0) * delta_percent / 100))
        if lock is None:
            lock = PriceChangeLock(product_id=product.id, last_delta_percent=delta_percent)
            db.add(lock)
        else:
            lock.last_delta_percent = delta_percent
            lock.last_change_at = datetime.utcnow()
        db.add(AuditLog(event_type="agent.price_change.dynamic",
                        message=f"Dynamic price {product.name} {delta_percent:+.1f}%",
                        metadata_={"product_id": str(product.id), "percent": delta_percent}))
        await db.flush()
        return True

    @classmethod
    async def run_cycle(cls, db: AsyncSession, shadow: bool = False) -> dict:
        applied, skipped = 0, 0
        result = await db.execute(select(Product).where(Product.status == ProductStatus.PUBLISHED))
        for product in list(result.scalars().all()):
            delta = await cls.propose(db, product)
            if delta is None:
                continue
            if await cls.apply(db, product, delta, shadow=shadow):
                applied += 1
            else:
                skipped += 1
        await db.flush()
        return {"applied": applied, "skipped": skipped}
