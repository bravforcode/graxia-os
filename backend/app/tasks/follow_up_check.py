"""
Follow-up Check Task

Scheduled task to check for follow-ups needed.
"""
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select

from app.database import AsyncSessionLocal
from app.models.submission import Submission
from app.tasks.base import execute_managed_async_task, idempotent_task
from app.tasks.celery_app import celery_app
from app.tasks.queues import DEFAULT_QUEUE
from app.telegram_bot.bot import send_message

logger = logging.getLogger(__name__)


async def run_follow_up_check():
    """
    Check for submissions that need follow-up.
    
    Scheduled: 9:00 AM Bangkok time daily
    """
    logger.info("Starting follow-up check")
    
    try:
        async with AsyncSessionLocal() as db:
            # Find submissions that need follow-up
            # - Status: submitted or in_review
            # - Last updated > 7 days ago
            # - No follow-up in last 7 days
            
            week_ago = datetime.now(UTC) - timedelta(days=7)
            
            query = select(Submission).where(
                and_(
                    Submission.status.in_(["submitted", "in_review"]),
                    Submission.updated_at < week_ago,
                    (Submission.last_follow_up_at == None) |
                    (Submission.last_follow_up_at < week_ago)
                )
            ).limit(10)
            
            result = await db.execute(query)
            submissions = list(result.scalars().all())
            
            if not submissions:
                logger.info("No follow-ups needed")
                return {"follow_ups_needed": 0}
            
            # Send notification
            message = f"""
📬 Follow-up Reminder

{len(submissions)} submission(s) need follow-up:

"""
            for i, sub in enumerate(submissions[:5], 1):
                days_ago = (datetime.now(UTC) - sub.updated_at).days
                message += f"{i}. {sub.opportunity.title if sub.opportunity else 'Unknown'}\n"
                message += f"   Status: {sub.status}\n"
                message += f"   Last update: {days_ago} days ago\n\n"
            
            if len(submissions) > 5:
                message += f"...and {len(submissions) - 5} more\n"
            
            await send_message(message)
            
            logger.info(f"Follow-up check complete: {len(submissions)} need follow-up")
            return {"follow_ups_needed": len(submissions)}
    except Exception as e:
        logger.error(f"Follow-up check task failed: {e}", exc_info=True)
        raise


@celery_app.task(name="tasks.follow_up_check.run", queue=DEFAULT_QUEUE)
@idempotent_task("{task_name}:{date}")
def follow_up_check_task():
    return execute_managed_async_task(
        task_name="follow_up_check",
        queue=DEFAULT_QUEUE,
        coroutine_factory=run_follow_up_check,
    )
