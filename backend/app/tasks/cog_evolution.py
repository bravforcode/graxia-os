"""Celery task for COG evolution loop (weekly weight adjustment suggestions)."""
import logging

from app.tasks.base import execute_managed_async_task, idempotent_task
from app.tasks.celery_app import celery_app
from app.tasks.queues import DEFAULT_QUEUE

logger = logging.getLogger(__name__)


async def run_cog_evolution():
    """
    Weekly COG evolution — analyze vault patterns and suggest scoring weight adjustments.

    Scheduled: Sunday 10:00 AM Bangkok time (after strategy_agent at 09:30)
    """
    logger.info("Starting COG evolution loop")

    try:
        from app.agents.cog_loop import CogEvolutionAgent
        from app.config import settings

        agent = CogEvolutionAgent()
        vault_path = getattr(settings, "OBSIDIAN_VAULT_PATH", None)

        if not vault_path:
            logger.warning("OBSIDIAN_VAULT_PATH not configured, skipping COG evolution")
            return {"status": "skipped", "reason": "vault_path not configured"}

        await agent.run_weekly_evolution(vault_path)

        logger.info("COG evolution loop completed successfully")
        return {"status": "success"}

    except Exception as e:
        logger.error(f"COG evolution failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@celery_app.task(name="tasks.cog_evolution.run", queue=DEFAULT_QUEUE)
@idempotent_task("{task_name}")
def run():
    """
    Celery task wrapper for COG evolution.
    """
    return execute_managed_async_task(
        task_name="cog_evolution",
        queue=DEFAULT_QUEUE,
        coroutine_factory=run_cog_evolution,
    )
