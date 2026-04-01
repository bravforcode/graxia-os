import asyncio
import logging
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def run_daily_scan() -> dict:
    """Run competition scout + lead hunter."""
    from app.agents.competition_scout import CompetitionScout
    from app.agents.lead_hunter import LeadHunter
    from app.agents.briefer import briefer_agent

    scout = CompetitionScout()
    hunter = LeadHunter()

    comp_count = await scout.run()
    lead_count = await hunter.run()

    await briefer_agent.send_morning_brief()

    logger.info(f"Daily scan: {comp_count} competitions + {lead_count} leads found")
    return {"competitions": comp_count, "leads": lead_count}


@celery_app.task(name="tasks.daily_scan")
def daily_scan_task():
    return asyncio.run(run_daily_scan())
