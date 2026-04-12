import asyncio
import logging
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.api.admin import router as admin_router
from app.api.approvals import router as approvals_router
from app.api.auth import router as auth_router
from app.api.calendar import router as calendar_router
from app.api.commands import router as commands_router
from app.api.contacts import router as contacts_router
from app.api.cognitive import router as cognitive_router
from app.api.costs import router as costs_router
from app.api.drafts import router as drafts_router
from app.api.email_threads import router as email_threads_router
from app.api.events import router as events_router
from app.api.inbox import router as inbox_router
from app.api.integrations import router as integrations_router
from app.api.jobs import router as jobs_router
from app.api.metrics import router as metrics_router
from app.api.opportunities import router as opportunities_router
from app.api.runs import router as runs_router
from app.api.obsidian import router as obsidian_router
from app.api.scrapers import router as scrapers_router
from app.api.skills import router as skills_router
from app.api.submissions import router as submissions_router
from app.api.system import router as system_router
from app.api.tasks import router as tasks_router
from app.config import settings
from app.cqrs.setup import setup_cqrs
from app.core.event_bus import event_bus
from app.core.monitoring import metrics_collector
from app.core.runtime_state import get_runtime_state, set_runtime_state
from app.middleware.auth import AuthMiddleware
from app.middleware.rate_limit import RateLimitMiddleware, get_redis_client
from app.middleware.security import (
    CSRFMiddleware,
    InputSanitizationMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.tasks.beat_lock import get_beat_lock_status
from app.tasks.celery_app import celery_app
from app.tasks.dlq_handler import DeadLetterQueue
from app.tasks.queues import get_queue_depths

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

setup_cqrs()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Personal OS starting up")
    set_runtime_state(False, "booting", [])

    settings.validate_production_configuration()
    redis_client = await get_redis_client()
    app.state.redis = redis_client
    event_loop_task = asyncio.create_task(event_bus.start_processing())
    scheduler = None

    try:
        from app.core.bootstrap import check_system_ready, wire_event_handlers
        from app.agents.obsidian_sync import obsidian_sync_agent

        wire_event_handlers()
        if "pytest" not in sys.modules and settings.SCHEDULER_EMBEDDED:
            try:
                from app.core.scheduler import scheduler as runtime_scheduler

                runtime_scheduler.setup()
                runtime_scheduler.start()
                scheduler = runtime_scheduler
                logger.info("Runtime scheduler started")
            except Exception as exc:
                logger.warning("Runtime scheduler not started: %s", exc)
        if settings.OBSIDIAN_AUTO_BOOTSTRAP:
            try:
                await obsidian_sync_agent.bootstrap_second_brain()
                logger.info("Obsidian second brain bootstrapped")
            except Exception as exc:
                logger.warning("Obsidian bootstrap skipped: %s", exc)
        is_ready, mode, issues = await check_system_ready()
        set_runtime_state(is_ready, mode, issues)
        logger.info("Startup readiness mode=%s issues=%s", mode, len(issues))
    except Exception as exc:
        set_runtime_state(False, "blocked", [str(exc)])
        logger.error("Startup error: %s", exc, exc_info=True)

    yield

    if hasattr(app.state, "redis") and app.state.redis:
        await app.state.redis.close()

    if scheduler is not None:
        scheduler.stop()

    event_bus.stop()
    event_loop_task.cancel()
    try:
        await event_loop_task
    except asyncio.CancelledError:
        pass
    logger.info("Personal OS shut down")


app = FastAPI(
    title="Personal Sovereign Enterprise OS",
    description="Canonical API for the Personal OS control plane",
    version="3.0.0",
    lifespan=lifespan,
    docs_url=None if settings.STRICT_BOOTSTRAP else "/docs",
    redoc_url=None if settings.STRICT_BOOTSTRAP else "/redoc",
    openapi_url=None if settings.STRICT_BOOTSTRAP else "/openapi.json",
)


@app.middleware("http")
async def add_metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    metrics_collector.record_http_request(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code,
        duration=duration,
    )
    response.headers["X-Process-Time"] = str(duration)
    return response


# Middleware order is outermost-last. Keep rate limiting ahead of auth and CSRF.
app.add_middleware(CSRFMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(InputSanitizationMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router, prefix="/api/v1")
app.include_router(approvals_router, prefix="/api/v1")
app.include_router(calendar_router, prefix="/api/v1")
app.include_router(commands_router, prefix="/api/v1")
app.include_router(opportunities_router, prefix="/api/v1")
app.include_router(contacts_router, prefix="/api/v1")
app.include_router(drafts_router, prefix="/api/v1")
app.include_router(metrics_router, prefix="/api/v1")
app.include_router(cognitive_router, prefix="/api/v1")
app.include_router(submissions_router, prefix="/api/v1")
app.include_router(system_router, prefix="/api/v1")
app.include_router(inbox_router, prefix="/api/v1")
app.include_router(integrations_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(runs_router, prefix="/api/v1")
app.include_router(email_threads_router)
app.include_router(obsidian_router)
app.include_router(skills_router, prefix="/api/v1")
app.include_router(tasks_router)
app.include_router(costs_router)
app.include_router(events_router)
app.include_router(scrapers_router)


@app.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    await metrics_collector.update_gauges()
    queue_depths = await get_queue_depths(getattr(app.state, "redis", None))
    for queue_name, depth in queue_depths.items():
        metrics_collector.set_queue_depth(queue_name, depth)
    dlq = DeadLetterQueue(getattr(app.state, "redis", None))
    metrics_collector.set_dlq_depth(await dlq.get_depth())
    try:
        inspect = celery_app.control.inspect(timeout=1.0)
        workers = inspect.ping() or {}
    except Exception:
        workers = {}
    metrics_collector.set_workers_online(len(workers))
    await get_beat_lock_status(getattr(app.state, "redis", None))
    return metrics_collector.export_metrics()


@app.get("/health")
async def root_health():
    readiness = get_runtime_state()
    return {
        "status": "ok" if readiness["is_ready"] else "degraded",
        "service": "Personal OS API",
        "readiness": readiness,
    }


@app.get("/")
async def root():
    return {
        "service": "Personal OS API",
        "version": app.version,
        "docs": "/docs",
        "health": "/health",
        "frontend": settings.FRONTEND_URL,
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)
