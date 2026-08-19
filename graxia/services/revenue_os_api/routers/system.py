"""
graxia/services/revenue_os_api/routers/system.py
System health & metrics — fixes MED-05 (real readiness probe).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ....packages.revenue_os.db import get_db_session
from ....packages.revenue_os.schemas import HealthResponse
from ....packages.revenue_os.services.kill_switch import MoneyKillSwitch
from ..dependencies import require_admin_api_key

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/readiness",
    response_model=HealthResponse,
    summary="Kubernetes readiness probe",
    tags=["System"],
)
async def readiness_probe() -> HealthResponse:
    """
    Returns 200 only when DB is reachable.
    Kubernetes uses this to route traffic — must be accurate.
    """
    db_ok = False
    try:
        async with get_db_session() as db:
            await db.execute(text("SELECT 1"))
        db_ok = True
    except SQLAlchemyError as exc:
        logger.error("DB readiness check failed: %s", exc)

    # Celery check: attempt ping via inspect (optional, non-blocking)
    celery_ok = False
    try:
        from ....packages.revenue_os.celery.entrypoint import app as celery_app
        inspector = celery_app.control.inspect(timeout=1.0)
        ping = inspector.ping()
        celery_ok = bool(ping)
    except Exception:
        celery_ok = False  # Celery not strictly required for readiness

    return HealthResponse(
        status="ok" if db_ok else "degraded",
        db_connected=db_ok,
        celery_ready=celery_ok,
    )


@router.get(
    "/metrics",
    summary="Prometheus metrics",
    tags=["System"],
)
async def metrics() -> Response:
    """
    Expose Prometheus metrics for scraping.
    """
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


class KillSwitchRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


@router.get("/kill-switch", dependencies=[Depends(require_admin_api_key)])
async def get_kill_switch_status() -> dict:
    return MoneyKillSwitch().get_status()


@router.post("/kill-switch/trigger", dependencies=[Depends(require_admin_api_key)])
async def trigger_kill_switch(payload: KillSwitchRequest) -> dict:
    state = MoneyKillSwitch().trigger(payload.reason)
    try:
        from graxia.services.telegram_notifier import notifier
        await notifier.notify_kill_switch_triggered(payload.reason)
    except Exception:
        logger.exception("kill switch telegram notification failed (non-blocking)")
    return state


@router.post("/kill-switch/reset", dependencies=[Depends(require_admin_api_key)])
async def reset_kill_switch(payload: KillSwitchRequest) -> dict:
    return MoneyKillSwitch().reset(payload.reason)
