"""
Time-Series Momentum (TSM) — ensemble of lookback windows.
Ported from scripts/tsm_paper_trade.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import BaseStrategy, Signal, StrategyResult


class TSMStrategy(BaseStrategy):
    """Ensemble TSM — vol-scaled momentum across multiple lookbacks."""

    def __init__(self):
        super().__init__("tsm")

    def generate_signals(self, df: pd.DataFrame, params: dict) -> StrategyResult:
        lookbacks = params.get("lookbacks", [20, 40, 60, 120])
        vol_target = params.get("vol_target", 0.10)
        atr_period = params.get("atr_period", 14)

        closes = df["close"].values.astype(float)
        returns = np.diff(closes) / closes[:-1]
        returns = np.concatenate([[0], returns])

        n = len(closes)
        ensemble = np.zeros(n)

        for lb in lookbacks:
            if n < lb + 2:
                continue
            roll_sum = pd.Series(returns).rolling(lb).sum().values
            roll_std = pd.Series(returns).rolling(lb).std().values
            sig = roll_sum / np.where(roll_std > 1e-10, roll_std, np.nan)
            sig = np.nan_to_num(sig, nan=0.0)
            ensemble += sig / len(lookbacks)

        # Normalize to z-scores — rolling window (no look-ahead)
        # Each bar's z-score uses only data available up to that bar.
        lookback_window = min(250, len(ensemble) - 1)
        if lookback_window > 0:
            ensemble_series = pd.Series(ensemble)
            rolling_mean = ensemble_series.rolling(lookback_window, min_periods=1).mean()
            rolling_std = ensemble_series.rolling(lookback_window, min_periods=1).std()
            z_scores = (ensemble - rolling_mean.values) / rolling_std.replace(0, np.nan).values
            z_scores = np.nan_to_num(z_scores, nan=0.0)
        else:
            z_scores = ensemble

        # Generate signals — threshold is in standard-deviation units
        # 0.5σ = moderate conviction, 1.0σ = high conviction
        ENTRY_THRESHOLD = 0.5  # z-score threshold
        signals = []
        atr = self.compute_atr(df, atr_period)

        for i in range(max(lookbacks) + 1, n):
            if np.isnan(z_scores[i]):
                continue
            z = z_scores[i]
            direction = 0
            conf = min(abs(z) / 2.0, 1.0)  # 2σ = full confidence

            if z > ENTRY_THRESHOLD:
                direction = 1
            elif z < -ENTRY_THRESHOLD:
                direction = -1

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
                    reason=f"TSM z={z:.2f}",
                    bar_index=i,
                ))

        return StrategyResult(
            signals=signals,
            metrics={"strategy": "tsm", "lookbacks": lookbacks, "vol_target": vol_target},
        )
