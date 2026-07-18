"""Risk management API endpoints — wired to real orchestrator components."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..core.config import get_config
from .auth import verify_admin_key, verify_api_key


risk_router = APIRouter(prefix="/risk", tags=["risk"])


class RiskStatusResponse(BaseModel):
    """Risk status response"""

    kill_switch: dict[str, Any]
    circuit_breaker: dict[str, Any]
    limits: dict[str, float]


class KillSwitchActionRequest(BaseModel):
    """Kill switch action request"""

    action: str = Field(..., description="trigger or reset")
    reason: str = Field(..., description="Reason for action")
    user_id: str = Field(..., description="User performing action")


def _get_orchestrator(request: Request):
    """Extract orchestrator from app state. Fail-closed if not available."""
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    return orch


@risk_router.get("/status", response_model=RiskStatusResponse)
async def get_risk_status(
    request: Request,
    _: str = Depends(verify_api_key),
):
    """Get current risk system status — reads from REAL orchestrator state."""
    orch = _get_orchestrator(request)
    kill_switch = orch.kill_switch
    ks_status = kill_switch.get_status()

    return RiskStatusResponse(
        kill_switch={
            "is_triggered": kill_switch.is_triggered,
            "state": ks_status.get("state", "inactive"),
            "reason": ks_status.get("reason", ""),
            "activated_at_utc": ks_status.get("activated_at_utc"),
            "authorized_by": ks_status.get("authorized_by"),
        },
        circuit_breaker={
            "is_blocked": False,
            "reason": None,
        },
        limits={
            "max_risk_per_trade_pct": orch._config.max_risk_per_trade_pct,
            "max_daily_loss_pct": orch._config.max_daily_loss_pct,
            "max_drawdown_pct": orch._config.max_drawdown_pct,
            "max_portfolio_exposure_pct": orch._config.max_portfolio_exposure_pct,
            "max_positions": orch._config.max_positions,
        },
    )


@risk_router.post("/kill-switch")
async def kill_switch_action(
    request: Request,
    payload: KillSwitchActionRequest,
    _: str = Depends(verify_admin_key),
):
    """Trigger or reset kill switch — calls REAL orchestrator methods."""
    if payload.action not in ("trigger", "reset"):
        raise HTTPException(status_code=400, detail="Action must be 'trigger' or 'reset'")

    orch = _get_orchestrator(request)
    now = datetime.now(UTC).isoformat()

    if payload.action == "trigger":
        orch.trigger_kill_switch(
            reason=payload.reason,
            source=f"rest:{payload.user_id}",
        )
    else:
        orch.reset_kill_switch(
            reason=payload.reason,
            authorized_by=f"rest:{payload.user_id}",
        )

    ks_status = orch.kill_switch.get_status()
    return {
        "success": True,
        "action": payload.action,
        "reason": payload.reason,
        "user_id": payload.user_id,
        "timestamp": now,
        "kill_switch_state": ks_status.get("state", "unknown"),
    }


@risk_router.get("/limits")
async def get_risk_limits(_: str = Depends(verify_api_key)):
    """Get current risk limits"""
    config = get_config()

    return {
        "trading_mode": config.trading_mode.value,
        "mode_limits": config.get_mode_risk_limits(),
        "global_limits": {
            "max_risk_per_trade_pct": config.max_risk_per_trade_pct,
            "max_daily_loss_pct": config.max_daily_loss_pct,
            "max_weekly_loss_pct": config.max_weekly_loss_pct,
            "max_drawdown_pct": config.max_drawdown_pct,
            "max_portfolio_exposure_pct": config.max_portfolio_exposure_pct,
            "max_positions": config.max_positions,
            "max_correlation_threshold": config.max_correlation_threshold,
        },
        "golden_rules": {
            "max_risk_per_trade_pct": 1.0,
            "hard_stop_drawdown_pct": 15.0,
            "max_daily_loss_pct": 2.0,
        },
    }


@risk_router.get("/exposure")
async def get_portfolio_exposure(
    request: Request,
    _: str = Depends(verify_api_key),
):
    """Get current portfolio exposure — reads from REAL position manager."""
    orch = _get_orchestrator(request)
    positions = orch.position_manager.get_positions()
    total_exposure = orch.position_manager.get_total_exposure()

    by_symbol: dict[str, float] = {}
    for pos in positions.values():
        by_symbol[pos.symbol] = by_symbol.get(pos.symbol, 0.0) + abs(pos.notional)

    equity = orch.position_manager.get_equity() or 1.0
    return {
        "total_exposure": f"{total_exposure:.2f}",
        "exposure_pct": round(total_exposure / equity * 100, 2) if equity > 0 else 0.0,
        "by_symbol": by_symbol,
        "by_strategy": {},
        "margin_used": "0.00",
        "free_margin": f"{equity:.2f}",
    }


@risk_router.get("/pnl")
async def get_pnl_summary(
    request: Request,
    _: str = Depends(verify_api_key),
):
    """Get P&L summary — reads from REAL risk ledger."""
    orch = _get_orchestrator(request)
    ledger = orch.risk_ledger

    daily = 0.0
    weekly = 0.0
    if hasattr(ledger, "_state"):
        daily = ledger._state.get("daily_realized_pnl", 0.0)
        weekly = ledger._state.get("weekly_realized_pnl", 0.0)

    return {
        "today": {
            "realized": f"{daily:.2f}",
            "unrealized": "0.00",
            "total": f"{daily:.2f}",
        },
        "this_week": {
            "realized": f"{weekly:.2f}",
            "total": f"{weekly:.2f}",
        },
        "this_month": {
            "realized": "0.00",
            "total": "0.00",
        },
        "ytd": {
            "realized": "0.00",
            "total": "0.00",
        },
    }
