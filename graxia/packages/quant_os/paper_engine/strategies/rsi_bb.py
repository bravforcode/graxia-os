"""
RSI + Bollinger Bands — mean-reversion at extremes.
Ported from paper_trade_simulator.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import BaseStrategy, Signal, StrategyResult


class RSIBBStrategy(BaseStrategy):
    """RSI(14) + BB(20,2) — buy oversold, sell overbought."""

    def __init__(self):
        super().__init__("rsi_bb")

    def generate_signals(self, df: pd.DataFrame, params: dict) -> StrategyResult:
        rsi_period = params.get("rsi_period", 14)
        rsi_oversold = params.get("rsi_oversold", 30)
        rsi_overbought = params.get("rsi_overbought", 70)
        bb_period = params.get("bb_period", 20)
        bb_std = params.get("bb_std", 2.0)
        atr_period = params.get("atr_period", 14)

        closes = df["close"].values.astype(float)
        highs = df["high"].values.astype(float)
        lows = df["low"].values.astype(float)
        n = len(closes)

        # RSI
        rsi = self._compute_rsi(closes, rsi_period)

        # Bollinger Bands
        sma, lower, upper = self._compute_bb(closes, bb_period, bb_std)

        # ATR for SL/TP
        atr = self.compute_atr(df, atr_period)

        signals = []
        for i in range(max(rsi_period, bb_period) + 1, n):
            if np.isnan(rsi[i]) or np.isnan(sma[i]):
                continue

            direction = 0
            conf = 0.0
            reason = ""

            # Oversold bounce
            if rsi[i] < rsi_oversold and closes[i] <= lower[i]:
                direction = 1
                conf = min((rsi_oversold - rsi[i]) / rsi_oversold, 1.0)
                reason = f"OVERSOLD rsi={rsi[i]:.1f} < {rsi_oversold}"
            # Overbought drop
            elif rsi[i] > rsi_overbought and closes[i] >= upper[i]:
                direction = -1
                conf = min((rsi[i] - rsi_overbought) / (100 - rsi_overbought), 1.0)
                reason = f"OVERBOUGHT rsi={rsi[i]:.1f} > {rsi_overbought}"

            if direction != 0 and conf > 0.1:
                entry = closes[i]
                sl = entry - atr[i] * 1.5 if direction == 1 else entry + atr[i] * 1.5
                tp = entry + atr[i] * 2.0 if direction == 1 else entry - atr[i] * 2.0
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

        return StrategyResult(signals=signals, metrics={"strategy": "rsi_bb"})

    def _compute_rsi(self, closes: np.ndarray, period: int) -> np.ndarray:
        n = len(closes)
        rsi = np.full(n, np.nan)
        if n < period + 1:
            return rsi
        delta = np.diff(closes)
        gain = np.where(delta > 0, delta, 0.0)
        loss = np.where(delta < 0, -delta, 0.0)
        avg_gain = np.mean(gain[:period])
        avg_loss = np.mean(loss[:period])
        for i in range(period, n - 1):
            if avg_loss == 0:
                rsi[i] = 100.0
            else:
                rs = avg_gain / (avg_loss + 1e-10)
                rsi[i] = 100.0 - 100.0 / (1.0 + rs)
            avg_gain = (avg_gain * (period - 1) + gain[i]) / period
            avg_loss = (avg_loss * (period - 1) + loss[i]) / period
        return rsi

    def _compute_bb(self, closes: np.ndarray, period: int, nbdev: float):
        n = len(closes)
        sma = np.full(n, np.nan)
        lower = np.full(n, np.nan)
        upper = np.full(n, np.nan)
        for i in range(period - 1, n):
            window = closes[i - period + 1: i + 1]
            mu = np.mean(window)
            sigma = np.std(window, ddof=1) if len(window) > 1 else 0
            sma[i] = mu
            lower[i] = mu - nbdev * sigma
            upper[i] = mu + nbdev * sigma
        return sma, lower, upper
