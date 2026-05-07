"""
Daily Revenue Operations Task
Runs at 06:00 UTC daily
"""
from datetime import datetime
import structlog

from celery import Task
from sqlalchemy import select

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...core.scoring import calculate_lead_score
from ...models import Lead, RevenueCampaign, Order
from ...enums import LeadStatus, CampaignStatus
from ...services.campaign_service import RevenueCampaignService

logger = structlog.get_logger()


async def _daily_revenue_ops_impl():
    """
    Daily revenue operations implementation.

    Tasks:
    1. Score all NEW leads
    2. Identify campaigns over budget → pause
    3. Update campaign metrics
    4. Generate daily revenue summary
    5. Update attribution analytics
    """
    async with get_db_session() as db:
        async with acquire_automation_lock(db, "daily_revenue_ops", ttl_seconds=3600) as acquired:
            if not acquired:
                logger.warning("daily_revenue_ops: lock not acquired, skipping")
                return {
                    "status": "skipped",
                    "reason": "lock_held_by_another_worker",
                }

            try:
                metrics = {
                    "leads_scored": 0,
                    "campaigns_paused": 0,
                    "campaigns_updated": 0,
                }

                # 1. Score all NEW leads
                logger.info("daily_revenue_ops: scoring new leads")
                result = await db.execute(
                    select(Lead).where(Lead.status == LeadStatus.NEW)
                )
                new_leads = result.scalars().all()

                for lead in new_leads:
                    lead_data = {
                        "email": lead.email,
                        "source": lead.source,
                        "lead_magnet_id": lead.lead_magnet_id,
                    }
                    score, rationale = calculate_lead_score(lead_data)
                    lead.score = score
                    lead.score_rationale = rationale
                    metrics["leads_scored"] += 1

                await db.commit()
                logger.info(f"daily_revenue_ops: scored {metrics['leads_scored']} leads")

                # 2. Identify campaigns over budget → pause
                logger.info("daily_revenue_ops: checking campaign budgets")
                paused = await RevenueCampaignService.auto_pause_over_budget_campaigns(db)
                metrics["campaigns_paused"] = paused
                logger.info(f"daily_revenue_ops: paused {paused} campaigns")

                # 3. Update campaign metrics
                logger.info("daily_revenue_ops: updating campaign metrics")
                active_campaigns = await RevenueCampaignService.get_active_campaigns(db)
                for campaign in active_campaigns:
                    await RevenueCampaignService.update_campaign_metrics(db, campaign.id)
                    metrics["campaigns_updated"] += 1

                logger.info(f"daily_revenue_ops: updated {metrics['campaigns_updated']} campaigns")

                # 4. Generate daily revenue summary
                logger.info("daily_revenue_ops: generating revenue summary")
                today_result = await db.execute(
                    select(Order).where(
                        Order.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
                    )
                )
                today_orders = today_result.scalars().all()

                total_revenue = sum(order.amount_cents for order in today_orders)
                metrics["today_orders"] = len(today_orders)
                metrics["today_revenue_cents"] = total_revenue

                logger.info(
                    "daily_revenue_ops: completed",
                    **metrics,
                )

                return {
                    "status": "completed",
                    "metrics": metrics,
                    "completed_at": datetime.utcnow().isoformat(),
                }

            except Exception as e:
                logger.error(
                    "daily_revenue_ops: failed",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise


def daily_revenue_ops(self: Task):
    """
    Celery task wrapper for daily revenue operations.
    """
    import asyncio
    return asyncio.run(_daily_revenue_ops_impl())
