import logging
from datetime import UTC, datetime
from datetime import timedelta as timedelta_cls

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import SchedulerNotRunningError
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.tasks.schedule import BEAT_SCHEDULE

logger = logging.getLogger(__name__)

BANGKOK = pytz.timezone("Asia/Bangkok")


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class PersonalOSScheduler:
    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler(timezone=BANGKOK)
        self._running = False

    def setup(self) -> None:
        for job_id, entry in BEAT_SCHEDULE.items():
            self.scheduler.add_job(
                self._dispatch_task,
                self._to_trigger(entry["schedule"]),
                args=[entry["task"]],
                id=job_id,
                replace_existing=True,
            )
        logger.info("Scheduler: %s jobs registered", len(BEAT_SCHEDULE))

    def start(self) -> None:
        self.scheduler.start()
        self._running = True
        logger.info("Scheduler: started")

    def stop(self) -> None:
        if not self._running:
            return
        try:
            self.scheduler.shutdown(wait=False)
        except SchedulerNotRunningError:
            logger.debug("Scheduler already stopped")
        finally:
            self._running = False

    @staticmethod
    def _to_trigger(schedule):
        if isinstance(schedule, timedelta_cls):
            return IntervalTrigger(seconds=int(schedule.total_seconds()), timezone=BANGKOK)
        
        # Map weekday names to 3-letter abbreviations for APScheduler
        day_of_week = str(schedule._orig_day_of_week)
        day_map = {
            "monday": "mon", "tuesday": "tue", "wednesday": "wed",
            "thursday": "thu", "friday": "fri", "saturday": "sat", "sunday": "sun"
        }
        if day_of_week.lower() in day_map:
            day_of_week = day_map[day_of_week.lower()]

        return CronTrigger(
            minute=str(schedule._orig_minute),
            hour=str(schedule._orig_hour),
            day=str(schedule._orig_day_of_month),
            month=str(schedule._orig_month_of_year),
            day_of_week=day_of_week,
            timezone=BANGKOK,
        )

    @staticmethod
    async def _dispatch_task(task_name: str) -> None:
        handlers = {
            "tasks.daily_scan.run": "app.tasks.daily_scan:run_daily_scan",
            "tasks.morning_briefing.run": "app.tasks.morning_briefing:send_morning_briefing",
            "tasks.follow_up_check.run": "app.tasks.follow_up_check:run_follow_up_check",
            "tasks.job_discovery.run": "app.tasks.job_discovery:run_job_discovery",
            "tasks.email_processing.run": "app.tasks.email_processing:run_email_processing",
            "tasks.weekly_review.run": "app.tasks.weekly_review:run_weekly_review",
            "tasks.maintenance.weekly_strategy": "app.tasks.maintenance_tasks:run_weekly_strategy",
            "tasks.maintenance.identity_snapshot": "app.tasks.maintenance_tasks:run_identity_snapshot",
            "tasks.maintenance.obsidian_daily_note": "app.tasks.maintenance_tasks:run_obsidian_daily_note",
            "tasks.maintenance.obsidian_refresh": "app.tasks.maintenance_tasks:run_obsidian_refresh",
            "tasks.maintenance.check_dlq_depth": "app.tasks.maintenance_tasks:check_dlq_depth",
            "tasks.backup.run_daily_backup": "app.tasks.backup_tasks:run_daily_backup_async",
            "tasks.backup.run_restore_drill": "app.tasks.backup_tasks:run_restore_drill_async",
            "tasks.backup.run_redis_backup": "app.tasks.backup_tasks:run_redis_backup_async",
        }
        target = handlers.get(task_name)
        if not target:
            logger.warning("No local dev scheduler handler registered for %s", task_name)
            return
        module_name, attr = target.split(":")
        module = __import__(module_name, fromlist=[attr])
        handler = getattr(module, attr)
        try:
            await handler()
        except Exception as exc:
            logger.error("Scheduled task %s failed: %s", task_name, exc, exc_info=True)


scheduler = PersonalOSScheduler()
