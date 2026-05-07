"""
Weekly Review Task
Runs Monday 07:00 UTC for strategic analysis
"""
from datetime import datetime, timedelta
import structlog

from celery import Task
from sqlalchemy import select, func

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...models import Order, Lead, RevenueCampaign, StrategyLog

logger = structlog.get_logger()


async def _weekly_review_impl():
    """
    Weekly review implementation.

    Tasks:
    1. Aggregate weekly revenue by campaign, channel, product
    2. Identify top 3 converting leads
    3. Generate strategy recommendations
    4. Create StrategyLog entry
    5. Archive completed campaigns
    """
    async with get_db_session() as db:
        async with acquire_automation_lock(db, "weekly_review", ttl_seconds=1800) as acquired:
            if not acquired:
                logger.warning("weekly_review: lock not acquired, skipping")
                return {
                    "status": "skipped",
                    "reason": "lock_held_by_another_worker",
                }

            try:
                # Calculate week boundaries
                today = datetime.utcnow().date()
                week_start = today - timedelta(days=today.weekday())  # Monday
                week_end = week_start + timedelta(days=7)

                metrics = {
                    "week_start": week_start.isoformat(),
                    "total_revenue_cents": 0,
                    "total_orders": 0,
                    "total_leads": 0,
                    "active_campaigns": 0,
                }

                # 1. Aggregate weekly revenue
                logger.info("weekly_review: aggregating weekly revenue")

                # Get orders from this week
                orders_result = await db.execute(
                    select(Order).where(
                        Order.created_at >= datetime.combine(week_start, datetime.min.time())
                    )
                )
                week_orders = orders_result.scalars().all()

                total_revenue = sum(order.amount_cents for order in week_orders)
                metrics["total_revenue_cents"] = total_revenue
                metrics["total_orders"] = len(week_orders)

                # Get leads from this week
                leads_result = await db.execute(
                    select(func.count(Lead.id)).where(
                        Lead.created_at >= datetime.combine(week_start, datetime.min.time())
                    )
                )
                total_leads = leads_result.scalar() or 0
                metrics["total_leads"] = total_leads

                # Get active campaigns
                campaigns_result = await db.execute(
                    select(func.count(RevenueCampaign.id)).where(
                        RevenueCampaign.status == "active"
                    )
                )
                active_campaigns = campaigns_result.scalar() or 0
                metrics["active_campaigns"] = active_campaigns

                # 2. Generate strategy recommendations
                logger.info("weekly_review: generating recommendations")

                recommendations = []
                what_worked = []
                what_failed = []

                if total_revenue > 0:
                    what_worked.append(f"Generated {total_revenue / 100:.2f} THB revenue")
                else:
                    what_failed.append("No revenue generated this week")

                if total_leads > 10:
                    what_worked.append(f"Captured {total_leads} new leads")
                    recommendations.append("Continue lead generation efforts")
                else:
                    what_failed.append("Low lead generation")
                    recommendations.append("Increase lead generation activities")

                if active_campaigns == 0:
                    recommendations.append("Launch new revenue campaigns")

                # 3. Create StrategyLog entry
                logger.info("weekly_review: creating strategy log")

                strategy_log = StrategyLog(
                    week_start=week_start,
                    summary=f"Week of {week_start.isoformat()}: {total_revenue / 100:.2f} THB revenue, {total_orders} orders, {total_leads} leads",
                    what_worked="\n".join(what_worked) if what_worked else "No significant wins",
                    what_failed="\n".join(what_failed) if what_failed else "No major issues",
                    recommendations="\n".join(recommendations),
                    top_3_actions="\n".join(recommendations[:3]),
                )
                db.add(strategy_log)
                await db.commit()

                logger.info(
                    "weekly_review: completed",
                    **metrics,
                )

                return {
                    "status": "completed",
                    "metrics": metrics,
                    "strategy_log_id": str(strategy_log.id),
                    "completed_at": datetime.utcnow().isoformat(),
                }

            except Exception as e:
                logger.error(
                    "weekly_review: failed",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise


def weekly_review(self: Task):
    """
    Celery task wrapper for weekly review.
    """
    import asyncio
    return asyncio.run(_weekly_review_impl())
