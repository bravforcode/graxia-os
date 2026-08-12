"""Ai Factory — slim store API for Vercel (serverless).

Mounts only the funnel/commerce stack of Graxia OS (products, checkout,
Stripe webhooks, delivery, lead magnets, analytics, AI recommendations,
automation, auth). Same middleware chain as app.main — but WITHOUT the
heavy imports (scrapers, ML, graphql, orchestrators, websockets) so the
function stays small and cold starts fast.

- WebSockets / Graxia swarm are intentionally not mounted (GRAXIA_ENABLED=false
  in the store deployment; Vercel Python does not support WebSockets).
- Celery is not used: automation scans run from cron-job.org pings to
  /internal/funnel/process-due plus a best-effort in-process APScheduler.
"""
import logging
import os
import sys
from contextlib import asynccontextmanager

# Make `backend/` importable as `app.*`
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from fastapi import FastAPI, Request, Response, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.config import settings  # noqa: E402
from app.core.exception_handlers import register_exception_handlers  # noqa: E402
from app.core.logging_config import setup_logging  # noqa: E402
from app.core.request_context import RequestContextMiddleware  # noqa: E402
from app.core.runtime_state import set_runtime_state  # noqa: E402
from app.auth.middleware import AuthContextMiddleware  # noqa: E402
from app.middleware.auth import AuthMiddleware  # noqa: E402
from app.middleware.rate_limit import RateLimitMiddleware  # noqa: E402
from app.core.security_hardening import (  # noqa: E402
    IPFilterMiddleware,
    RequestSanitizationMiddleware,
)
from app.middleware.security import (  # noqa: E402
    CSRFMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)

# ── Store-scope routers ────────────────────────────────────────────────────
from app.api.funnel_products import router as funnel_products_router  # noqa: E402
from app.api.funnel_webhooks import router as funnel_webhooks_router  # noqa: E402
from app.api.funnel_delivery import router as funnel_delivery_router  # noqa: E402
from app.api.lead_magnets import router as lead_magnets_router  # noqa: E402
from app.api.funnel_analytics import router as funnel_analytics_router  # noqa: E402
from app.api.funnel_ai import router as funnel_ai_router  # noqa: E402
from app.api.funnel_automation import router as funnel_automation_router  # noqa: E402
from app.api.auth import router as auth_router  # noqa: E402

setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    set_runtime_state(False, "booting", [])
    try:
        from app.core.bootstrap import seed_admin_user, wire_event_handlers

        wire_event_handlers()
        await seed_admin_user()

        # Best-effort in-process scheduler (Vercel may reclaim instances; the
        # cron-job.org ping is the reliable trigger for automation scans).
        global _scheduler
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            from app.tasks.funnel_automation_runtime import process_all_due

            _scheduler = AsyncIOScheduler(timezone="Asia/Bangkok")
            _scheduler.add_job(
                process_all_due,
                trigger="interval",
                minutes=15,
                id="funnel-automation",
                coalesce=True,
                max_instances=1,
            )
            _scheduler.start()
            logger.info("Embedded funnel automation scheduler started")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Embedded scheduler unavailable: {exc}")

        set_runtime_state(True, "running", [])
        logger.info("Ai Factory store API started (serverless)")
    except Exception as exc:  # noqa: BLE001
        set_runtime_state(False, "blocked", [str(exc)])
        logger.error(f"Startup error: {exc}", exc_info=True)
    yield
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            pass


app = FastAPI(
    title="Ai Factory Store API",
    description="Digital products store (Stripe checkout, delivery, funnel automation)",
    version="1.0.0",
    docs_url=None if settings.STRICT_BOOTSTRAP else "/docs",
    redoc_url=None if settings.STRICT_BOOTSTRAP else "/redoc",
    openapi_url=None if settings.STRICT_BOOTSTRAP else "/openapi.json",
    lifespan=lifespan,
)

register_exception_handlers(app)

# ── Middleware (same order as app.main) ────────────────────────────────────
app.add_middleware(RequestSanitizationMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(AuthContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
ip_whitelist = [i.strip() for i in settings.IP_WHITELIST.split(",") if i.strip()] if settings.IP_WHITELIST else []
ip_blacklist = [i.strip() for i in settings.IP_BLACKLIST.split(",") if i.strip()] if settings.IP_BLACKLIST else []
app.add_middleware(IPFilterMiddleware, whitelist=ip_whitelist, blacklist=ip_blacklist)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes (prefixes mirror app/api/router.py exactly) ─────────────────────
app.include_router(auth_router)  # paths already include /api/v1
app.include_router(funnel_products_router, prefix="/api/v1/funnel")
app.include_router(funnel_webhooks_router, prefix="/api/v1/funnel/webhooks")
app.include_router(funnel_delivery_router, prefix="/api/v1/funnel")
app.include_router(lead_magnets_router, prefix="/api/v1")
app.include_router(funnel_analytics_router, prefix="/api/v1/funnel")
app.include_router(funnel_ai_router, prefix="/api/v1/funnel")
app.include_router(funnel_automation_router, prefix="/api/v1/funnel")


@app.post("/internal/funnel/process-due")
async def process_due(request: Request):
    """Cron bridge: cron-job.org pings this every 15 min to run automation scans.

    Guarded by X-Internal-Token (settings.INTERNAL_METRICS_TOKEN).
    """
    token = request.headers.get("X-Internal-Token", "")
    expected = settings.INTERNAL_API_KEY
    if not expected or token != expected:
        raise HTTPException(status_code=403, detail="Forbidden")

    from app.tasks.funnel_automation_runtime import process_all_due

    result = await process_all_due()
    return {"status": "ok", "processed": result}


@app.get("/health")
async def health():
    from app.core.runtime_state import get_runtime_state

    readiness = get_runtime_state()
    return {
        "status": "ok" if readiness["is_ready"] else "degraded",
        "service": "Ai Factory Store API",
        "readiness": readiness,
    }


@app.get("/")
async def root():
    return {"service": "Ai Factory Store API", "docs": "/docs"}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
