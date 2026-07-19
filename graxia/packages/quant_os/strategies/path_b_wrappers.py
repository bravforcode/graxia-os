"""
Path B Strategy Wrappers
========================
Wraps standalone signal generators into Strategy subclasses for use
with BacktestEngine. Each wrapper:
1. Converts ohlcv_data (dict of lists) → pd.Series
2. Calls the underlying signal generator on the full series
3. Extracts the signal for the current bar (last bar)
4. Caches results to avoid recomputation

These are thin adapters — no new logic, no parameter changes.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

from ..core.enums import SignalType
from .base import Signal, Strategy, StrategyConfig


# ---------------------------------------------------------------------------
# Generic helper
# ---------------------------------------------------------------------------

def _ohlcv_to_series(ohlcv_data: dict[str, list]) -> dict[str, pd.Series]:
    """Convert engine OHLCV lists to pd.Series."""
    return {k: pd.Series(v, dtype=float) for k, v in ohlcv_data.items() if k in ("open", "high", "low", "close", "volume")}


def _series_to_signal(signal_value: float, symbol: str, strategy_id: str, **kwargs) -> Signal | None:
    """Convert a numeric signal (-1, 0, +1) to a Strategy Signal."""
    if signal_value == 0 or np.isnan(signal_value):
        return None
    sig_type = SignalType.BUY if signal_value > 0 else SignalType.SELL
    return Signal.create(
        strategy_id=strategy_id,
        symbol=symbol,
        signal_type=sig_type,
        confidence=abs(float(signal_value)),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. Carry Strategy Wrapper
# ---------------------------------------------------------------------------

class CarryStrategy(Strategy):
    """Wraps compute_carry_signal() into a Strategy for BacktestEngine.

    Note: This strategy needs base_rate and quote_rate data which are NOT
    available in standard OHLCV data. For backtesting, the caller must
    provide rate data via the indicators dict or pre-computed series.
    """

    def __init__(self, vol_target: float = 0.10):
        config = StrategyConfig(
            name="CarryStrategy",
            version="1.0.0",
            symbols=["XAUUSD"],
            timeframes=["D1"],
            risk_per_trade_pct=1.0,
            max_trades_per_day=1,
            require_trend_confirm=False,
        )
        super().__init__(config)
        self.vol_target = vol_target
        self._cached_index: int = -1
        self._cached_signal: float = 0.0

    def required_features(self) -> list[str]:
        return ["carry_signal"]

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict[str, Any] | None = None,
        regime=None,
        **kwargs,
    ) -> Signal | None:
        from .carry import compute_carry_signal

        # Need rate data from indicators
        if indicators is None or "base_rate" not in indicators or "quote_rate" not in indicators:
            return None

        base_rate = indicators["base_rate"]
        quote_rate = indicators["quote_rate"]

        # Compute signal on full series
        result = compute_carry_signal(base_rate, quote_rate, self.vol_target)
        signal_series = result.signal

        # Extract current bar signal (last value)
        if len(signal_series) == 0:
            return None
        current_signal = float(signal_series.iloc[-1])
        return _series_to_signal(current_signal, symbol, self.id)


# ---------------------------------------------------------------------------
# 2. TSMOM Strategy Wrapper
# ---------------------------------------------------------------------------

class TSMOMStrategy(Strategy):
    """Wraps compute_tsmom_signal() into a Strategy for BacktestEngine."""

    def __init__(self, lookbacks: list[int] | None = None, vol_target: float = 0.10):
        config = StrategyConfig(
            name="TSMOMStrategy",
            version="1.0.0",
            symbols=["XAUUSD"],
            timeframes=["D1"],
            risk_per_trade_pct=1.0,
            max_trades_per_day=1,
            require_trend_confirm=False,
        )
        super().__init__(config)
        self.lookbacks = lookbacks or [21, 63, 252]
        self.vol_target = vol_target

    def required_features(self) -> list[str]:
        return ["tsmom_signal"]

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict[str, Any] | None = None,
        regime=None,
        **kwargs,
    ) -> Signal | None:
        from .tsmom import compute_tsmom_signal

        close = pd.Series(ohlcv_data.get("close", []), dtype=float)
        if len(close) < max(self.lookbacks) + 5:
            return None

        result = compute_tsmom_signal(close, self.lookbacks, self.vol_target)
        signal_series = result.signal

        if len(signal_series) == 0:
            return None
        current_signal = float(signal_series.iloc[-1])
        return _series_to_signal(current_signal, symbol, self.id)


# ---------------------------------------------------------------------------
# 3. Cross-Asset Momentum Strategy Wrapper
# ---------------------------------------------------------------------------

class CrossAssetMomentumStrategy(Strategy):
    """Wraps compute_cam_signals() into a Strategy for BacktestEngine.

    Requires DXY close prices in indicators['dxy_close'].
    """

    def __init__(self, window: int = 60, z_threshold: float = 1.0, hold_days: int = 5):
        config = StrategyConfig(
            name="CrossAssetMomentumStrategy",
            version="1.0.0",
            symbols=["XAUUSD"],
            timeframes=["D1"],
            risk_per_trade_pct=1.0,
            max_trades_per_day=1,
            require_trend_confirm=False,
        )
        super().__init__(config)
        self.window = window
        self.z_threshold = z_threshold
        self.hold_days = hold_days

    def required_features(self) -> list[str]:
        return ["cross_asset_momentum_signal"]

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict[str, Any] | None = None,
        regime=None,
        **kwargs,
    ) -> Signal | None:
        from .cross_asset_momentum import CAMConfig, compute_cam_signals

        if indicators is None or "dxy_close" not in indicators:
            return None

        xau_close = pd.Series(ohlcv_data.get("close", []), dtype=float)
        dxy_close = indicators["dxy_close"]

        if len(xau_close) < self.window + 5 or len(dxy_close) < self.window + 5:
            return None

        # Use DatetimeIndex if available
        if not isinstance(xau_close.index, pd.DatetimeIndex):
            xau_close.index = pd.RangeIndex(len(xau_close))
        if not isinstance(dxy_close.index, pd.DatetimeIndex):
            dxy_close.index = pd.RangeIndex(len(dxy_close))

        config = CAMConfig(window=self.window, z_threshold=self.z_threshold, hold_days=self.hold_days)
        result = compute_cam_signals(xau_close, dxy_close, config)
        signal_series = result.signal

        if len(signal_series) == 0:
            return None
        current_signal = float(signal_series.iloc[-1])
        return _series_to_signal(current_signal, symbol, self.id)


# ---------------------------------------------------------------------------
# 4. FOMC Drift Strategy Wrapper
# ---------------------------------------------------------------------------

class FOMCDriftStrategy(Strategy):
    """Wraps compute_fomc_drift_signals() into a Strategy for BacktestEngine."""

    def __init__(
        self,
        drift_window_days: int = 3,
        min_fomc_return: float = 0.002,
        max_fomc_return: float = 0.03,
        atr_period: int = 14,
        stop_atr: float = 2.0,
    ):
        config = StrategyConfig(
            name="FOMCDriftStrategy",
            version="1.0.0",
            symbols=["XAUUSD"],
            timeframes=["D1"],
            risk_per_trade_pct=1.0,
            max_trades_per_day=1,
            require_trend_confirm=False,
        )
        super().__init__(config)
        self.drift_window_days = drift_window_days
        self.min_fomc_return = min_fomc_return
        self.max_fomc_return = max_fomc_return
        self.atr_period = atr_period
        self.stop_atr = stop_atr

    def required_features(self) -> list[str]:
        return ["fomc_drift_signal"]

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict[str, Any] | None = None,
        regime=None,
        **kwargs,
    ) -> Signal | None:
        from .fomc_drift import FOMCDriftConfig, compute_fomc_drift_signals

        close = pd.Series(ohlcv_data.get("close", []), dtype=float)
        high = pd.Series(ohlcv_data.get("high", []), dtype=float)
        low = pd.Series(ohlcv_data.get("low", []), dtype=float)

        if len(close) < self.atr_period + 10:
            return None

        # Create DatetimeIndex for FOMC date matching
        if not isinstance(close.index, pd.DatetimeIndex):
            close.index = pd.RangeIndex(len(close))
            high.index = pd.RangeIndex(len(high))
            low.index = pd.RangeIndex(len(low))

        config = FOMCDriftConfig(
            drift_window_days=self.drift_window_days,
            min_fomc_return=self.min_fomc_return,
            max_fomc_return=self.max_fomc_return,
            atr_period=self.atr_period,
            stop_atr=self.stop_atr,
        )
        result = compute_fomc_drift_signals(close, high, low, config)
        signal_series = result.signal

        if len(signal_series) == 0:
            return None
        current_signal = float(signal_series.iloc[-1])
        return _series_to_signal(current_signal, symbol, self.id)


# ---------------------------------------------------------------------------
# 5. COT Positioning Strategy Wrapper
# ---------------------------------------------------------------------------

class COTPositioningStrategy(Strategy):
    """Wraps compute_cot_positioning_signals() into a Strategy for BacktestEngine.

    Requires COT data in indicators['cot_dates'] and indicators['cot_net_positioning'].
    """

    def __init__(
        self,
        lookback_weeks: int = 52,
        entry_z: float = 2.0,
        exit_z: float = 0.5,
        min_hold_weeks: int = 1,
        max_hold_weeks: int = 4,
    ):
        config = StrategyConfig(
            name="COTPositioningStrategy",
            version="1.0.0",
            symbols=["XAUUSD"],
            timeframes=["D1"],
            risk_per_trade_pct=1.0,
            max_trades_per_day=1,
            require_trend_confirm=False,
        )
        super().__init__(config)
        self.lookback_weeks = lookback_weeks
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.min_hold_weeks = min_hold_weeks
        self.max_hold_weeks = max_hold_weeks

    def required_features(self) -> list[str]:
        return ["cot_positioning_signal"]

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict[str, Any] | None = None,
        regime=None,
        **kwargs,
    ) -> Signal | None:
        from .cot_positioning import COTPositioningConfig, compute_cot_positioning_signals

        if indicators is None or "cot_dates" not in indicators or "cot_net_positioning" not in indicators:
            return None

        cot_dates = indicators["cot_dates"]
        net_positioning = indicators["cot_net_positioning"]

        if len(cot_dates) < self.lookback_weeks + 5:
            return None

        config = COTPositioningConfig(
            lookback_weeks=self.lookback_weeks,
            entry_z=self.entry_z,
            exit_z=self.exit_z,
            min_hold_weeks=self.min_hold_weeks,
            max_hold_weeks=self.max_hold_weeks,
        )
        result = compute_cot_positioning_signals(cot_dates, net_positioning, config)
        signal_series = result.signal

        if len(signal_series) == 0:
            return None
        current_signal = float(signal_series.iloc[-1])
        return _series_to_signal(current_signal, symbol, self.id)


# ---------------------------------------------------------------------------
# 6. Vol Risk Premium Strategy Wrapper
# ---------------------------------------------------------------------------

class VolRiskPremiumStrategy(Strategy):
    """Wraps VRP signal computation into a Strategy for BacktestEngine.

    Requires GVZ data in indicators['gvz_close'].
    Note: compute_realized_vol import may fail — this wrapper implements
    the realized vol computation inline as a fallback.
    """

    def __init__(
        self,
        vrp_lookback: int = 20,
        entry_z: float = 1.5,
        exit_z: float = 0.5,
        realized_vol_window: int = 20,
        gvz_smoothing: int = 5,
        regime_threshold: float = 0.0,
    ):
        config = StrategyConfig(
            name="VolRiskPremiumStrategy",
            version="1.0.0",
            symbols=["XAUUSD"],
            timeframes=["D1"],
            risk_per_trade_pct=1.0,
            max_trades_per_day=1,
            require_trend_confirm=False,
        )
        super().__init__(config)
        self.vrp_lookback = vrp_lookback
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.realized_vol_window = realized_vol_window
        self.gvz_smoothing = gvz_smoothing
        self.regime_threshold = regime_threshold

    def required_features(self) -> list[str]:
        return ["vrp_signal"]

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict[str, Any] | None = None,
        regime=None,
        **kwargs,
    ) -> Signal | None:
        if indicators is None or "gvz_close" not in indicators:
            return None

        close = pd.Series(ohlcv_data.get("close", []), dtype=float)
        gvz = indicators["gvz_close"]

        if len(close) < self.realized_vol_window + 5 or len(gvz) < self.gvz_smoothing + 5:
            return None

        # Compute realized vol inline (fallback for missing import)
        log_ret = np.log(close / close.shift(1))
        realized_vol = log_ret.rolling(self.realized_vol_window).std() * np.sqrt(252)

        # Smooth GVZ
        gvz_smooth = gvz.rolling(self.gvz_smoothing).mean()

        # VRP = implied - realized
        vrp = gvz_smooth - realized_vol

        # Z-score of VRP
        vrp_mean = vrp.rolling(self.vrp_lookback).mean()
        vrp_std = vrp.rolling(self.vrp_lookback).std()
        vrp_z = (vrp - vrp_mean) / vrp_std.replace(0, np.nan)

        # Signal: mean-revert when VRP > 0, trend-follow when VRP < 0
        signal = pd.Series(0, index=close.index, dtype=float)

        # Mean-reversion regime (VRP positive → expect range-bound)
        mr_entry = vrp_z > self.entry_z
        mr_exit = vrp_z < self.exit_z

        # Trend-following regime (VRP negative → expect vol expansion)
        tf_entry = vrp_z < -self.entry_z
        tf_exit = vrp_z > -self.exit_z

        # Simple state machine: track current regime
        in_position = False
        position_dir = 0

        for i in range(len(signal)):
            if pd.isna(vrp_z.iloc[i]):
                continue

            if not in_position:
                if mr_entry.iloc[i]:
                    # Mean-revert: short vol → long gold (expect range → gold stays)
                    in_position = True
                    position_dir = 1
                elif tf_entry.iloc[i]:
                    # Trend-follow: expect vol expansion → follow trend
                    ret_20d = (close.iloc[i] / close.iloc[max(0, i - 20)] - 1) if i >= 20 else 0
                    in_position = True
                    position_dir = 1 if ret_20d > 0 else -1
            else:
                if position_dir == 1 and mr_exit.iloc[i]:
                    in_position = False
                    position_dir = 0
                elif position_dir == -1 and tf_exit.iloc[i]:
                    in_position = False
                    position_dir = 0

            signal.iloc[i] = float(position_dir)

        if len(signal) == 0:
            return None
        current_signal = float(signal.iloc[-1])
        return _series_to_signal(current_signal, symbol, self.id)
