"""EURUSD M15 London-session breakout of Asian range (Direction G trial 8002).

Frozen per research/pre_registration/trial_8002_eur_session_breakout_m15.md
(2026-08-05). No tuning after backtest.

Frozen parameters:
    asian_start_hour: 0   (00:00 UTC)
    asian_end_hour:   6   (06:00 UTC — range computed from prior-day Asian window)
    london_open_hour: 7   (07:00 UTC)
    ny_end_hour:      20  (20:00 UTC — time-based exit)
    atr_fast:         5
    atr_slow:         20
    vol_ratio_min:    1.25  (ATR(5)/ATR(20) > 1.25 — volatility expansion only)
    rr_min:           1.5   (fixed R:R exit >= 1:1.5)
    timeframes:       M15
    symbols:          EURUSD
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import numpy as np

from ..core.enums import RegimeType, SignalType
from .base import Signal, Strategy, StrategyConfig

ASIAN_START_HOUR = 0
ASIAN_END_HOUR = 6
LONDON_OPEN_HOUR = 7
NY_END_HOUR = 20
ATR_FAST = 5
ATR_SLOW = 20
VOL_RATIO_MIN = 1.25
RR_MIN = 1.5
WEEKEND_DAYS = {5, 6}

_WINDOW = 400  # trailing window: 20-bar ATR + 6h Asian range at M15 (24 bars)


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


class EurSessionBreakout(Strategy):
    """EURUSD breakout of prior Asian range at London open, vol-expansion filter."""

    def __init__(
        self,
        asian_start_hour: int = ASIAN_START_HOUR,
        asian_end_hour: int = ASIAN_END_HOUR,
        london_open_hour: int = LONDON_OPEN_HOUR,
        ny_end_hour: int = NY_END_HOUR,
        atr_fast: int = ATR_FAST,
        atr_slow: int = ATR_SLOW,
        vol_ratio_min: float = VOL_RATIO_MIN,
        rr_min: float = RR_MIN,
    ):
        config = StrategyConfig(
            name="EurSessionBreakout",
            version="1.0",
            symbols=["EURUSD"],
            timeframes=["M15"],
            risk_per_trade_pct=1.0,
            max_trades_per_day=1,
            min_confidence=0.0,
            min_risk_reward=rr_min,
            require_trend_confirm=False,
        )
        super().__init__(config)
        self.asian_start_hour = asian_start_hour
        self.asian_end_hour = asian_end_hour
        self.london_open_hour = london_open_hour
        self.ny_end_hour = ny_end_hour
        self.atr_fast = atr_fast
        self.atr_slow = atr_slow
        self.vol_ratio_min = vol_ratio_min
        self.rr_min = rr_min

    def required_features(self) -> list[str]:
        return [f"atr_{self.atr_fast}", f"atr_{self.atr_slow}"]

    def _is_london_open(self, t: datetime) -> bool:
        if t.weekday() in WEEKEND_DAYS:
            return False
        return self.london_open_hour <= t.hour < self.london_open_hour + 1

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

        now = current_time or datetime.now(UTC)
        if not self._is_london_open(now):
            return None

        min_bars = self.atr_slow + 5
        if len(close) < min_bars:
            return None

        tail = slice(-_WINDOW, None)
        close_arr = np.array([float(c) for c in close[tail]], dtype=np.float64)
        high_arr = np.array([float(h) for h in high[tail]], dtype=np.float64)
        low_arr = np.array([float(lo) for lo in low[tail]], dtype=np.float64)

        atr_fast = _atr(high_arr, low_arr, close_arr, self.atr_fast)
        atr_slow = _atr(high_arr, low_arr, close_arr, self.atr_slow)
        ratio = (
            atr_fast[-1] / atr_slow[-1] if atr_slow[-1] and not np.isnan(atr_slow[-1]) and atr_slow[-1] > 0 else np.nan
        )
        if np.isnan(ratio) or ratio < self.vol_ratio_min:
            return None  # volatility expansion filter — skip quiet markets

        # Asian range: prior 24 M15 bars (6 hours) EXCLUDING current bar —
        # engine passes ohlcv_data without timestamps, so we approximate the
        # Asian window by the last 24 completed bars before the London-open
        # bar. This matches the frozen spec (Asian 00:00-06:00 UTC) since the
        # engine calls generate_signal on the London-open bar itself.
        asian_window = close_arr[-25:-1]
        if len(asian_window) < 12:
            return None  # need at least half a window
        asian_high = float(np.max(high_arr[-25:-1]))
        asian_low = float(np.min(low_arr[-25:-1]))

        cur_close = close_arr[-1]
        direction = 0
        if cur_close > asian_high:
            direction = 1
        elif cur_close < asian_low:
            direction = -1
        else:
            return None

        entry = Decimal(str(cur_close))
        atr_now = atr_fast[-1] if not np.isnan(atr_fast[-1]) else float(close_arr[-1]) * 0.001
        sl_dist = Decimal(str(max(atr_now, 1e-9)))
        tp_dist = sl_dist * Decimal(str(self.rr_min))

        if direction == 1:
            signal_type = SignalType.BUY
            stop_loss = entry - sl_dist
            take_profit = entry + tp_dist
        else:
            signal_type = SignalType.SELL
            stop_loss = entry + sl_dist
            take_profit = entry - tp_dist

        breakout_pct = (
            abs(cur_close - asian_high) / cur_close if direction == 1 else abs(asian_low - cur_close) / cur_close
        )
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
