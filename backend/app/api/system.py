from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, TypedDict, cast

from fastapi import APIRouter, Query
from sqlalchemy import desc, func, select

from app.config import settings
from app.core.advanced_health import health_checker as advanced_health_checker
from app.core.control_plane import create_run, mark_run_completed, mark_run_failed, mark_run_started
from app.core.event_bus import event_bus
from app.core.identity import WeightHistoryEntry, identity
from app.core.llm import llm_client
from app.core.redis_circuit_breaker import openclaw_circuit_breaker, redis_circuit_breaker
from app.core.redis_pool import redis_pool
from app.core.runtime_state import get_runtime_state
from app.database import AsyncSessionLocal
from app.models.assistant_task import AssistantTask
from app.models.audit import AuditLog
from app.models.automation_run import AutomationRun
from app.models.contact import Contact
from app.models.network_interaction import NetworkInteraction
from app.models.opportunity import Opportunity
from app.models.scraper_health import ScraperHealth
from app.tasks.queues import get_queue_depths

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


class StatsHistoryItem(TypedDict):
    name: str
    date: str
    leads: int
    outreach: int
    success: int
    failed: int


class StatsResponse(TypedDict):
    leads_scanned: int
    active_leads: int
    total_contacts: int
    opportunities_found: int
    ai_actions: int
    success_rate: float
    completed_24h: int
    failed_24h: int
    outreach_sent_24h: int
    active_ai_provider: str
    active_ai_model: str
    environment: str
    history: list[StatsHistoryItem]


def _active_ai_provider() -> str:
    if settings.HAS_REAL_OPENCLAW_KEY:
        base_url = (settings.OPENCLAW_BASE_URL or "").lower()
        if "openrouter" in base_url:
            return "OpenRouter"
        if "groq" in base_url:
            return "Groq"
        if "openclaw" in base_url:
            return "OpenClaw"
        return "OpenAI-compatible"
    if settings.HAS_REAL_GEMINI_KEY:
        return "Gemini"
    return "Not configured"


@router.get("/stats")
async def get_system_stats() -> StatsResponse:
    """
    Get real-time system statistics for the dashboard.
    Includes 7-day performance history.
    """
    async with AsyncSessionLocal() as db:
        now = datetime.now(UTC)
        yesterday = now - timedelta(hours=24)

        active_contacts = Contact.is_deleted.is_(False)
        total_contacts = int(
            await db.scalar(select(func.count(Contact.id)).where(active_contacts)) or 0
        )
        active_leads = int(
            await db.scalar(
                select(func.count(Contact.id)).where(
                    active_contacts,
                    func.lower(Contact.contact_type) == "lead",
                )
            )
            or 0
        )
        opportunities_found = int(
            await db.scalar(
                select(func.count(Opportunity.id)).where(Opportunity.is_deleted.is_(False))
            )
            or 0
        )

        run_total = int(await db.scalar(select(func.count(AutomationRun.id))) or 0)
        completed_runs = int(
            await db.scalar(
                select(func.count(AutomationRun.id)).where(AutomationRun.status == "completed")
            )
            or 0
        )
        failed_runs = int(
            await db.scalar(
                select(func.count(AutomationRun.id)).where(AutomationRun.status == "failed")
            )
            or 0
        )
        completed_tasks = int(
            await db.scalar(
                select(func.count(AssistantTask.id)).where(AssistantTask.status == "completed")
            )
            or 0
        )
        failed_tasks = int(
            await db.scalar(
                select(func.count(AssistantTask.id)).where(AssistantTask.status == "failed")
            )
            or 0
        )
        llm_actions = int(
            await db.scalar(
                select(func.count(AuditLog.id)).where(AuditLog.ai_model_used.is_not(None))
            )
            or 0
        )

        success_count = completed_runs + completed_tasks
        failed_count = failed_runs + failed_tasks
        denominator = success_count + failed_count
        success_rate = (success_count / denominator) * 100 if denominator else 0.0

        completed_24h = await db.scalar(
            select(func.count(AutomationRun.id)).where(
                AutomationRun.status == "completed",
                AutomationRun.updated_at >= yesterday,
            )
        )
        failed_24h = await db.scalar(
            select(func.count(AutomationRun.id)).where(
                AutomationRun.status == "failed",
                AutomationRun.updated_at >= yesterday,
            )
        )
        outreach_sent_24h = await db.scalar(
            select(func.count(NetworkInteraction.id)).where(
                NetworkInteraction.interaction_type.in_(
                    [
                        "email_outreach_initial",
                        "email_outreach_followup_1",
                        "email_outreach_followup_2",
                    ]
                ),
                NetworkInteraction.interaction_at >= yesterday,
            )
        )

        history: list[StatsHistoryItem] = []
        for i in range(6, -1, -1):
            target_date = now - timedelta(days=i)
            day_str = target_date.strftime("%a")
            start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = start_of_day + timedelta(days=1)

            day_completed = await db.scalar(
                select(func.count(AutomationRun.id)).where(
                    AutomationRun.status == "completed",
                    AutomationRun.updated_at >= start_of_day,
                    AutomationRun.updated_at < end_of_day,
                )
            )
            day_failed = await db.scalar(
                select(func.count(AutomationRun.id)).where(
                    AutomationRun.status == "failed",
                    AutomationRun.updated_at >= start_of_day,
                    AutomationRun.updated_at < end_of_day,
                )
            )
            day_leads = await db.scalar(
                select(func.count(Contact.id)).where(
                    active_contacts,
                    func.lower(Contact.contact_type) == "lead",
                    Contact.created_at >= start_of_day,
                    Contact.created_at < end_of_day,
                )
            )
            day_outreach = await db.scalar(
                select(func.count(NetworkInteraction.id)).where(
                    NetworkInteraction.interaction_type.in_(
                        [
                            "email_outreach_initial",
                            "email_outreach_followup_1",
                            "email_outreach_followup_2",
                        ]
                    ),
                    NetworkInteraction.interaction_at >= start_of_day,
                    NetworkInteraction.interaction_at < end_of_day,
                )
            )

            history.append(
                {
                    "name": day_str,
                    "date": target_date.date().isoformat(),
                    "leads": int(day_leads or 0),
                    "outreach": int(day_outreach or 0),
                    "success": int(day_completed or 0),
                    "failed": int(day_failed or 0),
                }
            )

        return {
            "leads_scanned": active_leads + opportunities_found,
            "active_leads": active_leads,
            "total_contacts": total_contacts,
            "opportunities_found": opportunities_found,
            "ai_actions": llm_actions + run_total,
            "success_rate": round(success_rate, 1),
            "completed_24h": int(completed_24h or 0),
            "failed_24h": int(failed_24h or 0),
            "outreach_sent_24h": int(outreach_sent_24h or 0),
            "active_ai_provider": _active_ai_provider(),
            "active_ai_model": llm_client.default_model,
            "environment": settings.APP_ENV,
            "history": history,
        }


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


class DetailedHealthResponse(TypedDict):
    status: str
    timestamp: str
    redis: dict[str, Any]
    circuit_breakers: dict[str, Any]
    queues: dict[str, int]
    llm: dict[str, Any]
    system_wide: dict[str, Any]


@router.get("/health/detailed")
async def health_detailed() -> DetailedHealthResponse:
    """Detailed health check with circuit breaker and pool status."""

    # Redis pool health
    redis_health = await redis_pool.health_status()

    # Circuit breaker states
    cb_states = {
        "redis": {
            "state": redis_circuit_breaker.get_state().value,
            "failure_count": redis_circuit_breaker._failure_count,
            "last_failure_time": redis_circuit_breaker._last_failure_time,
            "success_count": redis_circuit_breaker._success_count,
        },
        "openclaw": {
            "state": openclaw_circuit_breaker.get_state().value,
            "failure_count": openclaw_circuit_breaker._failure_count,
            "last_failure_time": openclaw_circuit_breaker._last_failure_time,
            "success_count": openclaw_circuit_breaker._success_count,
        }
    }

    # Queue depths
    try:
        queues = await get_queue_depths()
    except Exception:
        queues = {}

    # LLM status
    llm_status = {
        "degraded": llm_client.is_degraded(),
        "cost_paused": llm_client.is_cost_paused(),
        "using_openclaw": llm_client._using_openclaw(),
        "calls_today": await llm_client.get_call_count_today(),
    }

    # Determine overall status
    status = "healthy"
    if cb_states["redis"]["state"] == "OPEN" or cb_states["openclaw"]["state"] == "OPEN":
        status = "degraded"
    if llm_status["degraded"]:
        status = "degraded"

    return {
        "status": status,
        "timestamp": lambda: datetime.now(UTC)().isoformat(),
        "redis": redis_health,
        "circuit_breakers": cb_states,
        "queues": queues,
        "llm": llm_status,
        "system_wide": {
            "any_circuit_open": any(cb["state"] == "OPEN" for cb in cb_states.values()),
            "all_circuits_closed": all(cb["state"] == "CLOSED" for cb in cb_states.values()),
        }
    }


@router.post("/health/predictive-test")
async def predictive_test(request: dict[str, Any]) -> dict[str, Any]:
    """Test predictive alerting by injecting metrics."""

    service = request.get("service", "test")
    metrics = request.get("metrics", {})

    # Record metrics in health checker
    now = datetime.now(UTC)

    for metric_name, values in metrics.items():
        if isinstance(values, list):
            for value in values:
                if isinstance(value, (int, float)):
                    await advanced_health_checker.record_metric(
                        service, metric_name, float(value), now
                    )

    # Check for alerts
    alert_sent = False
    prediction = None

    try:
        result = await advanced_health_checker.check_service_health(service, metrics)
        if result and result.get("alert"):
            alert_sent = True
            prediction = result.get("prediction")
    except Exception as e:
        return {
            "error": str(e),
            "alert_sent": False,
            "prediction": None,
            "metrics_recorded": len(metrics)
        }

    return {
        "alert_sent": alert_sent,
        "prediction": prediction,
        "service": service,
        "metrics_recorded": sum(len(v) if isinstance(v, list) else 1 for v in metrics.values()),
        "timestamp": lambda: datetime.now(UTC)().isoformat(),
    }


@router.get("/resilience/status")
async def resilience_status() -> dict[str, Any]:
    """Get comprehensive resilience system status."""

    # Circuit breaker detailed status
    cb_status = {
        "redis": {
            "state": redis_circuit_breaker.get_state().value,
            "config": {
                "failure_threshold": redis_circuit_breaker._config.failure_threshold,
                "recovery_timeout": redis_circuit_breaker._config.recovery_timeout,
                "half_open_max_calls": redis_circuit_breaker._config.half_open_max_calls,
            },
            "stats": {
                "failure_count": redis_circuit_breaker._failure_count,
                "success_count": redis_circuit_breaker._success_count,
                "last_failure_time": redis_circuit_breaker._last_failure_time,
                "last_success_time": redis_circuit_breaker._last_success_time,
            }
        },
        "openclaw": {
            "state": openclaw_circuit_breaker.get_state().value,
            "config": {
                "failure_threshold": openclaw_circuit_breaker._config.failure_threshold,
                "recovery_timeout": openclaw_circuit_breaker._config.recovery_timeout,
                "half_open_max_calls": openclaw_circuit_breaker._config.half_open_max_calls,
            },
            "stats": {
                "failure_count": openclaw_circuit_breaker._failure_count,
                "success_count": openclaw_circuit_breaker._success_count,
                "last_failure_time": openclaw_circuit_breaker._last_failure_time,
                "last_success_time": openclaw_circuit_breaker._last_success_time,
            }
        }
    }

    # Redis pool status
    pool_status = {
        "initialized": redis_pool._initialized,
        "pool_config": {
            "max_connections": redis_pool._pool_config.max_connections if redis_pool._pool_config else None,
        },
        "health": await redis_pool.health_status(),
    }

    # Advanced health checker status
    health_status = {
        "services_monitored": list(advanced_health_checker.metric_history.keys()),
        "alert_cooldown": advanced_health_checker.alert_cooldown_seconds,
        "trend_window_size": advanced_health_checker.TREND_WINDOW_SIZE,
        "degradation_threshold": advanced_health_checker.DEGRADATION_THRESHOLD,
    }

    return {
        "timestamp": lambda: datetime.now(UTC)().isoformat(),
        "circuit_breakers": cb_status,
        "redis_pool": pool_status,
        "advanced_health": health_status,
        "overall_resilience_score": _calculate_resilience_score(cb_status, pool_status),
    }


def _calculate_resilience_score(cb_status: dict, pool_status: dict) -> int:
    """Calculate overall resilience score (0-100)."""
    score = 100

    # Deduct for open circuits
    for cb in cb_status.values():
        if cb["state"] == "OPEN":
            score -= 30
        elif cb["state"] == "HALF_OPEN":
            score -= 15

    # Deduct for unhealthy Redis
    if not pool_status.get("health", {}).get("healthy", False):
        score -= 25

    return max(0, score)
