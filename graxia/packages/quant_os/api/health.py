"""
Health — system health and readiness endpoints.

GET /health          — lightweight liveness probe
GET /health/detailed — full SystemState snapshot (secrets redacted)
"""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Dict

import structlog
from fastapi import APIRouter, Request

from ..core.state_store import SystemState

logger = structlog.get_logger(__name__)

health_router = APIRouter(tags=["health"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REDACTED_KEYS = frozenset({
    "password", "secret", "token", "api_key", "hmac", "jwt",
    "mt5_password", "binance_secret", "telegram_bot_token",
    "admin_api_key", "webhook_hmac_secret", "jwt_secret_key",
})


def _redact_secrets(obj: Any) -> Any:
    """Recursively redact keys containing secret-like substrings."""
    if isinstance(obj, dict):
        return {
            k: "***REDACTED***" if any(s in k.lower() for s in _REDACTED_KEYS) else _redact_secrets(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_secrets(item) for item in obj]
    return obj


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@health_router.get("/health")
async def health_check(request: Request) -> Dict[str, Any]:
    """Lightweight liveness probe.

    Returns system state summary, uptime, position count, and queue depth.
    """
    start_time = getattr(request.app.state, "_start_time", None)
    uptime_s = time.monotonic() - start_time if start_time else -1.0

    # Queue depth from signal queue
    signal_queue = getattr(request.app.state, "signal_queue", None)
    queue_depth = signal_queue.qsize() if signal_queue else 0

    # DuckDB write queue depth
    write_queue = getattr(request.app.state, "duckdb_write_queue", None)
    write_queue_depth = 0
    if write_queue and hasattr(write_queue, "stats"):
        write_queue_depth = write_queue.stats.queue_depth

    # Event bus pending
    event_bus = getattr(request.app.state, "event_bus", None)
    event_bus_pending = event_bus.pending if event_bus else 0

    return {
        "status": "healthy",
        "uptime_s": round(uptime_s, 1),
        "signal_queue_depth": queue_depth,
        "write_queue_depth": write_queue_depth,
        "event_bus_pending": event_bus_pending,
    }


@health_router.get("/health/detailed")
async def health_detailed(request: Request) -> Dict[str, Any]:
    """Full SystemState snapshot with secrets redacted."""
    from ..core.config import get_settings

    settings = get_settings()
    start_time = getattr(request.app.state, "_start_time", None)
    uptime_s = time.monotonic() - start_time if start_time else -1.0

    # Build SystemState snapshot
    state = SystemState.default(environment=settings.ENVIRONMENT)

    # Queue depths
    signal_queue = getattr(request.app.state, "signal_queue", None)
    write_queue = getattr(request.app.state, "duckdb_write_queue", None)
    event_bus = getattr(request.app.state, "event_bus", None)

    # Gateway stats
    gateway = getattr(request.app.state, "signal_gateway", None)
    dedup_count = len(gateway._seen) if gateway else 0

    detailed: Dict[str, Any] = {
        "uptime_s": round(uptime_s, 1),
        "system_state": asdict(state),
        "signal_queue_depth": signal_queue.qsize() if signal_queue else 0,
        "write_queue_depth": write_queue.stats.queue_depth if write_queue and hasattr(write_queue, "stats") else 0,
        "write_queue_stats": {
            "total_enqueued": write_queue.stats.total_enqueued,
            "total_written": write_queue.stats.total_written,
            "total_flushes": write_queue.stats.total_flushes,
            "total_errors": write_queue.stats.total_errors,
            "last_flush_duration_ms": write_queue.stats.last_flush_duration_ms,
        } if write_queue and hasattr(write_queue, "stats") else {},
        "event_bus_pending": event_bus.pending if event_bus else 0,
        "dedup_window_active_signals": dedup_count,
        "environment": settings.ENVIRONMENT,
    }

    return _redact_secrets(detailed)
