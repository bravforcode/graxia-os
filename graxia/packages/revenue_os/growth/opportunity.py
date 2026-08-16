"""Growth opportunity engine — read-only recommendations (no auto-mutations).

Answers "where should effort go?" from real data:
- margin per channel (channel_pl) -> shift inventory to the higher-margin
  channel when the gap > 10 points
- demand per channel (orders last 7d) -> stock up / focus listing on movers
- low-margin products (est margin < 20%) -> repricing candidates

Consumed by GET /api/dashboard/opportunities and the daily growth digest.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import OrderStatus
from ..finance.channel_pl import channel_pl
from ..models import Order

MARGIN_SHIFT_GAP_POINTS = 10.0
LOW_MARGIN_PERCENT = 20.0
DEMAND_WINDOW_DAYS = 7


async def opportunity_scan(db: AsyncSession) -> dict:
    """Produce recommendations from current data. Pure read."""
    recommendations: list[dict] = []
    pl = {r["platform"]: r for r in await channel_pl(db)}

    # 1) margin shift across channels
    rows = sorted(pl.values(), key=lambda r: r["est_margin_cents"], reverse=True)
    if len(rows) >= 2:
        best, worst = rows[0], rows[-1]
        if best["revenue_cents"] > 0:
            best_margin_pct = (best["est_margin_cents"] / best["revenue_cents"] * 100)
            worst_margin_pct = (worst["est_margin_cents"] / worst["revenue_cents"] * 100)
            if best_margin_pct - worst_margin_pct > MARGIN_SHIFT_GAP_POINTS:
                recommendations.append({
                    "type": "channel_margin_shift",
                    "from": worst["platform"], "to": best["platform"],
                    "gap_points": round(best_margin_pct - worst_margin_pct, 1),
                    "detail": (f"{best['platform']} margin {best_margin_pct:.1f}% vs "
                               f"{worst['platform']} {worst_margin_pct:.1f}% — shift "
                               f"inventory/ads budget toward {best['platform']}"),
                })

    # 2) demand per channel (last 7 days)
    cutoff = datetime.now(timezone.utc) - timedelta(days=DEMAND_WINDOW_DAYS)
    demand = (await db.execute(
        select(Order.platform, func.count(Order.id))
        .where(Order.status.in_([OrderStatus.PAID, OrderStatus.PROCESSING,
                                 OrderStatus.FULFILLED]),
               Order.purchased_at >= cutoff)
        .group_by(Order.platform)
        .order_by(func.count(Order.id).desc()))).all()
    for platform, count in demand:
        recommendations.append({
            "type": "channel_demand",
            "channel": platform,
            "orders_7d": count,
            "detail": f"{platform}: {count} orders in the last {DEMAND_WINDOW_DAYS} days",
        })

    # 3) low-margin channels (est margin < 20% of revenue) -> repricing targets
    for r in pl.values():
        if r["revenue_cents"] > 0:
            margin_pct = r["est_margin_cents"] / r["revenue_cents"] * 100
            if margin_pct < LOW_MARGIN_PERCENT:
                recommendations.append({
                    "type": "low_margin_channel",
                    "channel": r["platform"],
                    "margin_percent": round(margin_pct, 1),
                    "detail": (f"{r['platform']} est margin {margin_pct:.1f}% — "
                               f"check price_multiplier / repricing"),
                })

    return {"generated_at": datetime.now(timezone.utc).isoformat(),
            "recommendations": recommendations}


def _digest_text(scan: dict) -> str:
    lines = [f"Growth digest ({scan['generated_at'][:10]}):"]
    for rec in scan["recommendations"][:8]:
        lines.append(f"- [{rec['type']}] {rec['detail']}")
    return "\n".join(lines) if len(lines) > 1 else "Growth digest: no opportunities today"
