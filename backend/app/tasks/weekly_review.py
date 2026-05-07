import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select

from app.agents.learning_engine import LearningEngine
from app.database import AsyncSessionLocal
from app.models.opportunity import Opportunity
from app.models.submission import Submission
from app.tasks.base import execute_managed_async_task, idempotent_task
from app.tasks.celery_app import celery_app
from app.tasks.queues import DEFAULT_QUEUE
from app.telegram_bot.bot import send_message

logger = logging.getLogger(__name__)


async def run_weekly_review():
    """
    Generate weekly review and learning insights.
    
    Scheduled: Sunday 9:30 AM Bangkok time
    """
    logger.info("Starting weekly review")
    
    try:
        async with AsyncSessionLocal() as db:
            # Get last week's data
            week_ago = datetime.now(UTC) - timedelta(days=7)
            
            # Opportunities discovered
            opp_query = select(func.count(Opportunity.id)).where(
                Opportunity.found_at >= week_ago
            )
            opp_result = await db.execute(opp_query)
            opportunities_count = opp_result.scalar() or 0
            
            # Submissions made
            sub_query = select(func.count(Submission.id)).where(
                Submission.created_at >= week_ago
            )
            sub_result = await db.execute(sub_query)
            submissions_count = sub_result.scalar() or 0
            
            # Wins (accepted submissions)
            wins_query = select(Submission).where(
                and_(
                    Submission.status == "won",
                    Submission.updated_at >= week_ago
                )
            )
            wins_result = await db.execute(wins_query)
            wins = list(wins_result.scalars().all())
            
            # Losses (rejected submissions)
            losses_query = select(Submission).where(
                and_(
                    Submission.status == "lost",
                    Submission.updated_at >= week_ago
                )
            )
            losses_result = await db.execute(losses_query)
            losses = list(losses_result.scalars().all())

            opportunity_ids = {
                submission.opportunity_id
                for submission in wins + losses
                if submission.opportunity_id is not None
            }
            opportunity_titles: dict = {}
            if opportunity_ids:
                opportunity_rows = await db.execute(
                    select(Opportunity.id, Opportunity.title).where(
                        Opportunity.id.in_(opportunity_ids)
                    )
                )
                opportunity_titles = {
                    row.id: row.title or "Unknown"
                    for row in opportunity_rows
                }
            
            # Generate review message
            message = f"""
📊 Weekly Review

📈 This Week's Stats:
• Opportunities: {opportunities_count}
• Submissions: {submissions_count}
• Wins: {len(wins)} ✅
• Losses: {len(losses)} ❌

"""
            
            if wins:
                message += "🎉 Wins:\n"
                for win in wins[:3]:
                    message += f"• {opportunity_titles.get(win.opportunity_id, 'Unknown')}\n"
                message += "\n"
            
            if losses:
                message += "📝 Lessons from Losses:\n"
                # Run learning engine on losses
                learning_engine = LearningEngine()
                for loss in losses[:3]:
                    insights = await learning_engine.analyze_loss(loss)
                    if insights:
                        message += f"• {opportunity_titles.get(loss.opportunity_id, 'Unknown')}\n"
                        message += f"  Insight: {insights.get('key_insight', 'N/A')[:100]}\n"
                message += "\n"
            
            # Conversion rate
            if submissions_count > 0:
                conversion_rate = (len(wins) / submissions_count) * 100
                message += f"📊 Conversion Rate: {conversion_rate:.1f}%\n\n"
            
            message += "💡 Keep learning and improving! 🚀"
            
            await send_message(message)

            try:
                from app.agents.obsidian_sync import obsidian_sync_agent

                await obsidian_sync_agent.create_weekly_review(
                    {
                        "opportunities": opportunities_count,
                        "submissions": submissions_count,
                        "wins": len(wins),
                        "losses": len(losses),
                        "highlights": "Weekly review generated from live system metrics.",
                        "learnings": message,
                    }
                )
            except Exception as exc:
                logger.warning("Weekly review sync to Obsidian failed: %s", exc)
            
            logger.info("Weekly review complete")
            return {
                "opportunities": opportunities_count,
                "submissions": submissions_count,
                "wins": len(wins),
                "losses": len(losses)
            }
    except Exception as e:
        logger.error(f"Weekly review task failed: {e}", exc_info=True)
        raise


@celery_app.task(name="tasks.weekly_review.run", queue=DEFAULT_QUEUE)
@idempotent_task("{task_name}:{date}")
def weekly_review_task():
    return execute_managed_async_task(
        task_name="weekly_review",
        queue=DEFAULT_QUEUE,
        coroutine_factory=run_weekly_review,
    )
