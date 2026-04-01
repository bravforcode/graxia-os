import asyncio
import logging
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def run_weekly_review() -> None:
    """Run learning engine analysis."""
    from app.agents.learning_engine import learning_engine
    await learning_engine.run_weekly_analysis()


@celery_app.task(name="tasks.weekly_review")
def weekly_review_task():
    return asyncio.run(run_weekly_review())
