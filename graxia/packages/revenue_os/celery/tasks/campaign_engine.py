"""
Campaign Engine Task
Runs every 15 minutes to manage campaign lifecycle
"""
from datetime import datetime
import structlog

from celery import Task

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...services.campaign_service import RevenueCampaignService

logger = structlog.get_logger()


async def _campaign_engine_impl():
    """
    Campaign engine implementation.

    Tasks:
    1. Resume PAUSED campaigns whose incident has been RESOLVED
    2. Pause ACTIVE campaigns linked to OPEN CRITICAL incidents
    3. Expire campaigns past end_date → status=COMPLETED
    4. Compute ROAS (Return on Ad Spend) for all active campaigns
    5. Trigger notifications if campaign exceeds target revenue
    """
    async with get_db_session() as db:
        async with acquire_automation_lock(db, "campaign_engine", ttl_seconds=600) as acquired:
            if not acquired:
                logger.debug("campaign_engine: lock not acquired, skipping")
                return {
                    "status": "skipped",
                    "reason": "lock_held_by_another_worker",
                }

            try:
                metrics = {
                    "campaigns_paused_budget": 0,
                    "campaigns_paused_incidents": 0,
                    "campaigns_updated": 0,
                }

                # 1. Pause campaigns over budget
                logger.info("campaign_engine: checking campaign budgets")
                paused_budget = await RevenueCampaignService.auto_pause_over_budget_campaigns(db)
                metrics["campaigns_paused_budget"] = paused_budget

                # 2. Pause campaigns with critical incidents
                logger.info("campaign_engine: checking critical incidents")
                paused_incidents = await RevenueCampaignService.auto_pause_campaigns_with_critical_incidents(db)
                metrics["campaigns_paused_incidents"] = paused_incidents

                # 3. Update metrics for all active campaigns
                logger.info("campaign_engine: updating campaign metrics")
                active_campaigns = await RevenueCampaignService.get_active_campaigns(db)

                for campaign in active_campaigns:
                    await RevenueCampaignService.update_campaign_metrics(db, campaign.id)
                    metrics["campaigns_updated"] += 1

                    # Check if campaign exceeded target revenue
                    if campaign.target_revenue_cents > 0:
                        if campaign.actual_revenue_cents >= campaign.target_revenue_cents:
                            logger.info(
                                "campaign_engine: campaign exceeded target",
                                campaign_id=str(campaign.id),
                                target=campaign.target_revenue_cents,
                                actual=campaign.actual_revenue_cents,
                            )

                logger.info(
                    "campaign_engine: completed",
                    **metrics,
                )

                return {
                    "status": "completed",
                    "metrics": metrics,
                    "completed_at": datetime.utcnow().isoformat(),
                }

            except Exception as e:
                logger.error(
                    "campaign_engine: failed",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise


def campaign_engine(self: Task):
    """
    Celery task wrapper for campaign engine.
    """
    import asyncio
    return asyncio.run(_campaign_engine_impl())
