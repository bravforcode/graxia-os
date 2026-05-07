import logging
from typing import TypedDict

from app.tasks.base import execute_managed_async_task, idempotent_task
from app.tasks.celery_app import celery_app
from app.tasks.queues import DEFAULT_QUEUE

logger = logging.getLogger(__name__)


class DailyScanResult(TypedDict):
    competitions: int
    leads: int


async def run_daily_scan() -> DailyScanResult:
    """Run competition scout + lead hunter."""
    from app.agents.briefer import briefer_agent
    from app.agents.competition_scout import CompetitionScout
    from app.agents.lead_hunter import LeadHunter

    scout = CompetitionScout()
    hunter = LeadHunter()

    comp_count = int(await scout.run())
    lead_count = int(await hunter.run())

    await briefer_agent.send_morning_brief()

    logger.info(f"Daily scan: {comp_count} competitions + {lead_count} leads found")
    return {"competitions": comp_count, "leads": lead_count}


@celery_app.task(name="tasks.daily_scan.run", queue=DEFAULT_QUEUE)
@idempotent_task("{task_name}:{date}")
def daily_scan_task() -> DailyScanResult:
    return execute_managed_async_task(
        task_name="daily_scan",
        queue=DEFAULT_QUEUE,
        coroutine_factory=run_daily_scan,
    )
