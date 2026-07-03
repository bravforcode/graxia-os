"""
Webhook Receiver — TradingView and generic signal ingestion endpoints.

POST /webhook/tradingview  — authenticated via TV_WEBHOOK_SECRET header
POST /webhook/generic      — authenticated via X-API-Key header
"""

from __future__ import annotations

import hmac as _hmac
from typing import Any, Dict, Optional

import structlog
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from ..core.config import get_settings
from ..core.signal_gateway import AssetClass, SignalSource

logger = structlog.get_logger(__name__)

webhook_router = APIRouter(prefix="/webhook", tags=["webhook"])


# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------


class TradingViewAlert(BaseModel):
    """TradingView webhook payload schema."""

    symbol: str = Field(..., min_length=1, max_length=20, description="Trading symbol")
    action: str = Field(..., description="buy | sell | exit")
    price: float = Field(..., gt=0, description="Entry price")
    sl: float = Field(..., gt=0, description="Stop loss price")
    tp: float = Field(..., gt=0, description="Take profit price")
    strategy: str = Field(default="tradingview", min_length=1, max_length=100)
    regime: Optional[str] = None
    asset_class: str = Field(default="forex", description="metals|crypto|forex|indices")
    conviction: float = Field(default=0.75, ge=0.0, le=1.0)
    timestamp: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        allowed = {"buy", "sell", "exit"}
        v_lower = v.lower()
        if v_lower not in allowed:
            raise ValueError(f"action must be one of {allowed}, got '{v}'")
        return v_lower

    @field_validator("asset_class")
    @classmethod
    def validate_asset_class(cls, v: str) -> str:
        allowed = {e.value for e in AssetClass}
        v_lower = v.lower()
        if v_lower not in allowed:
            raise ValueError(f"asset_class must be one of {allowed}, got '{v}'")
        return v_lower


class GenericWebhookPayload(BaseModel):
    """Generic webhook payload for non-TV sources."""

    symbol: str = Field(..., min_length=1, max_length=20)
    asset_class: str = Field(...)
    side: str = Field(..., description="BUY | SELL")
    conviction: float = Field(..., ge=0.0, le=1.0)
    strategy: str = Field(..., min_length=1, max_length=100)
    entry_price: float = Field(..., gt=0)
    stop_loss: float = Field(..., gt=0)
    take_profit: float = Field(..., gt=0)
    regime: Optional[str] = None
    source: str = Field(default="generic", description="Signal source identifier")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("asset_class")
    @classmethod
    def validate_asset_class(cls, v: str) -> str:
        allowed = {e.value for e in AssetClass}
        v_lower = v.lower()
        if v_lower not in allowed:
            raise ValueError(f"asset_class must be one of {allowed}, got '{v}'")
        return v_lower

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        allowed = {"BUY", "SELL"}
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"side must be one of {allowed}, got '{v}'")
        return v_upper


class WebhookResponse(BaseModel):
    """Standard webhook response."""

    success: bool
    signal_id: Optional[str] = None
    status: str
    message: str
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@webhook_router.post("/tradingview", response_model=WebhookResponse)
async def tradingview_webhook(
    request: Request,
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
) -> WebhookResponse:
    """Receive TradingView alert, validate secret, ingest via SignalGateway."""
    settings = get_settings()

    # Authenticate — fail-closed: reject if secret is not configured
    tv_secret = getattr(settings, "TV_WEBHOOK_SECRET", "")
    if not tv_secret:
        logger.warning("webhook.tv.no_secret_configured")
        raise HTTPException(status_code=503, detail="Webhook secret not configured")
    if not x_webhook_secret or not _hmac.compare_digest(x_webhook_secret, tv_secret):
        logger.warning("webhook.tv.auth_failed")
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # Parse
    try:
        body = await request.json()
        alert = TradingViewAlert(**body)
    except Exception as exc:
        logger.warning("webhook.tv.parse_error", error=str(exc))
        raise HTTPException(status_code=400, detail=f"Invalid payload: {exc}")

    # Map action to side
    side = "BUY" if alert.action == "buy" else "SELL" if alert.action == "sell" else "EXIT"

    # Build raw signal dict for SignalGateway
    raw_signal = {
        "symbol": alert.symbol.upper(),
        "asset_class": alert.asset_class,
        "side": side,
        "conviction": alert.conviction,
        "strategy": alert.strategy,
        "entry_price": alert.price,
        "stop_loss": alert.sl,
        "take_profit": alert.tp,
        "regime": alert.regime,
        "metadata": {
            **alert.metadata,
            "source": "tradingview",
            "tv_timestamp": alert.timestamp,
        },
    }

    # Ingest
    gateway = request.app.state.signal_gateway
    signal = await gateway.ingest(raw_signal, source=SignalSource.TRADINGVIEW)

    if signal is None:
        return WebhookResponse(
            success=False,
            status="rejected",
            message="Signal rejected (validation failed or duplicate)",
        )

    logger.info(
        "webhook.tv.accepted",
        signal_id=signal.signal_id,
        symbol=signal.symbol,
        side=signal.side.value,
    )

    return WebhookResponse(
        success=True,
        signal_id=signal.signal_id,
        status="accepted",
        message=f"Signal {signal.signal_id} ingested for {signal.symbol}",
    )


@webhook_router.post("/generic", response_model=WebhookResponse)
async def generic_webhook(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> WebhookResponse:
    """Generic webhook for external signal sources (EAs, Python scripts, ML)."""
    settings = get_settings()

    # Authenticate via API key — fail-closed: reject if key is not configured
    admin_key = getattr(settings, "ADMIN_API_KEY", "")
    if not admin_key:
        logger.warning("webhook.generic.no_key_configured")
        raise HTTPException(status_code=503, detail="Admin API key not configured")
    if not x_api_key or not _hmac.compare_digest(x_api_key, admin_key):
        logger.warning("webhook.generic.auth_failed")
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Parse
    try:
        body = await request.json()
        payload = GenericWebhookPayload(**body)
    except Exception as exc:
        logger.warning("webhook.generic.parse_error", error=str(exc))
        raise HTTPException(status_code=400, detail=f"Invalid payload: {exc}")

    raw_signal = {
        "symbol": payload.symbol.upper(),
        "asset_class": payload.asset_class,
        "side": payload.side,
        "conviction": payload.conviction,
        "strategy": payload.strategy,
        "entry_price": payload.entry_price,
        "stop_loss": payload.stop_loss,
        "take_profit": payload.take_profit,
        "regime": payload.regime,
        "metadata": {
            **payload.metadata,
            "source": payload.source,
        },
    }

    gateway = request.app.state.signal_gateway
    source = SignalSource(payload.source) if payload.source in {e.value for e in SignalSource} else SignalSource.PYTHON
    signal = await gateway.ingest(raw_signal, source=source)

    if signal is None:
        return WebhookResponse(
            success=False,
            status="rejected",
            message="Signal rejected (validation failed or duplicate)",
        )

    return WebhookResponse(
        success=True,
        signal_id=signal.signal_id,
        status="accepted",
        message=f"Signal {signal.signal_id} ingested for {signal.symbol}",
    )
