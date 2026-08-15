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
from ..models import AdCampaignSync, AuditLog, IncidentEvent, Order, Product, RevenueCampaign, StrategyLog
from ..services.campaign_service import RevenueCampaignService
from ..ads.meta import MetaAdsClient

logger = structlog.get_logger()

PRICE_CUT_PERCENT = 10.0
STALE_PRODUCT_DAYS = 14
STALE_ORDER_HOURS = 48
AD_ROAS_PAUSE = 1.0
AD_BUDGET_CUT_PERCENT = 10.0
AD_TARGET_ROAS = 3.0

ads_client = MetaAdsClient()  # monkeypatch target for tests


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
                from ..models import PriceChangeLock as _PCL
                _lock = await db.get(_PCL, product.id)
                if _lock is not None and _lock.last_change_at is not None and                         _lock.last_change_at.replace(tzinfo=None) > datetime.utcnow() - timedelta(hours=24):
                    continue  # dynamic pricing already moved this product recently
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
                _pcl = await db.get(_PCL, product.id)
                if _pcl is None:
                    db.add(_PCL(product_id=product.id, last_delta_percent=-PRICE_CUT_PERCENT))
                else:
                    _pcl.last_change_at = datetime.utcnow()
                    _pcl.last_delta_percent = -PRICE_CUT_PERCENT
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
    async def _ads_optimization(db: AsyncSession, shadow: bool) -> tuple[list[str], list[str], list[str]]:
        """ROAS-based budget optimization — policy-gated, shadow-aware (Task 5)."""
        actions, denials, proposals = [], [], []
        result = await db.execute(select(AdCampaignSync).where(AdCampaignSync.status == "ACTIVE"))
        for campaign in list(result.scalars().all()):
            if campaign.spend_cents <= 0:
                continue  # no data yet — never pause/cut on missing data
            if campaign.roas < AD_ROAS_PAUSE:
                # ROAS below 1.0 → pause (CAMPAIGN_PAUSE allow rule already seeded)
                decision = await PolicyEngine.check(db, ActionType.CAMPAIGN_PAUSE, {})
                if not decision.allow:
                    denials.append(f"campaign_pause:{campaign.platform_campaign_id}:{decision.reason}")
                    continue
                if shadow:
                    proposals.append(f"campaign_pause:{campaign.platform_campaign_id}")
                    continue
                try:
                    await ads_client.set_status(campaign.platform_campaign_id, active=False)
                except Exception:
                    logger.exception("ads_pause_failed", campaign=campaign.platform_campaign_id)
                    denials.append(f"campaign_pause:{campaign.platform_campaign_id}:api_error")
                    continue
                campaign.status = "PAUSED"
                actions.append(f"campaign_pause:{campaign.platform_campaign_id}")
                continue
            if campaign.daily_budget_cents <= 0 or campaign.spend_cents <= 0:
                continue
            # target budget = spend * (target_roas / actual_roas), clamped to ±10%
            actual_roas = campaign.roas or 0.0
            target_budget = campaign.daily_budget_cents * (AD_TARGET_ROAS / actual_roas) if actual_roas > 0 else campaign.daily_budget_cents
            delta = target_budget - campaign.daily_budget_cents
            if abs(delta) < campaign.daily_budget_cents * 0.01:
                continue  # within noise
            delta_pct = (delta / campaign.daily_budget_cents) * 100
            delta_pct = max(-AD_BUDGET_CUT_PERCENT, min(AD_BUDGET_CUT_PERCENT, delta_pct))
            delta_cents = int(campaign.daily_budget_cents * abs(delta_pct) / 100)
            decision = await PolicyEngine.check(
                db, ActionType.AD_BUDGET,
                {"value": abs(delta_pct), "value_cents": delta_cents, "currency": "THB"},
            )
            if not decision.allow:
                denials.append(f"ad_budget:{campaign.platform_campaign_id}:{decision.reason}")
                db.add(IncidentEvent(
                    title=f"Policy denied ad budget change for {campaign.name}",
                    description=decision.reason,
                    severity=IncidentSeverity.MEDIUM,
                ))
                continue
            new_budget = campaign.daily_budget_cents + int(campaign.daily_budget_cents * delta_pct / 100)
            if shadow:
                proposals.append(f"ad_budget:{campaign.platform_campaign_id}:{new_budget}")
                continue
            try:
                await ads_client.set_budget(campaign.platform_campaign_id, new_budget)
            except Exception:
                logger.exception("ads_budget_change_failed", campaign=campaign.platform_campaign_id)
                denials.append(f"ad_budget:{campaign.platform_campaign_id}:api_error")
                continue
            campaign.daily_budget_cents = new_budget
            actions.append(f"ad_budget:{campaign.platform_campaign_id}:{new_budget}")
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
        # Dynamic pricing (shared price-write path, 24h per-product lock)
        from ..pricing.dynamic import DynamicPricingEngine
        dyn = await DynamicPricingEngine.run_cycle(db, shadow=shadow)
        if not shadow:
            actions += [f"dynamic_price:{a}" for a in ([] if dyn["applied"] == 0 else [str(dyn["applied"])])]
        a2, d2, p2 = await cls._campaign_check(db, shadow)
        actions += a2; denials += d2; proposals += p2
        a3, d3, p3 = await cls._ads_optimization(db, shadow)
        actions += a3; denials += d3; proposals += p3
        actions += await cls._stale_order_review(db)
        await cls._daily_report(db)
        await db.commit()
        logger.info("commerce_ops_cycle", mode=mode.value, actions=actions, denials=denials, proposals=proposals)
        return {"skipped": False, "actions_taken": actions, "policy_denials": denials, "shadow_proposals": proposals}
