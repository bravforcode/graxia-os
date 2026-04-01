import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

logger = logging.getLogger(__name__)

BANGKOK = pytz.timezone("Asia/Bangkok")


class PersonalOSScheduler:
    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler(timezone=BANGKOK)
        self._running = False

    def setup(self) -> None:
        # Daily scan — 7:00 AM Bangkok
        self.scheduler.add_job(
            self._run_daily_scan,
            CronTrigger(hour=7, minute=0, timezone=BANGKOK),
            id="daily_scan",
            replace_existing=True,
        )
        # Follow-up check — 9:00 AM Bangkok
        self.scheduler.add_job(
            self._run_follow_up_check,
            CronTrigger(hour=9, minute=0, timezone=BANGKOK),
            id="follow_up_check",
            replace_existing=True,
        )
        # Weekly strategy — Sunday 8:30 AM Bangkok
        self.scheduler.add_job(
            self._run_weekly_strategy,
            CronTrigger(day_of_week="sun", hour=8, minute=30, timezone=BANGKOK),
            id="weekly_strategy",
            replace_existing=True,
        )
        # Weekly learning — Sunday 9:30 AM Bangkok
        self.scheduler.add_job(
            self._run_weekly_learning,
            CronTrigger(day_of_week="sun", hour=9, minute=30, timezone=BANGKOK),
            id="weekly_learning",
            replace_existing=True,
        )
        # Monthly identity snapshot — 1st of month, 10:00 AM
        self.scheduler.add_job(
            self._run_identity_snapshot,
            CronTrigger(day=1, hour=10, minute=0, timezone=BANGKOK),
            id="identity_snapshot",
            replace_existing=True,
        )
        logger.info("Scheduler: 5 jobs registered")

    def start(self) -> None:
        self.scheduler.start()
        self._running = True
        logger.info("Scheduler: started")

    def stop(self) -> None:
        self.scheduler.shutdown(wait=False)
        self._running = False

    @staticmethod
    async def _run_daily_scan() -> None:
        try:
            from app.tasks.daily_scan import run_daily_scan
            await run_daily_scan()
        except Exception as e:
            logger.error(f"Daily scan failed: {e}", exc_info=True)

    @staticmethod
    async def _run_follow_up_check() -> None:
        try:
            from app.tasks.follow_up_check import run_follow_up_check
            await run_follow_up_check()
        except Exception as e:
            logger.error(f"Follow-up check failed: {e}", exc_info=True)

    @staticmethod
    async def _run_weekly_strategy() -> None:
        try:
            from app.agents.strategy_agent import StrategyAgent
            agent = StrategyAgent()
            await agent.run()
        except Exception as e:
            logger.error(f"Weekly strategy failed: {e}", exc_info=True)

    @staticmethod
    async def _run_weekly_learning() -> None:
        try:
            from app.tasks.weekly_review import run_weekly_review
            await run_weekly_review()
        except Exception as e:
            logger.error(f"Weekly learning failed: {e}", exc_info=True)

    @staticmethod
    async def _run_identity_snapshot() -> None:
        try:
            from app.core.identity import identity
            await identity.maybe_snapshot_identity()
        except Exception as e:
            logger.error(f"Identity snapshot failed: {e}", exc_info=True)


scheduler = PersonalOSScheduler()
