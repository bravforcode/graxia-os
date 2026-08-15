"""Backtest harness — replay history through the REAL policy engine + agent
signals in-memory. Never writes business state; estimates are labeled."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.policy_engine import PolicyEngine
from ..enums import ActionType, ProductStatus
from ..models import MetricDaily, Product

ELASTICITY = 0.2  # rough unit-elasticity assumption — ESTIMATE only


@dataclass
class SimDecision:
    action: str
    product_id: str
    delta_percent: float
    allowed: bool
    reason: str = ""


async def run_backtest(db: AsyncSession, days: int = 30) -> dict:
    """Simulate agent decisions over the window using real policy. In-memory only."""
    window_start = datetime.utcnow() - timedelta(days=days)
    # fetch products + metrics for the window
    products = (await db.execute(select(Product).where(Product.status == ProductStatus.PUBLISHED))).scalars().all()
    metrics = (await db.execute(
        select(MetricDaily).where(MetricDaily.date >= window_start.date())
    )).scalars().all()
    orders_known = len(metrics)

    decisions: list[SimDecision] = []
    price_sim = {p.id: p.price_cents for p in products}

    for product in products:
        # simulate the stale-product signal from Phase 1 / dynamic pricing
        created = product.created_at.replace(tzinfo=None) if product.created_at else None
        if created is None or created >= datetime.utcnow() - timedelta(days=14):
            continue
        delta = -10.0
        cut_cents = int((price_sim[product.id] or 0) * 0.10)
        decision = await PolicyEngine.check(
            db, ActionType.PRICE_CHANGE,
            {"value": abs(delta), "value_cents": cut_cents, "product_id": str(product.id), "currency": product.currency},
        )
        decisions.append(SimDecision(
            action="price_change", product_id=str(product.id), delta_percent=delta,
            allowed=decision.allow, reason=decision.reason,
        ))
        if decision.allow:
            price_sim[product.id] = max(0, price_sim[product.id] - cut_cents)

    allowed = sum(1 for d in decisions if d.allowed)
    denied = len(decisions) - allowed

    # ESTIMATE: revenue impact ≈ elasticity * avg_price_cut * baseline revenue
    baseline_revenue_cents = 0  # MetricDaily schema-specific; see note
    impact_cents = 0
    for d in decisions:
        if d.allowed:
            product = next((p for p in products if str(p.id) == d.product_id), None)
            if product is not None:
                impact_cents += int((product.price_cents or 0) * abs(d.delta_percent) / 100 * ELASTICITY)

    by_action: dict = {}
    for d in decisions:
        bucket = by_action.setdefault(d.action, {"allowed": 0, "denied": 0})
        bucket["allowed" if d.allowed else "denied"] += 1

    return {
        "window_days": days,
        "baseline_revenue_cents": baseline_revenue_cents,
        "decisions": len(decisions),
        "allowed": allowed,
        "denied": denied,
        "by_action": by_action,
        "est_revenue_impact_cents": impact_cents,  # ESTIMATE — elasticity-based
        "report_lines": [f"{d.action} {d.product_id} {d.delta_percent:+.1f}% -> {'ALLOW' if d.allowed else 'DENY'}" for d in decisions],
    }
