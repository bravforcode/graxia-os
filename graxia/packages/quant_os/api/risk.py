"""Risk management API endpoints"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field

from ..core.config import get_config

security = HTTPBearer()


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


@risk_router.get("/status", response_model=RiskStatusResponse)
async def get_risk_status(credentials=Depends(security)):
    """Get current risk system status"""
    config = get_config()

    # These would be injected dependencies in real app
    kill_switch = None  # Would get from app state
    circuit_breaker = None

    return RiskStatusResponse(
        kill_switch={
            "is_triggered": kill_switch.is_triggered if kill_switch else False,
            "trigger_type": kill_switch.trigger_type.value if kill_switch and kill_switch.trigger_type else None,
        }
        if kill_switch
        else {"is_triggered": False},
        circuit_breaker={
            "is_blocked": circuit_breaker.is_blocked if circuit_breaker else False,
            "reason": circuit_breaker.reason if circuit_breaker else None,
        }
        if circuit_breaker
        else {"is_blocked": False},
        limits={
            "max_risk_per_trade_pct": config.max_risk_per_trade_pct,
            "max_daily_loss_pct": config.max_daily_loss_pct,
            "max_drawdown_pct": config.max_drawdown_pct,
            "max_portfolio_exposure_pct": config.max_portfolio_exposure_pct,
            "max_positions": config.max_positions,
        },
    )


@risk_router.post("/kill-switch")
async def kill_switch_action(request: KillSwitchActionRequest, credentials=Depends(security)):
    """Trigger or reset kill switch"""
    # This would integrate with actual kill switch

    if request.action not in ["trigger", "reset"]:
        raise HTTPException(status_code=400, detail="Action must be 'trigger' or 'reset'")

    # Would perform actual kill switch action
    return {
        "success": True,
        "action": request.action,
        "reason": request.reason,
        "user_id": request.user_id,
        "timestamp": "2024-01-01T00:00:00Z",
    }


@risk_router.get("/limits")
async def get_risk_limits(credentials=Depends(security)):
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
async def get_portfolio_exposure(credentials=Depends(security)):
    """Get current portfolio exposure"""
    # Would calculate from positions
    return {
        "total_exposure": "0.00",
        "exposure_pct": 0.0,
        "by_symbol": {},
        "by_strategy": {},
        "margin_used": "0.00",
        "free_margin": "100000.00",
    }


@risk_router.get("/pnl")
async def get_pnl_summary(credentials=Depends(security)):
    """Get P&L summary"""
    return {
        "today": {
            "realized": "0.00",
            "unrealized": "0.00",
            "total": "0.00",
        },
        "this_week": {
            "realized": "0.00",
            "total": "0.00",
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
