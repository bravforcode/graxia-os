"""BTCUSD H1 Donchian trend follower (Direction G trial 8001).

Frozen per research/pre_registration/trial_8001_btc_donchian_h1.md (2026-08-05).
No tuning after backtest.

Frozen parameters:
    donchian_period:  20   (prior-20-bar channel, as-of prior close — no lookahead)
    volume_filter:    vol > 1.5 * SMA(vol, 20)
    atr_period:       14
    atr_trailing:     2.5x ATR chandelier-style exit
    timeframes:       H1
    symbols:          BTCUSD
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import numpy as np

from ..core.enums import RegimeType, SignalType
from .base import Signal, Strategy, StrategyConfig

DONCHIAN_PERIOD = 20
VOL_SMA_PERIOD = 20
VOL_FILTER_MULT = 1.5
ATR_PERIOD = 14
ATR_TRAILING_MULT = 2.5

_WINDOW = 300  # trailing window: Donchian(20)+SMA(20)+ATR(14) converge fast


def _sma(x: np.ndarray, period: int) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=np.float64)
    if len(x) < period:
        return out
    cs = np.cumsum(np.insert(np.asarray(x, dtype=np.float64), 0, 0.0))
    out[period - 1 :] = (cs[period:] - cs[:-period]) / period
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


class BtcDonchianTrend(Strategy):
    """BTCUSD H1 Donchian breakout with volume filter + ATR trailing exit."""

    def __init__(
        self,
        donchian_period: int = DONCHIAN_PERIOD,
        vol_sma_period: int = VOL_SMA_PERIOD,
        vol_filter_mult: float = VOL_FILTER_MULT,
        atr_period: int = ATR_PERIOD,
        atr_trailing_mult: float = ATR_TRAILING_MULT,
    ):
        config = StrategyConfig(
            name="BtcDonchianTrend",
            version="1.0",
            symbols=["BTCUSD"],
            timeframes=["H1"],
            risk_per_trade_pct=1.0,
            max_trades_per_day=1,
            min_confidence=0.0,
            min_risk_reward=2.0,
            require_trend_confirm=False,
        )
        super().__init__(config)
        self.donchian_period = donchian_period
        self.vol_sma_period = vol_sma_period
        self.vol_filter_mult = vol_filter_mult
        self.atr_period = atr_period
        self.atr_trailing_mult = atr_trailing_mult

    def required_features(self) -> list[str]:
        return [f"atr_{self.atr_period}"]

    def _volume_ok(self, volume_arr: np.ndarray) -> bool:
        if len(volume_arr) < self.vol_sma_period:
            return False
        cur_vol = float(volume_arr[-1])
        vol_sma = _sma(volume_arr, self.vol_sma_period)[-1]
        if np.isnan(vol_sma) or vol_sma <= 0:
            return False
        return cur_vol > self.vol_filter_mult * vol_sma

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
        volume = ohlcv_data.get("volume", [])

        min_bars = self.donchian_period + self.vol_sma_period + self.atr_period + 5
        if len(close) < min_bars:
            return None

        tail = slice(-_WINDOW, None)
        close_arr = np.array([float(c) for c in close[tail]], dtype=np.float64)
        high_arr = np.array([float(h) for h in high[tail]], dtype=np.float64)
        low_arr = np.array([float(lo) for lo in low[tail]], dtype=np.float64)
        vol_arr = np.array([float(v) for v in volume[tail]], dtype=np.float64)

        atr = _atr(high_arr, low_arr, close_arr, self.atr_period)
        cur_close = close_arr[-1]
        atr_now = atr[-1]
        if np.isnan(atr_now) or atr_now <= 0:
            return None

        # Prior-20-bar high/low EXCLUDING current bar (no lookahead)
        prior = close_arr[-self.donchian_period - 1 : -1]
        if len(prior) == 0:
            return None
        prior_high = float(prior.max())
        prior_low = float(prior.min())

        direction = 0
        if cur_close > prior_high:
            direction = 1
        elif cur_close < prior_low:
            direction = -1
        else:
            return None

        # Volume filter (frozen): require volume expansion on breakout bar
        if not self._volume_ok(vol_arr):
            return None

        entry = Decimal(str(cur_close))
        sl_dist = Decimal(str(self.atr_trailing_mult * atr_now))

        if direction == 1:
            signal_type = SignalType.BUY
            stop_loss = entry - sl_dist
            take_profit = entry + sl_dist * 2  # R:R >= 1:2 (trailing exit primary)
        else:
            signal_type = SignalType.SELL
            stop_loss = entry + sl_dist
            take_profit = entry - sl_dist * 2

        # Confidence: normalized breakout size (small caps at 0.5)
        breakout_pct = (
            abs(cur_close - prior_high) / cur_close if direction == 1 else abs(prior_low - cur_close) / cur_close
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
