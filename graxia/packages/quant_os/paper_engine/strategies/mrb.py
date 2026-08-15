"""
Mean Reversion (MRB) — z-score mean reversion with Bollinger-style entry.
Ported from strategies/mrb.py.
"""

from __future__ import annotations

import numpy as np

from .base import BaseStrategy, Signal, StrategyResult


class MRBStrategy(BaseStrategy):
    """Mean reversion — enter when price deviates > entry_z sigma, exit when < exit_z."""

    def __init__(self):
        super().__init__("mrb")

    def generate_signals(self, df, params):
        lookback = params.get("lookback", 20)
        entry_z = params.get("entry_z", 2.0)
        exit_z = params.get("exit_z", 0.5)
        atr_period = params.get("atr_period", 14)

        closes = df["close"].values.astype(float)
        n = len(closes)

        atr = self.compute_atr(df, atr_period)

        # Rolling z-score
        z_scores = np.full(n, np.nan)
        for i in range(lookback, n):
            window = closes[i - lookback: i]
            mu = np.mean(window)
            std = np.std(window, ddof=1) if len(window) > 1 else 0
            if std > 1e-10:
                z_scores[i] = (closes[i] - mu) / std

        signals = []
        in_position = 0  # track position to avoid multiple signals

        for i in range(lookback + 1, n):
            if np.isnan(z_scores[i]):
                continue

            z = z_scores[i]
            direction = 0
            conf = 0.0
            reason = ""

            if in_position == 0:
                if z > entry_z:
                    direction = -1  # short — overbought
                    conf = min((z - entry_z) / entry_z, 1.0)
                    reason = f"MR_SHORT z={z:.2f} > {entry_z}"
                elif z < -entry_z:
                    direction = 1  # long — oversold
                    conf = min((abs(z) - entry_z) / entry_z, 1.0)
                    reason = f"MR_LONG z={z:.2f} < -{entry_z}"
            else:
                # Exit when reverts
                if in_position == 1 and z > -exit_z:
                    direction = 0
                    reason = f"MR_EXIT_LONG z={z:.2f} > -{exit_z}"
                elif in_position == -1 and z < exit_z:
                    direction = 0
                    reason = f"MR_EXIT_SHORT z={z:.2f} < {exit_z}"

            if direction != 0:
                entry = closes[i]
                sl = None
                tp = None
                if direction in (1, -1):
                    sl = entry - atr[i] * 2.0 if direction == 1 else entry + atr[i] * 2.0
                    tp = entry + atr[i] * 2.0 if direction == 1 else entry - atr[i] * 2.0

                signals.append(Signal(
                    timestamp=str(df.index[i]),
                    direction=direction,
                    confidence=round(conf, 3) if conf > 0 else 0,
                    entry_price=round(entry, 5),
                    stop_loss=round(sl, 5) if sl else None,
                    take_profit=round(tp, 5) if tp else None,
                    reason=reason,
                    bar_index=i,
                ))

                if direction in (1, -1):
                    in_position = direction
                else:
                    in_position = 0

        return StrategyResult(signals=signals, metrics={
            "strategy": "mrb", "lookback": lookback, "entry_z": entry_z,
        })
