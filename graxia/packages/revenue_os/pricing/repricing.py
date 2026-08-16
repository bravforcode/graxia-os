"""Competitor repricing — react to competitor price observations through the
SHARED policy-gated price path (DynamicPricingEngine.apply: 24h PriceChangeLock
+ PRICE_CHANGE dual caps + audit log).

Reaction rule: only act when our price is > REACT_ABOVE_PERCENT above the
competitor; retarget to 2% UNDER the competitor; deltas clamped to
±MAX_REPRICE_PERCENT (the seeded PRICE_CHANGE percent cap is 20%).
Observations come from a provider seam (scraping/API) wired at deployment.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import ProductStatus
from ..models import Product
from .dynamic import DynamicPricingEngine

MAX_REPRICE_PERCENT = 20.0   # clamp — matches seeded PRICE_CHANGE PERCENT cap
REACT_ABOVE_PERCENT = 5.0    # only react when we are >5% above the competitor
UNDERCUT_PERCENT = 2.0       # retarget price = competitor - 2%


async def repricing_cycle(db: AsyncSession, observations: dict,
                          adapter=None) -> dict:
    """Apply repricing deltas from competitor observations.

    observations: {product_id (str): competitor_price_cents (int)}.
    Returns {applied, skipped, changes:[{product_id, delta_percent}]}.
    """
    applied = skipped = 0
    changes: list[dict] = []
    for pid_str, comp_cents in observations.items():
        product = await db.get(Product, pid_str)
        if product is None or product.status != ProductStatus.PUBLISHED:
            skipped += 1
            continue
        ours = product.price_cents or 0
        if ours <= 0 or comp_cents <= 0:
            skipped += 1
            continue
        if ours <= int(comp_cents * (1 + REACT_ABOVE_PERCENT / 100)):
            skipped += 1  # already at/below competitor + buffer -> no reaction
            continue
        desired = int(comp_cents * (1 - UNDERCUT_PERCENT / 100))
        delta = (desired - ours) / ours * 100
        delta = max(-MAX_REPRICE_PERCENT, min(MAX_REPRICE_PERCENT, delta))
        if await DynamicPricingEngine.apply(db, product, delta):
            applied += 1
            changes.append({"product_id": str(product.id),
                            "delta_percent": round(delta, 2)})
        else:
            skipped += 1  # policy denied or 24h lock
    await db.commit()
    return {"applied": applied, "skipped": skipped, "changes": changes}


class CompetitorPriceProvider:
    """Provider seam for competitor price observations. Deployment wires a
    subclass implementing get_competitor_prices() -> {product_id: price_cents}."""

    async def get_competitor_prices(self) -> dict:
        raise NotImplementedError


def provider_from_env() -> Optional[CompetitorPriceProvider]:
    return None  # wired at deployment (runbook: competitor-repricing)
