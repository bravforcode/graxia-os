"""
Job Discovery Task

Scheduled task to run job hunter agent.
"""
import logging

from app.agents.job_hunter import job_hunter_agent
from app.tasks.base import execute_managed_async_task, idempotent_task
from app.tasks.celery_app import celery_app
from app.tasks.queues import DEFAULT_QUEUE

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
        
        # Log results
        logger.info(
            f"Job discovery complete: {discovered} discovered, "
            f"{new_jobs} new, {duplicates} duplicates"
        )
        
        return result
    except Exception:
        logger.error("Job discovery task failed", exc_info=True)
        raise


@celery_app.task(name="tasks.job_discovery.run", queue=DEFAULT_QUEUE)
@idempotent_task("{task_name}:{date}")
def job_discovery_task():
    return execute_managed_async_task(
        task_name="job_discovery",
        queue=DEFAULT_QUEUE,
        coroutine_factory=run_job_discovery,
    )
