"""
TradingView Webhook Handler

Receives signals from TradingView Pine Script via webhook.
Implements HMAC-SHA256 authentication to prevent unauthorized access.

Payload format:
{
    "action": "buy" | "sell",
    "symbol": "EURUSD",
    "price": 1.0850,
    "sl": 1.0820,
    "tp": 1.0910,
    "strategy": "mtm" | "mrb" | "mlb",
    "regime": "trend" | "range",
    "atr": 0.0020,
    "timestamp": 1234567890,
    "signature": "HMAC_SHA256_HEX"
}
"""

import hmac
import hashlib
import json
import time
from typing import Dict, Any, Optional
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Header, Request, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_config
from ..core.enums import SignalType, TradingMode
from ..core.exceptions import ValidationError, KillSwitchTriggeredError
from ..execution.manager import OrderManager
from ..execution.adapters.manager import BrokerManager
from ..risk.engine import RiskEngine
from ..risk.kill_switch import KillSwitch
from ..data.models import Signal as SignalModel

from graxia.packages.revenue_os.db import get_db as _get_db

webhook_router = APIRouter(prefix="/webhook", tags=["webhook"])


# Database dependency - use Revenue OS shared session
async def get_db():
    """Database session dependency - yields from shared pool"""
    async for session in _get_db():
        yield session


class TradingViewPayload(BaseModel):
    """TradingView webhook payload schema"""
    action: str = Field(..., description="buy or sell")
    symbol: str = Field(..., description="Trading symbol")
    price: float = Field(..., description="Entry price")
    sl: float = Field(..., description="Stop loss price")
    tp: float = Field(..., description="Take profit price")
    strategy: str = Field(default="ensemble", description="Strategy name")
    regime: str = Field(default="trend", description="Market regime")
    atr: float = Field(default=0.0, description="ATR value")
    timestamp: int = Field(default_factory=lambda: int(time.time()))

    class Config:
        json_schema_extra = {
            "example": {
                "action": "buy",
                "symbol": "EURUSD",
                "price": 1.0850,
                "sl": 1.0820,
                "tp": 1.0910,
                "strategy": "mtm",
                "regime": "trend",
                "atr": 0.0020,
                "timestamp": 1704067200
            }
        }


class WebhookResponse(BaseModel):
    """Webhook response"""
    success: bool
    signal_id: Optional[str] = None
    order_id: Optional[str] = None
    status: str
    message: str
    error: Optional[str] = None


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature"""
    if not secret:
        # No secret configured - allow (not recommended for production)
        return True

    if not signature:
        return False

    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(expected, signature)


@webhook_router.post("/tradingview", response_model=WebhookResponse)
async def tradingview_webhook(
    request: Request,
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
    db: AsyncSession = Depends(get_db)
):
    """
    Receive TradingView webhook signal.

    Authenticated via HMAC-SHA256 signature in X-Signature header.
    """
    config = get_config()

    # Read raw body for signature verification
    body = await request.body()

    # Verify signature
    if not verify_webhook_signature(body, x_signature or "", config.webhook_hmac_secret):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse payload
    try:
        data = json.loads(body)
        payload = TradingViewPayload(**data)
    except (json.JSONDecodeError, ValidationError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")

    # Validate timestamp (prevent replay attacks)
    current_time = int(time.time())
    if abs(current_time - payload.timestamp) > 60:
        raise HTTPException(status_code=400, detail="Request timestamp too old")

    # Convert to internal signal format
    try:
        signal_type = SignalType.BUY if payload.action.lower() == "buy" else SignalType.SELL
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid action: {payload.action}")

    # Record signal in database
    signal = SignalModel(
        strategy_id=payload.strategy,
        symbol=payload.symbol.upper(),
        signal_type=signal_type,
        confidence=0.75,  # TradingView signals have high confidence
        regime=payload.regime,
        indicator_values={
            "price": payload.price,
            "sl": payload.sl,
            "tp": payload.tp,
            "atr": payload.atr,
            "source": "tradingview"
        },
        raw_payload=data,
        received_at=datetime.utcnow()
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)

    # Initialize components
    broker_manager = BrokerManager.from_config()
    await broker_manager.initialize()

    risk_engine = RiskEngine(db_session=db)

    order_manager = OrderManager(
        db_session=db,
        broker_manager=broker_manager,
        risk_engine=risk_engine,
        kill_switch=None  # Would be injected
    )

    # Check if we should auto-trade
    if config.trading_mode in [TradingMode.PAPER, TradingMode.LIVE_MICRO,
                                TradingMode.LIVE_LIMITED, TradingMode.LIVE_CONTROLLED]:
        try:
            # Submit order
            from decimal import Decimal
            result = await order_manager.submit_order(
                symbol=payload.symbol.upper(),
                side=payload.action.upper(),
                order_type="MARKET",
                quantity=calculate_position_size(payload),  # Would calculate based on risk
                stop_price=Decimal(str(payload.sl)),
                strategy_id=payload.strategy,
                signal_id=str(signal.id)
            )

            if result.get("success"):
                signal.processed = True
                signal.order_id = result.get("order_id")
                signal.processed_at = datetime.utcnow()
                db.commit()

                return WebhookResponse(
                    success=True,
                    signal_id=str(signal.id),
                    order_id=result.get("order_id"),
                    status="submitted",
                    message="Signal received and order submitted"
                )
            else:
                signal.rejection_reason = result.get("error")
                db.commit()

                return WebhookResponse(
                    success=False,
                    signal_id=str(signal.id),
                    status="rejected",
                    message="Signal processed but order rejected",
                    error=result.get("error")
                )

        except KillSwitchTriggeredError as e:
            signal.rejection_reason = f"Kill switch: {e.switch_type}"
            db.commit()

            return WebhookResponse(
                success=False,
                signal_id=str(signal.id),
                status="blocked",
                message="Signal blocked by kill switch",
                error=str(e)
            )

    # Signal recorded but not auto-traded
    return WebhookResponse(
        success=True,
        signal_id=str(signal.id),
        status="recorded",
        message="Signal recorded for manual review"
    )


@webhook_router.post("/manual", response_model=WebhookResponse)
async def manual_signal(
    payload: TradingViewPayload,
    api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db)
):
    """
    Manual signal entry endpoint.
    For testing or manual strategy signals.
    """
    config = get_config()

    # Verify API key
    if api_key != config.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Record signal
    signal_type = SignalType.BUY if payload.action.lower() == "buy" else SignalType.SELL

    signal = SignalModel(
        strategy_id=f"manual_{payload.strategy}",
        symbol=payload.symbol.upper(),
        signal_type=signal_type,
        confidence=1.0,  # Manual signals have full confidence
        indicator_values={
            "price": payload.price,
            "sl": payload.sl,
            "tp": payload.tp,
            "source": "manual"
        },
        raw_payload=payload.dict(),
        received_at=datetime.utcnow()
    )
    db.add(signal)
    db.commit()

    return WebhookResponse(
        success=True,
        signal_id=str(signal.id),
        status="recorded",
        message="Manual signal recorded"
    )


def calculate_position_size(payload: TradingViewPayload) -> Decimal:
    """Calculate position size based on signal parameters"""
    from decimal import Decimal

    # Simplified - would use proper position sizing from risk engine
    config = get_config()

    # Default to 0.01 lot for testing
    # In production, calculate based on:
    # - Account balance
    # - Risk per trade
    # - SL distance
    # - Symbol pip value

    return Decimal("0.01")  # Minimum lot size
