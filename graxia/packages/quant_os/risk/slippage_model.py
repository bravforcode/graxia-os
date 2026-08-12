"""
Slippage Model — risk-layer with session classification and volatility regimes.

.. deprecated::
    Use ``core.slippage_model.SlippageModel`` instead.
    This module will be removed in a future release.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum


class TradingSession(str, Enum):
    ASIAN = "asian"
    LONDON = "london"
    NEW_YORK = "new_york"
    OVERLAP = "overlap"
    ROLLOVER = "rollover"
    CLOSED = "closed"


class VolatilityRegime(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EXTREME = "extreme"


class OrderSize(str, Enum):
    MICRO = "micro"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    INSTITUTIONAL = "inst"


BASE_SLIPPAGE = {"XAUUSD": 0.3, "EURUSD": 0.1, "GBPUSD": 0.15, "USDJPY": 0.15, "BTCUSD": 5.0, "US30": 1.0}
SESSION_MULTIPLIER = {"asian": 1.5, "london": 0.8, "new_york": 0.9, "overlap": 0.7, "closed": 3.0, "rollover": 5.0}
ORDER_SIZE_MULTIPLIER = {
    OrderSize.MICRO: 0.5,
    OrderSize.SMALL: 1.0,
    OrderSize.MEDIUM: 1.5,
    OrderSize.LARGE: 2.5,
    OrderSize.INSTITUTIONAL: 4.0,
}
VOLATILITY_BASE = 0.15

_SESSION_RANGES: dict[TradingSession, tuple[time, time]] = {
    TradingSession.ASIAN: (time(0, 0), time(7, 0)),
    TradingSession.LONDON: (time(7, 0), time(12, 0)),
    TradingSession.OVERLAP: (time(12, 0), time(16, 0)),
    TradingSession.NEW_YORK: (time(16, 0), time(21, 55)),
}


def classify_session(ts: datetime) -> TradingSession:
    t = ts.time()
    if time(21, 55) <= t and t < time(22, 16):
        return TradingSession.ROLLOVER
    for session, (start, end) in _SESSION_RANGES.items():
        if start <= t < end:
            return session
    return TradingSession.CLOSED


@dataclass(frozen=True)
class SlippageEstimate:
    symbol: str
    base_slippage_pips: float
    session_multiplier: float
    size_multiplier: float
    volatility_multiplier: float
    estimated_slippage_pips: float
    estimated_slippage_price: float
    session: str
    order_size: str


class SlippageModel:
    def __init__(self, pip_values: dict[str, float] | None = None):
        self._pip_values = pip_values or {
            "XAUUSD": 0.01,
            "EURUSD": 0.0001,
            "GBPUSD": 0.0001,
            "USDJPY": 0.01,
            "BTCUSD": 0.01,
            "US30": 0.01,
        }

    def _classify_size(self, lots: float) -> OrderSize:
        if lots < 0.1:
            return OrderSize.MICRO
        if lots < 0.5:
            return OrderSize.SMALL
        if lots < 2.0:
            return OrderSize.MEDIUM
        if lots < 5.0:
            return OrderSize.LARGE
        return OrderSize.INSTITUTIONAL

    def _volatility_multiplier(self, volatility: float | VolatilityRegime | str) -> float:
        if isinstance(volatility, VolatilityRegime):
            return {
                VolatilityRegime.LOW: 0.5,
                VolatilityRegime.NORMAL: 1.0,
                VolatilityRegime.HIGH: 2.0,
                VolatilityRegime.EXTREME: 4.0,
            }.get(volatility, 1.0)
        if isinstance(volatility, str):
            try:
                return self._volatility_multiplier(VolatilityRegime(volatility))
            except ValueError:
                return 1.0
        if volatility <= 0:
            return 1.0
        ratio = volatility / VOLATILITY_BASE
        return 1.0 + (ratio - 1.0) ** 1.5

    def _resolve_session(self, session: str | TradingSession) -> str:
        return session.value if isinstance(session, TradingSession) else session

    def estimate(
        self,
        symbol: str,
        order_size_lots: float,
        volatility: float | VolatilityRegime | str = 0.15,
        session: str | TradingSession = "london",
    ) -> SlippageEstimate:
        base = BASE_SLIPPAGE.get(symbol, 0.2) if isinstance(symbol, str) and symbol else 0.0
        session_str = self._resolve_session(session)
        session_mult = SESSION_MULTIPLIER.get(session_str, 1.0)
        size_class = self._classify_size(order_size_lots)
        size_mult = ORDER_SIZE_MULTIPLIER[size_class]
        vol_mult = self._volatility_multiplier(volatility)
        estimated = base * session_mult * size_mult * vol_mult
        pip_value = self._pip_values.get(symbol, 0.01) if isinstance(symbol, str) else 0.01
        estimated_price = estimated * pip_value
        return SlippageEstimate(
            symbol=symbol,
            base_slippage_pips=base,
            session_multiplier=session_mult,
            size_multiplier=size_mult,
            volatility_multiplier=vol_mult,
            estimated_slippage_pips=round(estimated, 4),
            estimated_slippage_price=round(estimated_price, 6),
            session=session_str,
            order_size=size_class.value,
        )

    def get_slippage(
        self, symbol: str, session: str | TradingSession = "london", volatility: float | VolatilityRegime | str = 0.15
    ) -> float:
        if not isinstance(symbol, str) or not symbol:
            return 0.0
        base = BASE_SLIPPAGE.get(symbol, 0.2)
        session_str = self._resolve_session(session)
        session_mult = SESSION_MULTIPLIER.get(session_str, 1.0)
        vol_mult = self._volatility_multiplier(volatility)
        return base * session_mult * vol_mult

    def apply_slippage(
        self,
        price: float,
        direction: str,
        lots: float = 0.01,
        symbol: str = "XAUUSD",
        session: str | TradingSession = "london",
        volatility: float | VolatilityRegime | str = 0.15,
    ) -> float:
        if lots <= 0:
            return price
        slip = self.get_slippage(symbol, session, volatility)
        pip_value = self._pip_values.get(symbol, 0.01)
        slip_price = slip * pip_value
        if str(direction).upper() == "BUY":
            return price + slip_price
        return price - slip_price

    def estimate_cost_per_trade(
        self,
        symbol: str,
        session: str | TradingSession = "london",
        lots: float = 0.01,
        volatility: float | VolatilityRegime | str = 0.15,
        commission_per_lot: float = 0.0,
    ) -> dict:
        est = self.estimate(symbol, lots, volatility, session)
        slip_cost = est.estimated_slippage_price * lots * 100000
        comm_cost = commission_per_lot * lots
        return {
            "spread_pips": est.base_slippage_pips,
            "slippage_pips": est.estimated_slippage_pips,
            "total_pips": est.base_slippage_pips + est.estimated_slippage_pips,
            "total_usd": round(slip_cost + comm_cost, 2),
        }
