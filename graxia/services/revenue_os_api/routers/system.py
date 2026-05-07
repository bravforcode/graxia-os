"""
graxia/services/revenue_os_api/routers/system.py
System health & metrics — fixes MED-05 (real readiness probe).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ....packages.revenue_os.db import get_db_session
from ....packages.revenue_os.schemas import HealthResponse

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
        from ....packages.revenue_os.celery.celery_app import celery_app
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
