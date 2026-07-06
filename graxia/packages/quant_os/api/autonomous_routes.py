"""Autonomous Trading Loop — health dashboard and control endpoints.

Exposes status, decisions, executions, statistics, and start/stop
controls for the autonomous trading orchestrator via FastAPI.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query

from ..autonomous.orchestrator import AutonomousOrchestrator, SystemHealth
from ..autonomous.persistence import TradeStore

logger = structlog.get_logger(__name__)

autonomous_router = APIRouter(prefix="/autonomous", tags=["autonomous"])

_orchestrator: AutonomousOrchestrator | None = None
_trade_store: TradeStore | None = None


def _get_orchestrator() -> AutonomousOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AutonomousOrchestrator()
    return _orchestrator


def _get_store() -> TradeStore:
    global _trade_store
    if _trade_store is None:
        _trade_store = TradeStore()
    return _trade_store


@autonomous_router.get("/status")
async def get_status() -> dict[str, Any]:
    """Get autonomous loop status."""
    if _orchestrator is None:
        return {"is_running": False, "message": "Orchestrator not started"}
    orch = _orchestrator
    health: SystemHealth = orch.get_status()
    return {
        "is_running": health.is_running,
        "uptime_seconds": health.uptime_seconds,
        "total_decisions": health.total_decisions,
        "total_trades": health.total_trades,
        "errors": health.errors,
        "consecutive_errors": health.consecutive_errors,
        "kill_switch_active": health.kill_switch_active,
        "last_snapshot_time": health.last_snapshot_time.isoformat() if health.last_snapshot_time else None,
        "last_trade_time": health.last_trade_time.isoformat() if health.last_trade_time else None,
    }


@autonomous_router.get("/decisions")
async def get_decisions(
    symbol: str | None = Query(None, description="Filter by symbol"),
    limit: int = Query(50, ge=1, le=500, description="Max results"),
) -> dict[str, Any]:
    """Get recent trade decisions."""
    store = _get_store()
    if symbol:
        rows = store.get_recent_decisions(symbol, limit=limit)
    else:
        conn = store._get_conn()
        rows = [dict(r) for r in conn.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]

    return {"count": len(rows), "decisions": rows}


@autonomous_router.get("/executions")
async def get_executions(
    limit: int = Query(50, ge=1, le=500, description="Max results"),
) -> dict[str, Any]:
    """Get execution log."""
    store = _get_store()
    rows = store.get_execution_log(limit=limit)
    return {"count": len(rows), "executions": rows}


@autonomous_router.get("/stats")
async def get_stats() -> dict[str, Any]:
    """Get daily trading statistics."""
    store = _get_store()
    conn = store._get_conn()
    row = conn.execute(
        "SELECT SUM(trades_today) as total_trades, SUM(realized_pnl) as total_pnl "
        "FROM daily_stats WHERE date = date('now')"
    ).fetchone()
    return {
        "trades_today": row["total_trades"] if row and row["total_trades"] else 0,
        "realized_pnl": row["total_pnl"] if row and row["total_pnl"] else 0.0,
    }


@autonomous_router.post("/start")
async def start_loop() -> dict[str, str]:
    """Start the autonomous loop."""
    orch = _get_orchestrator()
    try:
        await orch.start()
        return {"status": "started"}
    except Exception as exc:
        logger.error("autonomous_start_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to start: {exc}")


@autonomous_router.post("/stop")
async def stop_loop() -> dict[str, str]:
    """Stop the autonomous loop."""
    orch = _get_orchestrator()
    try:
        await orch.stop()
        return {"status": "stopped"}
    except Exception as exc:
        logger.error("autonomous_stop_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to stop: {exc}")
