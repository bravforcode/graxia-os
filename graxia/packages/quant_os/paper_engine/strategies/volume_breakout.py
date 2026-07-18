"""
Volume Breakout — price breakout confirmed by volume surge.
"""

from __future__ import annotations

import numpy as np

from .base import BaseStrategy, Signal, StrategyResult


class VolumeBreakoutStrategy(BaseStrategy):
    """Volume-confirmed price breakout."""

    def __init__(self):
        super().__init__("volume_breakout")

    def generate_signals(self, df, params):
        vol_period = params.get("vol_period", 20)
        vol_mult = params.get("vol_mult", 2.0)
        lookback = params.get("lookback", 20)
        atr_period = params.get("atr_period", 14)

        closes = df["close"].values.astype(float)
        highs = df["high"].values.astype(float)
        lows = df["low"].values.astype(float)
        volumes = df["volume"].values.astype(float)
        n = len(closes)

        atr = self.compute_atr(df, atr_period)

        # Volume moving average
        vol_ma = np.full(n, np.nan)
        for i in range(vol_period, n):
            vol_ma[i] = np.mean(volumes[i - vol_period: i])

        signals = []
        for i in range(max(lookback, vol_period) + 1, n):
            # Check volume surge
            vol_surge = volumes[i] > vol_ma[i] * vol_mult if not np.isnan(vol_ma[i]) else False
            if not vol_surge:
                continue

            # Check price breakout
            recent_high = np.max(highs[i - lookback: i])
            recent_low = np.min(lows[i - lookback: i])

            direction = 0
            conf = 0.0
            reason = ""

            if closes[i] > recent_high:
                direction = 1
                vol_ratio = volumes[i] / vol_ma[i] if not np.isnan(vol_ma[i]) else 1.0
                conf = min((vol_ratio - 1) / 2, 1.0)
                reason = f"VOL_BREAKOUT LONG vol={vol_ratio:.1f}x ma"
            elif closes[i] < recent_low:
                direction = -1
                vol_ratio = volumes[i] / vol_ma[i] if not np.isnan(vol_ma[i]) else 1.0
                conf = min((vol_ratio - 1) / 2, 1.0)
                reason = f"VOL_BREAKOUT SHORT vol={vol_ratio:.1f}x ma"

            if direction != 0 and conf > 0.1:
                entry = closes[i]
                sl = entry - atr[i] * 2.0 if direction == 1 else entry + atr[i] * 2.0
                tp = entry + atr[i] * 3.0 if direction == 1 else entry - atr[i] * 3.0
                signals.append(Signal(
                    timestamp=str(df.index[i]),
                    direction=direction,
                    confidence=round(conf, 3),
                    entry_price=round(entry, 5),
                    stop_loss=round(sl, 5),
                    take_profit=round(tp, 5),
                    reason=reason,
                    bar_index=i,
                ))

        return StrategyResult(signals=signals, metrics={
            "strategy": "volume_breakout", "vol_period": vol_period, "vol_mult": vol_mult,
        })
