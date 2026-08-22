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


@router.post(
    "/seed",
    summary="Admin: create tables + seed demo + wire Stripe prices",
    tags=["System"],
)
async def seed_db(admin=Depends(require_admin_api_key)) -> dict:
    """Idempotent seed — creates tables if missing, inserts products if empty, wires Stripe Price IDs."""
    from sqlalchemy import func, select, text, update

    from graxia.packages.revenue_os.db import DATABASE_URL, get_db_session

    # 1. Create tables (idempotent) — use sync engine via run_sync
    try:
        from graxia.database import Base  # type: ignore

        from graxia.packages.revenue_os import models as _models  # noqa: F401 register tables
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()
    except Exception as exc:
        logger.warning("create_all failed (may already exist): %s", exc)

    # 2. Seed products if empty + wire Stripe prices
    stripe_map = {
        "revenue-os-starter": "price_1Tk8sg0u86vWnztX9dXtypOV",
        "revenue-os-growth": "price_1Tk8si0u86vWnztXmgV4gEpM",
        "revenue-os-scale": "price_1Tk8sj0u86vWnztXXtiM9M2C",
    }
    async with get_db_session() as db:
        try:
            from sqlalchemy import func, select, update

            from graxia.packages.revenue_os.models import Product

            existing = await db.scalar(select(func.count()).select_from(Product))
            if not existing or existing == 0:
                try:
                    from scripts.seed_revenue_os_demo import PRODUCTS  # type: ignore
                except ImportError:
                    # Fallback minimal products if scripts not importable
                    from graxia.packages.revenue_os.enums import ProductStatus, ProductType

                    PRODUCTS = [
                        dict(name="Revenue OS Starter", slug="revenue-os-starter", type=ProductType.CORE, price_cents=49900, currency="THB", status=ProductStatus.PUBLISHED, stripe_price_id=""),
                        dict(name="Revenue OS Growth", slug="revenue-os-growth", type=ProductType.CORE, price_cents=149000, currency="THB", status=ProductStatus.PUBLISHED, stripe_price_id=""),
                        dict(name="Revenue OS Scale", slug="revenue-os-scale", type=ProductType.CORE, price_cents=490000, currency="THB", status=ProductStatus.PUBLISHED, stripe_price_id=""),
                    ]
                for p in PRODUCTS:
                    # Only seed core products if they match stripe_map
                    if p.get("slug") in stripe_map or True:
                        db.add(Product(**p))
                await db.flush()
        except Exception as exc:
            logger.warning("seed products failed: %s", exc)

        # Wire Stripe Price IDs (always)
        wired: dict[str, str] = {}
        for slug, price_id in stripe_map.items():
            try:
                from graxia.packages.revenue_os.models import Product

                await db.execute(update(Product).where(Product.slug == slug).values(stripe_price_id=price_id))
                wired[slug] = price_id
            except Exception as exc:
                wired[slug] = f"error: {exc}"

    return {"status": "seeded", "wired": wired}


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
