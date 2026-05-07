import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.core.bootstrap import (
    check_system_ready,
    initialize_telegram_notifier,
    seed_admin_user,
    wire_event_handlers,
)
from app.core.event_bus import event_bus
from app.core.runtime_state import set_runtime_state
from app.core.swarm_bootstrap import (
    GRAXIA_ENABLED,
    initialize_graxia_components,
    message_bus,
    swarm,
)
from app.middleware.rate_limit import get_redis_client

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    logger.info("Personal OS starting up")
    set_runtime_state(False, "booting", [])

    try:
        redis_client = await get_redis_client()
        fastapi_app.state.redis = redis_client
    except Exception as e:
        logger.info(f"Redis connection failed (non-blocking): {e}")
        fastapi_app.state.redis = None
    event_loop_task = asyncio.create_task(event_bus.start_processing())
    scheduler = None
    telegram_task = None
    telegram_lock = None

    try:
        logger.info("Database initialization bypassed. Ensure `alembic upgrade head` is run before deployment.")

        wire_event_handlers()
        try:
            await seed_admin_user()
        except Exception as e:
            logger.warning(f"Seeding admin user failed (non-blocking): {e}")

        if not settings.TESTING:
            try:
                await initialize_telegram_notifier()
            except Exception as e:
                logger.warning(f"Telegram notifier failed: {e}")

        # Graxia OS Wakeup
        if GRAXIA_ENABLED and message_bus is not None and swarm is not None:
            try:
                await message_bus.connect()
                asyncio.create_task(swarm.listen_and_execute())
                logger.info("Graxia Swarm Engine Listeners Started.")
                fastapi_app.state.ingestion_pipeline = await initialize_graxia_components()
            except Exception as e:
                logger.error(f"Graxia Swarm Engine Wakeup Failed: {e}")
        else:
            logger.info("Graxia OS not enabled, skipping swarm initialization")

        if not settings.TESTING and settings.SCHEDULER_EMBEDDED:
            try:
                from app.core.scheduler import scheduler as runtime_scheduler

                runtime_scheduler.setup()
                runtime_scheduler.start()
                scheduler = runtime_scheduler
                logger.info("Runtime scheduler started")
            except Exception as exc:
                logger.warning("Runtime scheduler not started: %s", exc)

        if not settings.TESTING and settings.SKILLSMP_AUTO_SYNC:
            try:
                from app.jobs.scheduler import init_scheduler as init_skillsmp_scheduler

                skillsmp_scheduler = init_skillsmp_scheduler()
                skillsmp_scheduler.start()
                fastapi_app.state.skillsmp_scheduler = skillsmp_scheduler
                logger.info("SkillsMP scheduler started (hourly sync + daily improvement)")
            except Exception as exc:
                logger.warning("SkillsMP scheduler not started: %s", exc)
        if (
            not settings.TESTING
            and settings.TELEGRAM_POLLING_ENABLED
            and settings.HAS_REAL_TELEGRAM_TOKEN
        ):
            try:
                from app.core.telegram_lock import TelegramPollingSingletonLock
                from app.telegram_bot.bot import run_polling_forever

                if redis_client is not None:
                    telegram_lock = TelegramPollingSingletonLock(redis_client)
                    if await telegram_lock.acquire():
                        telegram_task = asyncio.create_task(run_polling_forever())
                        logger.info("Telegram polling started")
                    else:
                        logger.info("Telegram polling skipped: lock is already held")
                else:
                    logger.info("Telegram polling skipped: redis client unavailable")
            except Exception as exc:
                logger.warning("Telegram polling not started: %s", exc)
        is_ready, mode, issues = await check_system_ready()
        set_runtime_state(is_ready, mode, issues)
        logger.info("Startup readiness mode=%s issues=%s", mode, len(issues))
    except Exception as exc:
        set_runtime_state(False, "blocked", [str(exc)])
        logger.error("Startup error: %s", exc, exc_info=True)

    yield

    if hasattr(fastapi_app.state, "redis") and fastapi_app.state.redis:
        await fastapi_app.state.redis.close()

    if scheduler is not None:
        scheduler.stop()

    if hasattr(fastapi_app.state, "skillsmp_scheduler") and fastapi_app.state.skillsmp_scheduler:
        fastapi_app.state.skillsmp_scheduler.shutdown()
        logger.info("SkillsMP scheduler stopped")

    if telegram_task is not None:
        telegram_task.cancel()
        try:
            await telegram_task
        except asyncio.CancelledError:
            pass
    if telegram_lock is not None:
        await telegram_lock.release()

    if hasattr(fastapi_app.state, "ingestion_pipeline") and fastapi_app.state.ingestion_pipeline:
        await fastapi_app.state.ingestion_pipeline.stop()

    event_bus.stop()
    event_loop_task.cancel()
    try:
        await event_loop_task
    except asyncio.CancelledError:
        pass
    logger.info("Personal OS shut down")
