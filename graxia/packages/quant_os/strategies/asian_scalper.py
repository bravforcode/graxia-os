"""WallStreet-style Asian-session range scalper (EA-BENCH trial 1035).

Frozen per research/pre_registration/trial_1035_asian_scalper.md (2026-08-04).

Behavior profile mirrors the verified WallStreet Robot EA on MyFxBook
(15+ years, win 76%, avg win 8.3 pips, PF 1.37): Asian-session range
scalper with small ATR target and tight stop. Explicitly NON-martingale:
one position at a time (engine max_positions=1), no grid, no averaging.

Frozen parameters — do not tune after backtest results:
    session:          00:00-08:00 UTC (Asian)
    range_lookback:   20  (prior-20-bar high/low channel, as-of prior close)
    rsi_period:       14
    rsi_oversold:     30
    rsi_overbought:   70
    atr_period:       14
    atr_sl_mult:      1.0
    atr_tp_mult:      1.2  (small target, high win-rate profile)
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import numpy as np

from ..core.enums import RegimeType, SignalType
from .base import Signal, Strategy, StrategyConfig

SESSION_START_HOUR = 0  # Asian open (UTC)
SESSION_END_HOUR = 8  # Asian close (UTC)
WEEKEND_DAYS = {5, 6}  # Saturday, Sunday (UTC)

# Trailing computation window (see _WINDOW in happy_gold_scalper for rationale)
_WINDOW = 200


def _rsi(close: np.ndarray, period: int) -> np.ndarray:
    """Wilder's RSI."""
    n = len(close)
    out = np.full(n, np.nan, dtype=np.float64)
    if n < period + 1:
        return out
    delta = np.diff(close)
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))
    out[period] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return out


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    """Wilder's Average True Range."""
    n = len(close)
    out = np.empty(n, dtype=np.float64)
    out[: period + 1] = np.nan
    if n < period + 1:
        return out
    tr = np.maximum.reduce(
        [
            high[1:] - low[1:],
            np.abs(high[1:] - close[:-1]),
            np.abs(low[1:] - close[:-1]),
        ]
    )
    out[period] = float(np.mean(tr[:period]))
    for i in range(period + 1, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i - 1]) / period
    return out


class AsianScalper(Strategy):
    """Asian-session range fade with RSI extremes and tight ATR SL/TP."""

    def __init__(
        self,
        range_lookback: int = 20,
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        atr_period: int = 14,
        atr_sl_mult: float = 1.0,
        atr_tp_mult: float = 1.2,
    ):
        config = StrategyConfig(
            name="AsianScalper",
            version="1.0",
            symbols=["EURUSD", "GBPUSD", "USDJPY"],
            timeframes=["M15"],
            risk_per_trade_pct=1.0,
            max_trades_per_day=2,
            min_confidence=0.0,
            min_risk_reward=0.0,
            require_trend_confirm=False,
        )
        super().__init__(config)
        self.range_lookback = range_lookback
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def required_features(self) -> list[str]:
        return [f"rsi_{self.rsi_period}", f"atr_{self.atr_period}"]

    # ------------------------------------------------------------------
    # Session filter (frozen)
    # ------------------------------------------------------------------
    def _in_trading_session(self, current_time: datetime) -> bool:
        if current_time.weekday() in WEEKEND_DAYS:
            return False
        hour = current_time.hour
        return SESSION_START_HOUR <= hour < SESSION_END_HOUR

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------
    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict | None = None,
        regime: RegimeType | None = None,
        current_time: datetime | None = None,
        **kwargs,
    ) -> Signal | None:
        close = ohlcv_data.get("close", [])
        high = ohlcv_data.get("high", [])
        low = ohlcv_data.get("low", [])

        min_bars = self.range_lookback + self.rsi_period + self.atr_period + 5
        if len(close) < min_bars:
            return None

        now = current_time or datetime.now(UTC)
        if not self._in_trading_session(now):
            return None

        # Trailing window (identical result for short series)
        tail = slice(-_WINDOW, None)
        close_arr = np.array([float(c) for c in close[tail]], dtype=np.float64)
        high_arr = np.array([float(h) for h in high[tail]], dtype=np.float64)
        low_arr = np.array([float(l) for l in low[tail]], dtype=np.float64)

        rsi = _rsi(close_arr, self.rsi_period)
        atr = _atr(high_arr, low_arr, close_arr, self.atr_period)

        cur_close = close_arr[-1]
        rsi_now = rsi[-1]
        atr_now = atr[-1]
        if np.isnan(rsi_now) or np.isnan(atr_now) or atr_now <= 0:
            return None

        # Prior-20-bar channel EXCLUDING current bar (no lookahead)
        prior = close_arr[-self.range_lookback - 1 : -1]
        channel_high = float(prior.max())
        channel_low = float(prior.min())

        direction = 0
        if cur_close < channel_low and rsi_now < self.rsi_oversold:
            direction = 1  # oversold below channel → fade long
        elif cur_close > channel_high and rsi_now > self.rsi_overbought:
            direction = -1  # overbought above channel → fade short

        if direction == 0:
            return None

        entry = Decimal(str(cur_close))
        sl_dist = Decimal(str(self.atr_sl_mult * atr_now))
        tp_dist = Decimal(str(self.atr_tp_mult * atr_now))

        if direction == 1:
            signal_type = SignalType.BUY
            stop_loss = entry - sl_dist
            take_profit = entry + tp_dist
        else:
            signal_type = SignalType.SELL
            stop_loss = entry + sl_dist
            take_profit = entry - tp_dist

        # Confidence: RSI extremity (max at extreme)
        if direction == 1:
            confidence = float(np.clip((self.rsi_oversold - rsi_now) / self.rsi_oversold * 0.4 + 0.5, 0.5, 0.9))
        else:
            confidence = float(np.clip((rsi_now - self.rsi_overbought) / (100.0 - self.rsi_overbought) * 0.4 + 0.5, 0.5, 0.9))

        return Signal.create(
            strategy_id=self.id,
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
