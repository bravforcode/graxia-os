"""Commerce operations agent - the main store manager.

Runs on celery beat (lock-wrapped by the task in Task 8). Reads state, decides,
policy-checks, executes, logs. Rule-based for Phase 1 (no LLM in the critical path).
Mode semantics (Task 12): OFF=skip, SHADOW=log-only proposals, LIMITED/FULL=execute
(the engine applies the LIMITED multiplier automatically).
"""
from __future__ import annotations

import structlog
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.policy_engine import PolicyEngine
from ..enums import ActionType, AutonomyMode, CampaignStatus, IncidentSeverity, OrderStatus, ProductStatus
from ..models import AuditLog, IncidentEvent, Order, Product, RevenueCampaign, StrategyLog
from ..services.campaign_service import RevenueCampaignService

logger = structlog.get_logger()

PRICE_CUT_PERCENT = 10.0
STALE_PRODUCT_DAYS = 14
STALE_ORDER_HOURS = 48


def _naive(dt: datetime) -> datetime:
    """Postgres returns tz-aware datetimes; normalize to naive UTC for comparisons."""
    if dt is not None and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


class CommerceOpsAgent:
    """Main store manager: read state → decide → policy check → execute (or log in SHADOW)."""

    @staticmethod
    async def _log_action(db: AsyncSession, event_type: str, message: str, metadata: dict | None = None) -> None:
        db.add(AuditLog(event_type=event_type, message=message, metadata_=metadata or {}))
        await db.flush()

    @staticmethod
    async def _price_optimization(db: AsyncSession, shadow: bool) -> tuple[list[str], list[str], list[str]]:
        actions, denials, proposals = [], [], []
        cutoff = datetime.utcnow() - timedelta(days=7)
        result = await db.execute(select(Product).where(Product.status == ProductStatus.PUBLISHED))
        for product in list(result.scalars().all()):
            order_count = await db.scalar(
                select(Order.id).where(
                    Order.product_id == product.id,
                    Order.status == OrderStatus.PAID,
                    Order.purchased_at >= cutoff,
                ).limit(1)
            )
            if order_count is None and _naive(product.created_at) < datetime.utcnow() - timedelta(days=STALE_PRODUCT_DAYS):
                cut_cents = int((product.price_cents or 0) * (PRICE_CUT_PERCENT / 100))
                decision = await PolicyEngine.check(
                    db, ActionType.PRICE_CHANGE,
                    {
                        "value": PRICE_CUT_PERCENT,
                        "value_cents": cut_cents,          # ABSOLUTE cap check (draft-gap fix)
                        "product_id": str(product.id),
                    },
                )
                if not decision.allow:
                    denials.append(f"price_change:{product.slug}:{decision.reason}")
                    db.add(IncidentEvent(
                        title=f"Policy denied price change for {product.name}",
                        description=decision.reason,
                        severity=IncidentSeverity.MEDIUM,
                    ))
                    continue
                if shadow:
                    proposals.append(f"price_change:{product.slug}:-{PRICE_CUT_PERCENT}%")
                    await CommerceOpsAgent._log_action(
                        db, "agent.price_change.shadow",
                        f"SHADOW: would cut price of {product.name} by {PRICE_CUT_PERCENT}%",
                        {"product_id": str(product.id), "percent": PRICE_CUT_PERCENT},
                    )
                    continue
                product.price_cents = max(0, (product.price_cents or 0) - cut_cents)
                actions.append(f"price_change:{product.slug}:-{PRICE_CUT_PERCENT}%")
                await CommerceOpsAgent._log_action(
                    db, "agent.price_change",
                    f"Agent cut price of {product.name} by {PRICE_CUT_PERCENT}%",
                    {"product_id": str(product.id), "percent": PRICE_CUT_PERCENT, "cut_cents": cut_cents},
                )
        await db.flush()
        return actions, denials, proposals

    @staticmethod
    async def _campaign_check(db: AsyncSession, shadow: bool) -> tuple[list[str], list[str], list[str]]:
        actions, denials, proposals = [], [], []
        result = await db.execute(select(RevenueCampaign).where(RevenueCampaign.status == CampaignStatus.ACTIVE))
        for campaign in list(result.scalars().all()):
            metrics = await RevenueCampaignService.check_campaign_budget(db, campaign.id)
            if metrics.get("should_pause"):
                decision = await PolicyEngine.check(db, ActionType.CAMPAIGN_PAUSE, {})
                if not decision.allow:
                    denials.append(f"campaign_pause:{campaign.slug}:{decision.reason}")
                    continue
                if shadow:
                    proposals.append(f"campaign_pause:{campaign.slug}")
                    continue
                await RevenueCampaignService.pause_campaign(db, campaign.id, reason="auto: over budget")
                actions.append(f"campaign_pause:{campaign.slug}")
        await db.flush()
        return actions, denials, proposals

    @staticmethod
    async def _stale_order_review(db: AsyncSession) -> list[str]:
        actions = []
        cutoff = datetime.utcnow() - timedelta(hours=STALE_ORDER_HOURS)
        result = await db.execute(select(Order).where(Order.status == OrderStatus.PENDING))
        for order in list(result.scalars().all()):
            if _naive(order.created_at) >= cutoff:
                continue  # not stale yet (naive-UTC comparison)
            db.add(IncidentEvent(
                title=f"Stale pending order {order.id}",
                description=f"Order {order.id} stuck in PENDING for > {STALE_ORDER_HOURS}h",
                severity=IncidentSeverity.LOW,
                affected_order_id=order.id,
            ))
            actions.append(f"escalate_order:{order.id}")
        await db.flush()
        return actions

    @staticmethod
    async def _daily_report(db: AsyncSession) -> None:
        now = datetime.utcnow()
        from sqlalchemy import func as _func
        order_count = await db.scalar(
            select(_func.count(Order.id)).where(Order.purchased_at >= now - timedelta(days=1))
        )
        revenue = await db.scalar(
            select(_func.coalesce(_func.sum(Order.amount_cents), 0)).where(
                Order.status == OrderStatus.PAID,
                Order.purchased_at >= now - timedelta(days=1),
            )
        )
        db.add(StrategyLog(
            week_start=now.date(),
            summary=f"Daily report: {order_count or 0} orders, {(revenue or 0) / 100:.2f} revenue (24h)",
            recommendations="Agent-managed: see audit log for actions.",
        ))
        await db.flush()

    @classmethod
    async def run_cycle(cls, db: AsyncSession) -> dict:
        if await PolicyEngine.check_circuit_breaker(db):
            logger.warning("commerce_ops_skipped", reason="circuit_breaker_tripped")
            return {"skipped": True, "reason": "circuit_breaker",
                    "actions_taken": [], "policy_denials": [], "shadow_proposals": []}
        mode = await PolicyEngine.get_autonomy_mode(db)
        if mode == AutonomyMode.OFF:
            logger.info("commerce_ops_skipped", reason="autonomy_off")
            return {"skipped": True, "actions_taken": [], "policy_denials": [], "shadow_proposals": []}
        shadow = mode == AutonomyMode.SHADOW
        actions: list[str] = []
        denials: list[str] = []
        proposals: list[str] = []
        a1, d1, p1 = await cls._price_optimization(db, shadow)
        actions += a1; denials += d1; proposals += p1
        a2, d2, p2 = await cls._campaign_check(db, shadow)
        actions += a2; denials += d2; proposals += p2
        actions += await cls._stale_order_review(db)
        await cls._daily_report(db)
        await db.commit()
        logger.info("commerce_ops_cycle", mode=mode.value, actions=actions, denials=denials, proposals=proposals)
        return {"skipped": False, "actions_taken": actions, "policy_denials": denials, "shadow_proposals": proposals}
