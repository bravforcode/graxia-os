"""
Donchian Breakout — buy new high, sell new low, with vol filter.
Ported from live_paper_trade.py.
"""

from __future__ import annotations

import numpy as np

from .base import BaseStrategy, Signal, StrategyResult


class DonchianStrategy(BaseStrategy):
    """Donchian(period) breakout with optional volatility filter."""

    def __init__(self):
        super().__init__("donchian")

    def generate_signals(self, df, params):
        period = params.get("period", 20)
        vol_filter = params.get("vol_filter", True)
        atr_period = params.get("atr_period", 14)

        closes = df["close"].values.astype(float)
        highs = df["high"].values.astype(float)
        lows = df["low"].values.astype(float)
        n = len(closes)

        atr = self.compute_atr(df, atr_period)
        atr_ratio = np.where(closes > 0, atr / closes, 0)
        med_ratio = np.nanmedian(atr_ratio[-200:]) if n > 200 else np.nanmedian(atr_ratio)

        signals = []
        for i in range(period + 1, n):
            hh = np.max(highs[i - period: i - 1]) if i - period >= 0 else np.max(highs[:i - 1])
            ll = np.min(lows[i - period: i - 1]) if i - period >= 0 else np.min(lows[:i - 1])

            direction = 0
            conf = 0.0
            reason = ""

            # Vol filter
            vol_ok = True
            if vol_filter and i > 0:
                vol_ok = atr_ratio[i] > med_ratio * 0.8

            if closes[i] > hh and vol_ok:
                direction = 1
                strength = (closes[i] - hh) / (hh + 1e-10) * 100
                conf = min(strength * 5, 1.0)
                reason = f"BREAKOUT LONG high={hh:.5f}"
            elif closes[i] < ll and vol_ok:
                direction = -1
                strength = (ll - closes[i]) / (ll + 1e-10) * 100
                conf = min(strength * 5, 1.0)
                reason = f"BREAKOUT SHORT low={ll:.5f}"

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
            "strategy": "donchian", "period": period, "vol_filter": vol_filter,
        })
