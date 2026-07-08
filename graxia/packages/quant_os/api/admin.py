"""Admin API endpoints - requires authentication"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from ..core.config import get_config
from ..core.enums import TradingMode

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/admin", tags=["admin"])


async def verify_admin(
    api_key: str = Header(..., alias="X-Admin-Key"),
) -> bool:
    """Verify admin API key — delegates to shared ``verify_admin_key`` helper.

    Local definition (not re-exported from api.auth) so tests can
    patch ``api.admin.get_config`` and have it affect this function.
    """
    from .auth import verify_admin_key

    config = get_config()
    verify_admin_key(api_key, config.admin_api_key)
    return True


class ModeChangeRequest(BaseModel):
    """Request to change trading mode"""

    new_mode: TradingMode
    reason: str
    approved_by: str


class StrategyUpdateRequest(BaseModel):
    """Request to update strategy parameters"""

    strategy_id: str
    params: dict[str, Any]
    freeze_after_update: bool = True


@admin_router.post("/mode")
async def change_trading_mode(request: ModeChangeRequest, authorized: bool = Depends(verify_admin)):
    """
    Change system trading mode.

    Modes: RESEARCH_ONLY, BACKTEST_ONLY, SHADOW_MODE,
           PAPER_TRADING, LIVE_MICRO, LIVE_LIMITED, LIVE_CONTROLLED

    Requires explicit approval and reason.
    """
    config = get_config()

    # Validate mode transition
    valid_transitions = {
        TradingMode.PAPER: [TradingMode.LIVE_MICRO],
        TradingMode.LIVE_MICRO: [TradingMode.PAPER, TradingMode.LIVE_LIMITED],
        TradingMode.LIVE_LIMITED: [TradingMode.PAPER, TradingMode.LIVE_MICRO, TradingMode.LIVE_CONTROLLED],
    }

    current_mode = config.trading_mode
    allowed_next = valid_transitions.get(current_mode, [])

    if request.new_mode not in allowed_next and current_mode != request.new_mode:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode transition: {current_mode.value} → {request.new_mode.value}. "
            f"Allowed: {[m.value for m in allowed_next]}",
        )

    # Would update configuration (requires restart or hot-reload)
    return {
        "success": True,
        "previous_mode": current_mode.value,
        "new_mode": request.new_mode.value,
        "reason": request.reason,
        "approved_by": request.approved_by,
        "requires_restart": True,
        "message": f"Mode change to {request.new_mode.value} scheduled. Restart required.",
    }


@admin_router.get("/config")
async def get_config_endpoint(authorized: bool = Depends(verify_admin)):
    """Get current configuration (redacted)"""
    config = get_config()

    return {
        "trading_mode": config.trading_mode.value,
        "system_state": config.system_state.value,
        "live_trading_enabled": config.live_trading_enabled,
        "symbols": config.symbols,
        "primary_timeframe": config.primary_timeframe,
        "risk_limits": {
            "max_risk_per_trade_pct": config.max_risk_per_trade_pct,
            "max_daily_loss_pct": config.max_daily_loss_pct,
            "max_drawdown_pct": config.max_drawdown_pct,
        },
        "strategy_weights": config.strategy_weights,
    }


@admin_router.post("/strategy/update")
async def update_strategy(request: StrategyUpdateRequest, authorized: bool = Depends(verify_admin)):
    """Update strategy parameters"""
    return {
        "success": True,
        "strategy_id": request.strategy_id,
        "params_updated": request.params,
        "frozen": request.freeze_after_update,
        "message": "Strategy parameters updated. Backtest required for promotion.",
    }


@admin_router.post("/kill-switch/trigger")
async def admin_trigger_kill_switch(
    reason: str, user_id: str, close_positions: bool = True, authorized: bool = Depends(verify_admin)
):
    """Manually trigger kill switch"""
    from ..risk.kill_switch import KillSwitch

    ks = KillSwitch()
    ks.activate(reason=reason, source=f"admin:{user_id}")
    return {
        "success": True,
        "action": "trigger",
        "reason": reason,
        "triggered_by": user_id,
        "close_positions": close_positions,
        "requires_manual_reset": True,
        "message": "Kill switch triggered. All trading halted.",
    }


@admin_router.post("/kill-switch/reset")
async def admin_reset_kill_switch(reason: str, user_id: str, authorized: bool = Depends(verify_admin)):
    """Manually reset kill switch"""
    from ..risk.kill_switch import KillSwitch

    ks = KillSwitch()
    ks.deactivate(reason=reason, authorized_by=f"admin:{user_id}")
    return {
        "success": True,
        "action": "reset",
        "reason": reason,
        "reset_by": user_id,
        "message": "Kill switch reset. Trading resumed.",
    }


@admin_router.get("/audit-log")
async def get_audit_log(limit: int = 100, authorized: bool = Depends(verify_admin)):
    """Get recent audit log entries from kill switch state"""
    from ..risk.kill_switch import KillSwitch

    ks = KillSwitch()
    history = ks._state.get("history", [])[-limit:]
    return {"entries": history, "total": len(history), "limit": limit}


@admin_router.get("/system-stats")
async def get_system_stats(authorized: bool = Depends(verify_admin)):
    """Get detailed system statistics"""
    return {
        "orders": {
            "total_today": 0,
            "pending": 0,
            "filled": 0,
            "rejected": 0,
        },
        "positions": {
            "open_count": 0,
            "total_exposure": "0.00",
            "unrealized_pnl": "0.00",
        },
        "performance": {
            "today_pnl": "0.00",
            "this_week_pnl": "0.00",
            "win_rate": 0.0,
            "profit_factor": 0.0,
        },
        "risk": {
            "current_drawdown_pct": 0.0,
            "daily_loss_pct": 0.0,
            "kill_switch_active": False,
            "circuit_breaker_active": False,
        },
        "strategies": {
            "mtm": {"signals_today": 0, "win_rate": 0.0},
            "mrb": {"signals_today": 0, "win_rate": 0.0},
            "mlb": {"signals_today": 0, "win_rate": 0.0},
        },
    }
