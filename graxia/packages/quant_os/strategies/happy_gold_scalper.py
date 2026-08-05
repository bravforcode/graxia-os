"""Happy Gold-style M15 XAUUSD scalper (EA-BENCH trial 1034).

Frozen per research/pre_registration/trial_1034_happy_gold_scalper.md (2026-08-04).

Behavior profile mirrors the verified Happy Gold EA family on MyFxBook
(PF 2.0-3.5, DD 8-26%, monthly 6.9-8.3%): London/NY-session gold breakout
with EMA trend filter and ATR-based SL/TP. Explicitly NON-martingale:
one position at a time (engine max_positions=1), no grid, no averaging.

Frozen parameters — do not tune after backtest results:
    sessions:         London 08:00-16:00 UTC OR NY 13:00-21:00 UTC
    ema_period:       50
    breakout_lookback: 20  (prior-20-bar high/low, as-of prior close)
    atr_period:       14
    atr_sl_mult:      1.5
    atr_tp_mult:      2.0  (RR 1.33)
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import numpy as np

from ..core.enums import RegimeType, SignalType
from .base import Signal, Strategy, StrategyConfig

SESSION_START_HOUR = 8  # London open (UTC)
SESSION_END_HOUR = 21  # NY close (UTC)
WEEKEND_DAYS = {5, 6}  # Saturday, Sunday (UTC)

# Trailing computation window: EMA(50)/ATR(14) converge well within 200 bars
# (warmup error decays as (1-alpha)^k ≈ 0.96^150 ≈ 0.2%). Keeps per-bar cost
# O(window) instead of O(n) for long M15 histories (60k bars).
_WINDOW = 200


def _ema(close: np.ndarray, period: int) -> np.ndarray:
    """Exponential moving average (span=period)."""
    alpha = 2.0 / (period + 1.0)
    out = np.empty_like(close, dtype=np.float64)
    out[:period] = np.nan
    if len(close) < period:
        return out
    out[period - 1] = float(np.mean(close[:period]))
    for i in range(period, len(close)):
        out[i] = alpha * close[i] + (1.0 - alpha) * out[i - 1]
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


class HappyGoldScalper(Strategy):
    """London/NY gold breakout scalper with EMA trend filter + ATR SL/TP."""

    def __init__(
        self,
        ema_period: int = 50,
        breakout_lookback: int = 20,
        atr_period: int = 14,
        atr_sl_mult: float = 1.5,
        atr_tp_mult: float = 2.0,
    ):
        config = StrategyConfig(
            name="HappyGoldScalper",
            version="1.0",
            symbols=["XAUUSD"],
            timeframes=["M15"],
            risk_per_trade_pct=1.0,
            max_trades_per_day=1,
            min_confidence=0.0,
            min_risk_reward=0.0,
            require_trend_confirm=False,
        )
        super().__init__(config)
        self.ema_period = ema_period
        self.breakout_lookback = breakout_lookback
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def required_features(self) -> list[str]:
        return [f"ema_{self.ema_period}", f"atr_{self.atr_period}"]

    # ------------------------------------------------------------------
    # Session filter (frozen)
    # ------------------------------------------------------------------
    def _in_trading_session(self, current_time: datetime) -> bool:
        if current_time.weekday() in WEEKEND_DAYS:
            return False
        hour = current_time.hour
        # London 08:00-16:00 OR NY 13:00-21:00 → union 08:00-21:00 UTC
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

        min_bars = max(self.breakout_lookback + 1, self.ema_period) + self.atr_period + 5
        if len(close) < min_bars:
            return None

        now = current_time or datetime.now(UTC)
        if not self._in_trading_session(now):
            return None

        # Trailing window (see _WINDOW) — identical result for short series
        tail = slice(-_WINDOW, None)
        close_arr = np.array([float(c) for c in close[tail]], dtype=np.float64)
        high_arr = np.array([float(h) for h in high[tail]], dtype=np.float64)
        low_arr = np.array([float(l) for l in low[tail]], dtype=np.float64)

        ema = _ema(close_arr, self.ema_period)
        atr = _atr(high_arr, low_arr, close_arr, self.atr_period)

        cur_close = close_arr[-1]
        ema_now = ema[-1]
        atr_now = atr[-1]
        if np.isnan(ema_now) or np.isnan(atr_now) or atr_now <= 0:
            return None

        # Prior-20-bar high/low EXCLUDING current bar (no lookahead)
        prior = close_arr[-self.breakout_lookback - 1 : -1]
        prior_high = float(prior.max())
        prior_low = float(prior.min())

        direction = 0
        if cur_close > ema_now and cur_close > prior_high:
            direction = 1  # long: uptrend + upside breakout
        elif cur_close < ema_now and cur_close < prior_low:
            direction = -1  # short: downtrend + downside breakout

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

        # Confidence: normalized breakout size (small caps at 0.5)
        breakout_pct = abs(cur_close - prior_high) / cur_close if direction == 1 else abs(prior_low - cur_close) / cur_close
        confidence = float(np.clip(0.5 + breakout_pct * 5000, 0.5, 0.95))

        return Signal.create(
            strategy_id=self.id,
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
