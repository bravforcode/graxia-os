"""Policy scenario simulation — what-if policy changes WITHOUT touching the DB.

Pure read: candidate rules are evaluated in-memory against recent PAID orders
using the exact same _evaluate logic the live engine uses (FX-aware, mode-
aware, fail-closed when no rule applies). No writes, no commits.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels.marketplace_sync import fee_rate_for
from ..core.policy_engine import PolicyEngine, PolicyRule
from ..enums import ActionType, OrderStatus, RuleType, ValueType
from ..models import Order, Product

# Actions with full historical data to replay. Extend as more contexts exist.
SUPPORTED_SIMULATIONS = {ActionType.SUPPLIER_PURCHASE.value}


def _candidate_rule(rule_type: str, value_type: str, value: float,
                    priority: int = 10) -> PolicyRule:
    """In-memory rule (never persisted).

    rule_type/value_type are coerced to the enum types — plain strings do NOT
    compare equal to StrEnum members under Python 3.12 semantics, which would
    silently make every candidate rule inapplicable.
    """
    return PolicyRule(action="sim", rule_type=RuleType(rule_type),
                      value_type=ValueType(value_type), value=value,
                      priority=priority, scope="global")


async def simulate_policy_change(db: AsyncSession, action: str,
                                 candidate_rules: list[tuple],
                                 days: int = 30) -> dict:
    """candidate_rules: (rule_type, value_type, value) tuples, seed shape.

    Replays the last `days` of PAID orders through the candidates and reports
    would_allow / would_deny with up to 5 denial examples. Mirrors the live
    engine: a MAX/MIN rule that passes counts as allow; NO applicable rule
    counts as deny (fail-closed).
    """
    if action not in SUPPORTED_SIMULATIONS:
        return {"supported": False, "action": action,
                "reason": f"no historical data for action '{action}'"}
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    orders = (await db.execute(select(Order).where(
        Order.status == OrderStatus.PAID,
        Order.purchased_at >= cutoff,
    ))).scalars().all()
    rules = [_candidate_rule(*r) for r in candidate_rules]
    mode = await PolicyEngine.get_autonomy_mode(db)
    allowed = denied = 0
    denied_examples: list[dict] = []
    for order in orders:
        product = await db.get(Product, order.product_id)
        if product is None:
            continue
        cost = product.supplier_cost_cents or 0
        fee = order.amount_cents * await fee_rate_for(db, order.platform)
        margin = (((order.amount_cents - cost - fee) / order.amount_cents * 100)
                  if order.amount_cents else 0.0)
        context = {"value": margin, "value_cents": cost,
                   "order_id": str(order.id), "currency": order.currency}
        denied_reason = None
        saw_applicable = False
        for rule in rules:
            applies, reason = PolicyEngine._evaluate(rule, context, mode)
            if not applies:
                continue
            saw_applicable = True
            if reason is not None:
                denied_reason = reason
                break
        if denied_reason is not None or not saw_applicable:
            denied += 1
            if len(denied_examples) < 5:
                denied_examples.append({
                    "order_id": str(order.id), "platform": order.platform,
                    "margin_percent": round(margin, 1), "cost_cents": cost,
                    "reason": denied_reason or "no applicable rule",
                })
        else:
            allowed += 1
    return {"supported": True, "action": action, "orders_checked": len(orders),
            "would_allow": allowed, "would_deny": denied,
            "denied_examples": denied_examples}
