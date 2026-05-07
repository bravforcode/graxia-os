"""SkillsMP Scheduler Integration"""

import logging

from app.config import settings
from app.core.skill_learning_engine import SkillLearningEngine
from app.database import AsyncSessionLocal
from app.jobs.skillsmp_sync import run_hourly_sync
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


async def run_skillsmp_sync_job():
    """Hourly sync job wrapper."""
    logger.info("Running scheduled SkillsMP sync job")

    try:
        async with AsyncSessionLocal() as db:
            api_key = getattr(settings, "SKILLSMP_API_KEY", None)
            if not api_key:
                logger.warning("SKILLSMP_API_KEY not configured, skipping sync")
                return

            result = await run_hourly_sync(db, api_key)

            if result.get("status") == "success":
                stats = result.get("stats", {})
                logger.info(
                    f"SkillsMP sync completed: {stats.get('total_processed', 0)} processed, "
                    f"{stats.get('total_added', 0)} added, {stats.get('total_updated', 0)} updated"
                )
            else:
                logger.error(f"SkillsMP sync failed: {result.get('error')}")

    except Exception as e:
        logger.exception(f"SkillsMP sync job error: {e}")


async def run_skill_improvement_job():
    """Daily job to generate AI improvements for underperforming skills."""
    logger.info("Running scheduled skill improvement job")

    try:
        async with AsyncSessionLocal() as db:
            client_kwargs = {"api_key": settings.OPENAI_API_KEY}
            if settings.OPENAI_BASE_URL:
                client_kwargs["base_url"] = settings.OPENAI_BASE_URL
            openai_client = AsyncOpenAI(**client_kwargs)
            engine = SkillLearningEngine(db, openai_client)

            # Analyze and generate improvements
            analysis = await engine.analyze_skill_effectiveness(min_usage=5)

            improvements_generated = analysis.get("improvements_generated", 0)
            logger.info(
                f"Skill improvement job completed: {improvements_generated} improvements generated"
            )

    except Exception as e:
        logger.exception(f"Skill improvement job error: {e}")


def job_listener(event):
    """Listen for job events."""
    if event.exception:
        logger.error(f"Job {event.job_id} crashed: {event.exception}")
    else:
        logger.debug(f"Job {event.job_id} executed successfully")


def init_scheduler() -> AsyncIOScheduler:
    """
    Initialize and configure the scheduler.

    Adds jobs:
    - skillsmp_sync: Hourly sync from SkillsMP API
    - skill_improvement: Daily analysis and improvement generation
    """
    scheduler = get_scheduler()

    # Add event listener
    scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    # Hourly SkillsMP sync (at minute 0 of every hour)
    scheduler.add_job(
        run_skillsmp_sync_job,
        CronTrigger(minute=0),  # Every hour at minute 0
        id="skillsmp_hourly_sync",
        name="SkillsMP Hourly Sync",
        replace_existing=True,
        misfire_grace_time=3600,  # 1 hour grace period
    )
    logger.info("Scheduled: skillsmp_hourly_sync (every hour at :00)")

    # Daily skill improvement (at 2:00 AM)
    scheduler.add_job(
        run_skill_improvement_job,
        CronTrigger(hour=2, minute=0),  # 2:00 AM daily
        id="skill_daily_improvement",
        name="Daily Skill Improvement",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info("Scheduled: skill_daily_improvement (daily at 2:00 AM)")

    return scheduler


def start_scheduler():
    """Start the scheduler."""
    scheduler = init_scheduler()

    if not scheduler.running:
        scheduler.start()
        logger.info("SkillsMP scheduler started")
    else:
        logger.info("SkillsMP scheduler already running")

    return scheduler


def stop_scheduler():
    """Stop the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
        logger.info("SkillsMP scheduler stopped")
        _scheduler = None


def get_job_status() -> dict:
    """Get status of scheduled jobs."""
    scheduler = get_scheduler()

    jobs = scheduler.get_jobs()
    job_info = []

    for job in jobs:
        job_info.append(
            {
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
        )

    return {
        "running": scheduler.running,
        "jobs": job_info,
        "timezone": str(scheduler.timezone) if scheduler.timezone else "UTC",
    }


# Backwards compatibility for existing code
async def run_hourly_sync_job():
    """Alias for run_skillsmp_sync_job."""
    await run_skillsmp_sync_job()
