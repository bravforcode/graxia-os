from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, TypedDict, cast

from fastapi import APIRouter, Query
from sqlalchemy import desc, select

from app.core.event_bus import event_bus
from app.core.identity import WeightHistoryEntry, identity
from app.core.llm import llm_client
from app.core.runtime_state import get_runtime_state
from app.core.control_plane import create_run, mark_run_completed, mark_run_failed, mark_run_started
from app.database import AsyncSessionLocal
from app.models.audit import AuditLog
from app.models.scraper_health import ScraperHealth

router = APIRouter(prefix="/system", tags=["system"])

WeightHistoryLimit = Annotated[int, Query(ge=1, le=50)]
AuditLogLimit = Annotated[int, Query(ge=1, le=100)]
FallbackFilter = Annotated[bool | None, Query()]


class ScraperSummary(TypedDict):
    healthy: int
    total: int


class HealthResponse(TypedDict):
    status: str
    llm_degraded: bool
    llm_cost_paused: bool
    gemini_calls_today: int
    scraper_summary: ScraperSummary
    readiness: dict[str, Any]
    event_stats: dict[str, int]


class CostsResponse(TypedDict):
    cost_today_usd: float
    cost_month_usd: float
    calls_today: int
    cost_paused: bool
    llm_degraded: bool
    routing_enabled: bool
    max_single_call_cost_usd: float


class ScraperHealthItem(TypedDict):
    source_name: str
    last_attempted_at: str | None
    last_success_at: str | None
    consecutive_failures: int | None
    success_rate: float
    is_muted: bool | None
    muted_until: str | None
    avg_items_per_run: float
    last_error: str | None


class WeightsResponse(TypedDict):
    current: WeightHistoryEntry | None
    history: list[WeightHistoryEntry]


class RollbackNoopResponse(TypedDict):
    status: str
    message: str


class RollbackSuccessResponse(TypedDict):
    status: str
    restored_version: int
    weights: dict[str, float] | None


class AuditLogItem(TypedDict):
    id: str
    action: str
    entity_type: str | None
    entity_id: str | None
    details: dict[str, Any]
    triggered_by: str | None
    success: bool | None
    error_message: str | None
    ai_model_used: str | None
    was_fallback: bool | None
    created_at: str | None


class ReloadResponse(TypedDict):
    status: str


class StrategyResponse(TypedDict):
    status: str
    strategy: Any | None
    generated_at: str | None


class TriggerResponse(TypedDict):
    status: str
    run_id: str


@router.get("/health")
async def health() -> HealthResponse:
    call_count = await llm_client.get_call_count_today()
    readiness = get_runtime_state()
    try:
        async with AsyncSessionLocal() as db:
            scrapers = list(
                (await db.execute(select(ScraperHealth).order_by(ScraperHealth.source_name)))
                .scalars()
                .all()
            )
    except Exception:
        scrapers = []

    healthy_count = sum(1 for row in scrapers if not row.is_muted)
    mode = cast(str, readiness["mode"])
    status = mode if mode != "booting" else ("degraded" if not scrapers else "ok")
    return {
        "status": status,
        "llm_degraded": llm_client.is_degraded(),
        "llm_cost_paused": llm_client.is_cost_paused(),
        "gemini_calls_today": call_count,
        "scraper_summary": {
            "healthy": healthy_count,
            "total": len(scrapers),
        },
        "readiness": readiness,
        "event_stats": event_bus.get_event_stats(),
    }


@router.get("/costs")
async def costs() -> CostsResponse:
    router_summary = llm_client.get_router_summary()
    return {
        "cost_today_usd": llm_client.get_cost_today_usd(),
        "cost_month_usd": llm_client.get_cost_month_usd(),
        "calls_today": await llm_client.get_call_count_today(),
        "cost_paused": llm_client.is_cost_paused(),
        "llm_degraded": llm_client.is_degraded(),
        "routing_enabled": bool(router_summary["routing_enabled"]),
        "max_single_call_cost_usd": float(router_summary["max_single_call_cost_usd"]),
    }


@router.get("/scraper-health")
async def scraper_health() -> list[ScraperHealthItem]:
    try:
        async with AsyncSessionLocal() as db:
            rows = list(
                (await db.execute(select(ScraperHealth).order_by(ScraperHealth.source_name)))
                .scalars()
                .all()
            )
    except Exception:
        return []

    items: list[ScraperHealthItem] = []
    for row in rows:
        last_attempted_at: datetime | None = row.last_attempted_at
        last_success_at: datetime | None = row.last_success_at
        muted_until: datetime | None = row.muted_until
        success_rate: Decimal | None = row.success_rate
        avg_items_per_run: Decimal | None = row.avg_items_per_run

        items.append(
            {
                "source_name": row.source_name,
                "last_attempted_at": last_attempted_at.isoformat()
                if last_attempted_at is not None
                else None,
                "last_success_at": last_success_at.isoformat()
                if last_success_at is not None
                else None,
                "consecutive_failures": row.consecutive_failures,
                "success_rate": float(success_rate or 0),
                "is_muted": row.is_muted,
                "muted_until": muted_until.isoformat() if muted_until is not None else None,
                "avg_items_per_run": float(avg_items_per_run or 0),
                "last_error": row.last_error,
            }
        )

    return items


@router.get("/weights")
async def weights(limit: WeightHistoryLimit = 10) -> WeightsResponse:
    history = await identity.get_weight_history(limit=limit)
    current = next((row for row in history if row["is_current"]), None)
    return {
        "current": current,
        "history": history,
    }


@router.post("/weights/rollback")
async def rollback_weights() -> RollbackNoopResponse | RollbackSuccessResponse:
    result = await identity.rollback_scoring_weights()
    if result is None:
        return {"status": "noop", "message": "No previous weight version available"}

    return {
        "status": "rolled_back",
        "restored_version": result["restored_version"],
        "weights": result["weights"],
    }


@router.get("/audit-log")
async def audit_log(
    limit: AuditLogLimit = 20,
    was_fallback: FallbackFilter = None,
) -> list[AuditLogItem]:
    try:
        async with AsyncSessionLocal() as db:
            query = select(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit)
            if was_fallback is not None:
                query = query.where(AuditLog.was_fallback.is_(was_fallback))
            rows = list((await db.execute(query)).scalars().all())
    except Exception:
        return []

    items: list[AuditLogItem] = []
    for row in rows:
        entity_id = row.entity_id
        created_at = row.created_at
        details: dict[str, Any] = row.details or {}

        items.append(
            {
                "id": str(row.id),
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": str(entity_id) if entity_id is not None else None,
                "details": details,
                "triggered_by": row.triggered_by,
                "success": row.success,
                "error_message": row.error_message,
                "ai_model_used": row.ai_model_used,
                "was_fallback": row.was_fallback,
                "created_at": created_at.isoformat() if created_at is not None else None,
            }
        )

    return items


@router.post("/reload-identity")
async def reload_identity() -> ReloadResponse:
    identity.reload()
    return {"status": "reloaded"}


@router.get("/strategy")
async def strategy() -> StrategyResponse:
    try:
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(AuditLog)
                    .where(AuditLog.action == "strategy.generated")
                    .order_by(desc(AuditLog.created_at))
                    .limit(1)
                )
            ).scalar_one_or_none()
    except Exception:
        return {"status": "empty", "strategy": None, "generated_at": None}

    if row is None:
        return {"status": "empty", "strategy": None, "generated_at": None}

    details: dict[str, Any] = row.details or {}
    created_at = row.created_at
    return {
        "status": "ok",
        "strategy": details.get("strategy"),
        "generated_at": created_at.isoformat() if created_at is not None else None,
    }


@router.post("/scan")
@router.post("/scan/now")
async def trigger_scan() -> TriggerResponse:
    import asyncio

    from app.tasks.daily_scan import run_daily_scan

    run = await create_run(
        name="Manual daily scan",
        task_type="daily_scan",
        trigger_source="api",
        context={"route": "/api/v1/system/scan/now"},
    )

    async def _runner() -> None:
        try:
            await mark_run_started(run.id)
            result = await run_daily_scan()
            await mark_run_completed(run.id, result=result)
        except Exception as exc:
            await mark_run_failed(run.id, str(exc))

    asyncio.create_task(_runner())
    return {"status": "scan_triggered", "run_id": str(run.id)}


@router.post("/brief")
@router.post("/brief/now")
async def trigger_brief() -> TriggerResponse:
    import asyncio

    from app.agents.briefer import briefer_agent

    run = await create_run(
        name="Manual brief",
        task_type="morning_brief",
        trigger_source="api",
        context={"route": "/api/v1/system/brief/now"},
    )

    async def _runner() -> None:
        try:
            await mark_run_started(run.id)
            await briefer_agent.send_morning_brief()
            await mark_run_completed(run.id, result={"status": "sent"})
        except Exception as exc:
            await mark_run_failed(run.id, str(exc))

    asyncio.create_task(_runner())
    return {"status": "brief_triggered", "run_id": str(run.id)}
