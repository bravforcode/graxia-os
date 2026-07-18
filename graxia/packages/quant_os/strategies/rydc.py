"""
Real-Yield Divergence Continuation (RYDC) Strategy — XAUUSD

Hypothesis: When gold's realized move diverges from what DXY/real-yield
moves imply, the divergence persists for a few days (continuation) before
being arbitraged away.

Pre-registered parameters (cannot be tuned after seeing results):
- Rolling OLS window: 60 trading days
- Residual z-score threshold: ±1.5
- Hold period: 4 trading days fixed
- Stop-loss: 1.5 × ATR(14)
- FOMC/CPI exclusion: 48h before/after events

Economic rationale:
- Gold carries no yield → opportunity cost = real risk-free rate
- Real yields ↓ → gold tailwind (falling opportunity cost)
- DXY ↓ → gold tailwind (gold is USD-denominated)
- Information diffusion lag: rates markets are fast, gold retail flow is slower

Pre-registration: hypothesis_02_real_yield_divergence.md
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from ..core.enums import RegimeType, SignalType
from .base import Signal, Strategy, StrategyConfig


@dataclass(frozen=True)
class RYDCConfig:
    """Frozen configuration — cannot be changed after instantiation."""
    ols_window: int = 60        # Rolling OLS lookback (trading days)
    z_window: int = 20          # Z-score smoothing window
    z_entry: float = 1.5        # Entry threshold
    z_exit: float = 0.5         # Exit threshold (reversion complete)
    hold_days: int = 4          # Fixed hold period
    atr_period: int = 14        # ATR for stop-loss
    atr_multiplier: float = 1.5 # Stop-loss = 1.5 × ATR
    event_exclusion_hours: int = 48  # Hours before/after FOMC/CPI to exclude


class RollingOLS:
    """Rolling OLS regression: Gold_ret = α + β1·DXY_ret + β2·ΔDFII10 + ε

    No look-ahead: coefficients estimated on data through t-1 only.
    """

    def __init__(self, window: int = 60):
        self.window = window
        self._gold_returns: list[float] = []
        self._dxy_returns: list[float] = []
        self._dfii_changes: list[float] = []
        self._residuals: list[float] = []

    def update(
        self,
        gold_ret: float,
        dxy_ret: float,
        dfii_change: float,
    ) -> float | None:
        """Add new observation, return residual z-score or None if insufficient data."""
        self._gold_returns.append(gold_ret)
        self._dxy_returns.append(dxy_ret)
        self._dfii_changes.append(dfii_change)

        if len(self._gold_returns) < self.window + 1:
            return None

        # Fit OLS on data through t-1 (no look-ahead)
        y = np.array(self._gold_returns[-(self.window + 1):-1])
        x1 = np.array(self._dxy_returns[-(self.window + 1):-1])
        x2 = np.array(self._dfii_changes[-(self.window + 1):-1])

        # Design matrix: [1, x1, x2]
        X = np.column_stack([np.ones(len(y)), x1, x2])

        try:
            # OLS: β = (X'X)^-1 X'y
            beta = np.linalg.lstsq(X, y, rcond=None)[0]
        except np.linalg.LinAlgError:
            return None

        # Predict current gold return
        predicted = beta[0] + beta[1] * dxy_ret + beta[2] * dfii_change
        residual = gold_ret - predicted
        self._residuals.append(residual)

        if len(self._residuals) < self.z_window:
            return None

        # Z-score of recent residuals
        recent = self._residuals[-self.z_window:]
        mean = np.mean(recent)
        std = np.std(recent, ddof=1)

        if std < 1e-10:
            return 0.0

        z = (residual - mean) / std
        return float(z)

    @property
    def last_residual(self) -> float | None:
        return self._residuals[-1] if self._residuals else None

    @property
    def last_z(self) -> float | None:
        if len(self._residuals) < self.z_window:
            return None
        recent = self._residuals[-self.z_window:]
        mean = np.mean(recent)
        std = np.std(recent, ddof=1)
        if std < 1e-10:
            return 0.0
        return float((self._residuals[-1] - mean) / std)


class RYDCStrategy(Strategy):
    """Real-Yield Divergence Continuation strategy for XAUUSD.

    Pre-registered: Arm A (continuation/underreaction).
    Cannot be tuned after seeing results.
    """

    def __init__(self, config: StrategyConfig | None = None):
        super().__init__(config or StrategyConfig(name="RYDC"))
        self._rydc_config = RYDCConfig()
        self._ols = RollingOLS(window=self._rydc_config.ols_window)
        self._hold_counter: int = 0
        self._last_signal_type: SignalType | None = None

    def required_features(self) -> list[str]:
        return ["dxy_close", "dfii10_close"]

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict[str, Any] | None = None,
        regime: RegimeType | None = None,
        **kwargs,
    ) -> Signal | None:
        """Generate RYDC signal.

        Requires:
        - ohlcv_data: XAUUSD OHLCV
        - indicators["dxy_close"]: DXY close prices
        - indicators["dfii10_close"]: DFII10 (real yield) values
        - kwargs["event_dates"]: list of datetime for FOMC/CPI dates
        """
        close = ohlcv_data.get("close", [])
        if len(close) < self._rydc_config.ols_window + 20:
            return None

        # Get cross-asset data
        dxy_close = indicators.get("dxy_close", []) if indicators else []
        dfii10_close = indicators.get("dfii10_close", []) if indicators else []

        if len(dxy_close) < 2 or len(dfii10_close) < 2:
            return None

        # Compute returns
        gold_ret = (float(close[-1]) / float(close[-2])) - 1.0
        dxy_ret = (float(dxy_close[-1]) / float(dxy_close[-2])) - 1.0
        dfii_change = float(dfii10_close[-1]) - float(dfii10_close[-2])

        # Update OLS and get z-score
        z_score = self._ols.update(gold_ret, dxy_ret, dfii_change)

        if z_score is None:
            return None

        # Check event exclusion (FOMC/CPI within 48h)
        event_dates = kwargs.get("event_dates", [])
        current_time = kwargs.get("current_time")
        if current_time and event_dates:
            for event_dt in event_dates:
                if isinstance(event_dt, str):
                    event_dt = datetime.fromisoformat(event_dt)
                hours_diff = abs((current_time - event_dt).total_seconds()) / 3600
                if hours_diff < self._rydc_config.event_exclusion_hours:
                    return None

        # Fixed hold period check
        if self._hold_counter > 0:
            self._hold_counter -= 1
            if self._hold_counter == 0:
                # Exit signal
                exit_signal = Signal.create(
                    strategy_id=self.id,
                    symbol=symbol,
                    signal_type=SignalType.SELL if self._last_signal_type == SignalType.BUY else SignalType.BUY,
                    confidence=0.5,
                    entry_price=float(close[-1]),
                    stop_loss=float(close[-1]),  # No stop on exit
                    take_profit=float(close[-1]),  # No TP on exit
                    regime=regime or RegimeType.RANGE_BOUND,
                )
                self._last_signal_type = None
                return exit_signal
            return None

        # Entry signals
        atr = self._atr(
            [float(c) for c in close[-self._rydc_config.atr_period:]],
            [float(h) for h in ohlcv_data.get("high", close)[-self._rydc_config.atr_period:]],
            [float(l) for l in ohlcv_data.get("low", close)[-self._rydc_config.atr_period:]],
        )

        if atr <= 0:
            return None

        current_price = float(close[-1])
        stop_distance = atr * self._rydc_config.atr_multiplier

        # Long entry: residual z > +1.5 (gold underperformed model prediction)
        if z_score > self._rydc_config.z_entry:
            sl = current_price - stop_distance
            tp = current_price + (stop_distance * 2)  # 2:1 R:R
            self._hold_counter = self._rydc_config.hold_days
            self._last_signal_type = SignalType.BUY
            return Signal.create(
                strategy_id=self.id,
                symbol=symbol,
                signal_type=SignalType.BUY,
                confidence=min(0.9, abs(z_score) / 3.0),
                entry_price=current_price,
                stop_loss=sl,
                take_profit=tp,
                regime=regime or RegimeType.RANGE_BOUND,
            )

        # Short entry: residual z < -1.5 (gold outperformed model prediction)
        if z_score < -self._rydc_config.z_entry:
            sl = current_price + stop_distance
            tp = current_price - (stop_distance * 2)  # 2:1 R:R
            self._hold_counter = self._rydc_config.hold_days
            self._last_signal_type = SignalType.SELL
            return Signal.create(
                strategy_id=self.id,
                symbol=symbol,
                signal_type=SignalType.SELL,
                confidence=min(0.9, abs(z_score) / 3.0),
                entry_price=current_price,
                stop_loss=sl,
                take_profit=tp,
                regime=regime or RegimeType.RANGE_BOUND,
            )

        return None

    def _atr(self, closes: list[float], highs: list[float], lows: list[float]) -> float:
        """Calculate Average True Range."""
        if len(closes) < 2:
            return 0.0

        tr_values = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            tr_values.append(tr)

        return sum(tr_values) / len(tr_values) if tr_values else 0.0
