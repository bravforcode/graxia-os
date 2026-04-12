"""
Job Discovery Task

Scheduled task to run job hunter agent.
"""
import logging
from datetime import datetime, timezone

from app.agents.job_hunter import job_hunter_agent
from app.tasks.base import execute_managed_async_task, idempotent_task
from app.tasks.celery_app import celery_app
from app.tasks.queues import DEFAULT_QUEUE
from app.telegram_bot.bot import send_message

logger = logging.getLogger(__name__)


async def run_job_discovery():
    """
    Run job discovery across all platforms.
    
    Scheduled: 2x per day (10 AM, 6 PM Bangkok time)
    Target: 50+ jobs/week (7+ jobs/day)
    """
    logger.info("Starting scheduled job discovery")
    
    try:
        # Run job hunter
        result = await job_hunter_agent.run()
        
        discovered = result.get("discovered", 0)
        new_jobs = result.get("new", 0)
        duplicates = result.get("duplicates", 0)
        errors = result.get("errors", [])
        
        # Log results
        logger.info(
            f"Job discovery complete: {discovered} discovered, "
            f"{new_jobs} new, {duplicates} duplicates"
        )
        
        # Send notification if significant results
        if new_jobs >= 5:
            message = f"""
🎯 Job Discovery Update

✨ Found {new_jobs} new opportunities!
📊 Total discovered: {discovered}
🔄 Duplicates filtered: {duplicates}

Use /jobs to see top opportunities.
"""
            await send_message(message)
        
        # Alert on errors
        if errors:
            error_msg = f"⚠️ Job discovery had {len(errors)} errors:\n"
            for err in errors[:3]:  # Show first 3 errors
                error_msg += f"- {err.get('scraper')}: {err.get('error')[:50]}\n"
            await send_message(error_msg)
        
        return result
    except Exception as e:
        logger.error(f"Job discovery task failed: {e}", exc_info=True)
        await send_message(f"❌ Job discovery failed: {str(e)[:100]}")
        raise


@celery_app.task(name="tasks.job_discovery.run", queue=DEFAULT_QUEUE)
@idempotent_task("{task_name}:{date}")
def job_discovery_task():
    return execute_managed_async_task(
        task_name="job_discovery",
        queue=DEFAULT_QUEUE,
        coroutine_factory=run_job_discovery,
    )
