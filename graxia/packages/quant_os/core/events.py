"""
Event types for Quant OS (quanttrader pattern — A3)

Defines the event vocabulary for the event-driven architecture.
All events are frozen dataclasses with timestamp, event_id, and source.
Used by the event bus (A4) to decouple components.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .enums import SignalType


@dataclass(frozen=True)
class Event:
    """Base event — all events inherit from this"""

    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str = ""
    trace_id: str = field(default_factory=lambda: str(uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict (JSON-safe with datetime isoformat)"""
        d = {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "event_type": type(self).__name__,
        }
        # Add subclass fields
        for k, v in self.__dict__.items():
            if k not in ("event_id", "timestamp", "source"):
                d[k] = v
        return d


# ── Market Data Events ────────────────────────────────────────────


@dataclass(frozen=True)
class BarEvent(Event):
    """New bar arrived — strategy subscribes to this"""

    symbol: str = ""
    timeframe: str = "M15"
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    bar_index: int = 0


@dataclass(frozen=True)
class TickEvent(Event):
    """New tick — for real-time data"""

    symbol: str = ""
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    volume: float = 0.0


# ── Strategy Events ───────────────────────────────────────────────


@dataclass(frozen=True)
class SignalEvent(Event):
    """Strategy produced a signal — risk engine subscribes"""

    symbol: str = ""
    signal_type: SignalType = SignalType.NO_TRADE
    confidence: float = 0.0
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    timeframe: str = "M15"
    regime: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SignalValidationEvent(Event):
    """Result of AI signal validation — advisory only.

    Published by SignalValidatorAgent after LLM second-opinion check.
    Adjusted confidence is used by PortfolioManager for position sizing.
    """

    signal_id: str = ""
    original_confidence: float = 0.0
    adjusted_confidence: float = 0.0
    valid: bool = True
    reasoning: str = ""
    red_flags: tuple[str, ...] = ()
    tier_used: int = 0
    latency_ms: float = 0.0


# ── Order Events ──────────────────────────────────────────────────


@dataclass(frozen=True)
class OrderEvent(Event):
    """Order request — execution manager subscribes"""

    order_id: str = ""
    symbol: str = ""
    side: str = "BUY"  # OrderSide value
    order_type: str = "MARKET"  # OrderType value
    quantity: float = 0.0
    price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    strategy_id: str = ""
    signal_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FillEvent(Event):
    """Order filled — portfolio subscribes"""

    order_id: str = ""
    symbol: str = ""
    side: str = "BUY"
    fill_price: float = 0.0
    fill_quantity: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0
    strategy_id: str = ""


# ── Portfolio Events ──────────────────────────────────────────────


@dataclass(frozen=True)
class TradeClosedEvent(Event):
    """Trade closed — strategy.on_trade_closed() subscribes"""

    trade_id: str = ""
    symbol: str = ""
    side: str = "BUY"
    entry_price: float = 0.0
    exit_price: float = 0.0
    quantity: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    close_reason: str = ""
    strategy_id: str = ""
    duration_bars: int = 0
    fees: float = 0.0


# ── Risk Events ───────────────────────────────────────────────────


@dataclass(frozen=True)
class RiskEvent(Event):
    """Risk check result — for audit trail"""

    check_name: str = ""
    passed: bool = True
    order_id: str = ""
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)


# ── System Events ─────────────────────────────────────────────────


@dataclass(frozen=True)
class KillSwitchEvent(Event):
    """Kill switch activated — all components should stop"""

    trigger: str = ""
    reason: str = ""
    severity: str = "P0"


@dataclass(frozen=True)
class RegimeChangeEvent(Event):
    """Market regime changed — strategies should re-evaluate"""

    symbol: str = ""
    old_regime: str = ""
    new_regime: str = ""
    confidence: float = 0.0


@dataclass(frozen=True)
class NewsEvent(Event):
    """News headline impact on market"""

    headline: str = ""
    impact: str = "LOW"
    source: str = "news"
    link: str = ""
    source_name: str = ""
    summary: str = ""


@dataclass(frozen=True)
class NewsAnalyzedEvent(Event):
    """Sentiment analysis complete — regime updated"""

    headline: str = ""
    regime_label: str = "NORMAL"
    bias: str = "NEUTRAL"
    confidence: float = 0.5
    position_multiplier: float = 1.0
    source_provider: str = ""
