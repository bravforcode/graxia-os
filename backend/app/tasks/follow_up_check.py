import asyncio
import logging
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def run_follow_up_check() -> dict:
    """Check and generate due follow-up messages."""
    from app.agents.follow_up import follow_up_agent
    count = await follow_up_agent.run()
    logger.info(f"Follow-up check: {count} follow-ups processed")
    return {"follow_ups_processed": count}


@celery_app.task(name="tasks.follow_up_check")
def follow_up_check_task():
    return asyncio.run(run_follow_up_check())
