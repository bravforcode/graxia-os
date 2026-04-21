from __future__ import annotations

from typing import Annotated, Any, TypedDict

from fastapi import APIRouter, Depends, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.circuit_breaker import get_all_circuit_breakers
from app.core.monitoring import metrics_collector
from app.database import get_db
from app.models.audit import AuditLog
from app.tasks.celery_app import celery_app
from app.tasks.beat_lock import get_beat_lock_status
from app.tasks.dlq_handler import DeadLetterQueue
from app.tasks.queues import get_queue_depths

router = APIRouter(prefix="/admin", tags=["admin"])
DbSession = Annotated[AsyncSession, Depends(get_db)]


class AuditLogEntry(TypedDict):
    id: str
    event_type: str
    severity: str
    outcome: str
    user_id: str | None
    session_id: str | None
    ip_address: str | None
    request_path: str | None
    request_method: str | None
    metadata: dict[str, Any]
    checksum: str
    created_at: str | None


@router.get("/audit-logs")
async def get_audit_logs(db: DbSession, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    rows = list(
        (
            await db.execute(
                select(AuditLog).order_by(desc(AuditLog.created_at)).offset(offset).limit(limit)
            )
        ).scalars()
    )
    items: list[AuditLogEntry] = []
    for row in rows:
        items.append(
            {
                "id": str(row.id),
                "event_type": row.event_type,
                "severity": row.severity,
                "outcome": row.outcome,
                "user_id": str(row.user_id) if row.user_id else None,
                "session_id": row.session_id,
                "ip_address": row.ip_address,
                "request_path": row.request_path,
                "request_method": row.request_method,
                "metadata": row.metadata_json or {},
                "checksum": row.checksum,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/dlq")
async def list_dlq_messages(request: Request, offset: int = 0, limit: int = 20) -> dict[str, Any]:
    queue = DeadLetterQueue(getattr(request.app.state, "redis", None))
    messages = await queue.list_messages(offset=offset, limit=limit)
    return {
        "items": [
            {
                "message_id": item.message_id,
                "task_name": item.task_name,
                "original_queue": item.original_queue,
                "exception": item.exception,
                "failed_at": item.failed_at,
                "retries": item.retries,
            }
            for item in messages
        ],
        "depth": await queue.get_depth(),
    }


@router.post("/dlq/{message_id}/replay")
async def replay_dlq_message(message_id: str, request: Request) -> dict[str, Any]:
    operator_id = getattr(request.state, "authenticated_user_id", "admin")
    queue = DeadLetterQueue(getattr(request.app.state, "redis", None))
    success = await queue.replay_message(message_id, operator_id=operator_id)
    return {"status": "replayed" if success else "missing", "message_id": message_id}


@router.get("/runtime")
async def get_runtime_state(request: Request) -> dict[str, Any]:
    redis_client = getattr(request.app.state, "redis", None)
    beat = await get_beat_lock_status(redis_client)
    queue_depths = await get_queue_depths(redis_client, use_pool_fallback=False)
    for queue_name, depth in queue_depths.items():
        metrics_collector.set_queue_depth(queue_name, depth)
    active_workers: dict[str, Any] = {}
    try:
        inspect = celery_app.control.inspect(timeout=1.0)
        active_workers = inspect.ping() or {}
    except Exception:
        active_workers = {}
    metrics_collector.set_workers_online(len(active_workers))
    return {
        "beat_lock": {"owner": beat.owner, "ttl_seconds": beat.ttl_seconds},
        "queue_depths": queue_depths,
        "workers_online": len(active_workers),
        "circuit_breakers": get_all_circuit_breakers(),
    }
