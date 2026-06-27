"""
Canonical State Contract — Pydantic v2 payloads for all inter-module communication.

RULE: No module may send a raw dictionary via EventBus.
All payloads MUST be one of these models.

Architecture:
    Initiator (XGBoost/Technical) → produces MLSignalPayload / TechnicalSignalPayload
    Modifier (Sentiment) → reads/writes MacroRegimePayload
    Vetoer (RiskAuditor) → produces RiskVerdictPayload
    PortfolioManager → assembles FinalTradePayload
"""
from __future__ import annotations
from datetime import datetime, UTC
from enum import Enum
from typing import Optional, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class RegimeBias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    PANIC = "PANIC"


class SignalDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class VetoReason(str, Enum):
    NONE = "NONE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    POOR_RR_RATIO = "POOR_RR_RATIO"
    DUPLICATE_FLOOD = "DUPLICATE_FLOOD"
    SYMBOL_NOT_WHITELISTED = "SYMBOL_NOT_WHITELISTED"
    KILL_SWITCH = "KILL_SWITCH"
    MACRO_LOCKDOWN = "MACRO_LOCKDOWN"


class MLSignalPayload(BaseModel):
    """Output from XGBoost models."""
    model_config = {"frozen": True}
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    symbol: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    xgb_probability: float = Field(ge=0.0, le=1.0)
    xgb_model_version: str
    direction: SignalDirection
    entry_price: float
    stop_loss: float
    take_profit: float


class TechnicalSignalPayload(BaseModel):
    """Output from TechnicalAnalystAgent."""
    model_config = {"frozen": True}
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    symbol: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    technical_action: SignalDirection
    sma_short: float = 0.0
    sma_long: float = 0.0
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    reasons: list[str] = Field(default_factory=list)


class MacroRegimePayload(BaseModel):
    """Output from SentimentAgent. Modifier only."""
    model_config = {"frozen": True}
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    bias: RegimeBias = RegimeBias.NEUTRAL
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    position_multiplier: float = Field(ge=0.0, le=1.0, default=1.0)
    regime_label: Literal["NORMAL", "HIGH_UNCERTAINTY", "CRISIS"] = "NORMAL"
    source_provider: str = "unknown"
    headline: str = ""
    reasoning: str = ""


class RiskVerdictPayload(BaseModel):
    """Output from RiskAuditorAgent. Binary KILL/ALLOW gate.

    Canonical contract fields:
        verdict: human-readable "APPROVED" / "VETOED"
        risk_score: signal confidence (0.0–1.0)
        position_size_allowed: 0.0 when vetoed, else confidence-scaled
        max_loss: dollar risk from entry to stop (0.0 if no SL)
        warnings: soft warnings (non-blocking)
    """
    model_config = {"frozen": True}
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_approved: bool
    veto_reason: VetoReason = VetoReason.NONE
    veto_detail: str = ""
    checks_passed: list[str] = Field(default_factory=list)
    checks_failed: list[str] = Field(default_factory=list)
    verdict: str = ""
    risk_score: float = 0.0
    position_size_allowed: float = 0.0
    max_loss: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class FinalTradePayload(BaseModel):
    """Assembled by PortfolioManager. Goes to execution."""
    model_config = {"frozen": True}
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ml_trace_id: str = ""
    technical_trace_id: str = ""
    sentiment_trace_id: str = ""
    risk_trace_id: str = ""
    symbol: str
    direction: SignalDirection
    entry_price: float
    stop_loss: float
    take_profit: float
    raw_confidence: float = Field(ge=0.0, le=1.0)
    sentiment_modifier: float = Field(ge=0.0, le=1.0, default=1.0)
    final_confidence: float = Field(ge=0.0, le=1.0)
    risk_dollars: float = Field(ge=0.0)
    regime_bias: RegimeBias = RegimeBias.NEUTRAL
    regime_label: str = "NORMAL"
    risk_approved: bool = True
    veto_reason: str = ""


class SignalNewPayload(BaseModel):
    """Canonical payload for signal.new events on the EventBus."""
    model_config = {"frozen": True}
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    symbol: str
    side: SignalDirection
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)
    strategy: str = ""
    signal_id: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
