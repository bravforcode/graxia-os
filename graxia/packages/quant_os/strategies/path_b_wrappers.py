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


def _compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    """Compute ATR from OHLCV series. Returns latest ATR value."""
    if len(high) < period + 1:
        return 0.0
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=period, min_periods=period).mean()
    return float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else 0.0


def _signal_with_atr_sl_tp(
    signal_value: float, symbol: str, strategy_id: str,
    ohlcv_data: dict[str, list], sl_mult: float = 2.0, tp_mult: float = 3.0,
    **kwargs,
) -> Signal | None:
    """Create Signal with ATR-based SL/TP (fixes MISSING_SL engine rejection)."""
    if signal_value == 0 or np.isnan(signal_value):
        return None

    sig_type = SignalType.BUY if signal_value > 0 else SignalType.SELL
    entry = float(ohlcv_data["close"][-1]) if ohlcv_data.get("close") else None

    atr = _compute_atr(
        pd.Series(ohlcv_data.get("high", []), dtype=float),
        pd.Series(ohlcv_data.get("low", []), dtype=float),
        pd.Series(ohlcv_data.get("close", []), dtype=float),
    )

    sl = tp = None
    if entry and atr > 0:
        if sig_type == SignalType.BUY:
            sl = Decimal(str(entry - atr * sl_mult))
            tp = Decimal(str(entry + atr * tp_mult))
        else:
            sl = Decimal(str(entry + atr * sl_mult))
            tp = Decimal(str(entry - atr * tp_mult))

    return Signal.create(
        strategy_id=strategy_id,
        symbol=symbol,
        signal_type=sig_type,
        confidence=abs(float(signal_value)),
        entry_price=Decimal(str(entry)) if entry else None,
        stop_loss=sl,
        take_profit=tp,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. Carry Strategy Wrapper
# ---------------------------------------------------------------------------

class CarryStrategy(Strategy):
    """Wraps compute_carry_signal() into a Strategy for BacktestEngine.

    Note: This strategy needs base_rate and quote_rate data which are NOT
    available in standard OHLCV data. For backtesting, the caller must
    provide rate data via set_external_data() or the indicators dict.
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
        self._base_rate: pd.Series | None = None
        self._quote_rate: pd.Series | None = None
        self._cached_signal_len: int = -1
        self._cached_signal_series: pd.Series | None = None

    def set_external_data(self, **kwargs) -> None:
        """Inject external data (base_rate, quote_rate) before engine.run()."""
        if "base_rate" in kwargs:
            self._base_rate = kwargs["base_rate"]
        if "quote_rate" in kwargs:
            self._quote_rate = kwargs["quote_rate"]

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
        # Fast path: use pre-computed signal from edge_search_all.py
        if indicators is not None and "_precomputed_signal" in indicators:
            precomp = indicators["_precomputed_signal"]
            if precomp:
                sig_val = float(precomp[-1])
                return _signal_with_atr_sl_tp(sig_val, symbol, self.id, ohlcv_data)

        from .carry import compute_carry_signal

        # Prefer external data (set via set_external_data), fall back to indicators
        base_rate = self._base_rate
        quote_rate = self._quote_rate
        if base_rate is None and indicators is not None:
            base_rate = indicators.get("base_rate")
        if quote_rate is None and indicators is not None:
            quote_rate = indicators.get("quote_rate")

        if base_rate is None or quote_rate is None:
            return None

        # Convert list to Series if needed (engine slices indicators as lists)
        if isinstance(base_rate, list):
            base_rate = pd.Series(base_rate, dtype=float)
        if isinstance(quote_rate, list):
            quote_rate = pd.Series(quote_rate, dtype=float)

        # Cache: recompute only when input length changes
        cur_len = len(base_rate)
        if self._cached_signal_series is not None and self._cached_signal_len == cur_len:
            signal_series = self._cached_signal_series
        else:
            result = compute_carry_signal(base_rate, quote_rate, self.vol_target)
            signal_series = result.signal
            self._cached_signal_len = cur_len
            self._cached_signal_series = signal_series

        # Extract current bar signal (last value)
        if len(signal_series) == 0:
            return None
        current_signal = float(signal_series.iloc[-1])
        return _signal_with_atr_sl_tp(current_signal, symbol, self.id, ohlcv_data)


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
        self._cached_signal_len: int = -1
        self._cached_signal_series: pd.Series | None = None

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
        # Fast path: use pre-computed signal
        if indicators is not None and "_precomputed_signal" in indicators:
            precomp = indicators["_precomputed_signal"]
            if precomp:
                return _signal_with_atr_sl_tp(float(precomp[-1]), symbol, self.id, ohlcv_data)

        from .tsmom import compute_tsmom_signal

        close = pd.Series(ohlcv_data.get("close", []), dtype=float)
        if len(close) < max(self.lookbacks) + 5:
            return None

        # Cache: recompute only when input length changes
        cur_len = len(close)
        if self._cached_signal_series is not None and self._cached_signal_len == cur_len:
            signal_series = self._cached_signal_series
        else:
            result = compute_tsmom_signal(close, self.lookbacks, self.vol_target)
            signal_series = result.signal
            self._cached_signal_len = cur_len
            self._cached_signal_series = signal_series

        if len(signal_series) == 0:
            return None
        current_signal = float(signal_series.iloc[-1])
        return _signal_with_atr_sl_tp(current_signal, symbol, self.id, ohlcv_data)


# ---------------------------------------------------------------------------
# 3. Cross-Asset Momentum Strategy Wrapper
# ---------------------------------------------------------------------------

class CrossAssetMomentumStrategy(Strategy):
    """Wraps compute_cam_signals() into a Strategy for BacktestEngine.

    Requires DXY close prices — inject via set_external_data(dxy_close=...) or indicators['dxy_close'].
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
        self._dxy_close: pd.Series | None = None
        self._cached_signal_len: int = -1
        self._cached_signal_series: pd.Series | None = None

    def set_external_data(self, **kwargs) -> None:
        """Inject external data (dxy_close) before engine.run()."""
        if "dxy_close" in kwargs:
            self._dxy_close = kwargs["dxy_close"]

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
        # Fast path: use pre-computed signal
        if indicators is not None and "_precomputed_signal" in indicators:
            precomp = indicators["_precomputed_signal"]
            if precomp:
                return _signal_with_atr_sl_tp(float(precomp[-1]), symbol, self.id, ohlcv_data)

        from .cross_asset_momentum import CAMConfig, compute_cam_signals

        xau_close = pd.Series(ohlcv_data.get("close", []), dtype=float)

        # Prefer external data, fall back to indicators
        dxy_close = self._dxy_close
        if dxy_close is None and indicators is not None:
            dxy_close = indicators.get("dxy_close")

        if dxy_close is None:
            return None

        # Convert list to Series if needed (engine slices indicators as lists)
        if isinstance(dxy_close, list):
            dxy_close = pd.Series(dxy_close, dtype=float)

        if len(xau_close) < self.window + 5 or len(dxy_close) < self.window + 5:
            return None

        # Use DatetimeIndex if available
        if not isinstance(xau_close.index, pd.DatetimeIndex):
            xau_close.index = pd.RangeIndex(len(xau_close))
        if not isinstance(dxy_close.index, pd.DatetimeIndex):
            dxy_close.index = pd.RangeIndex(len(dxy_close))
        # Ensure indices match (critical for compute_cam_signals alignment)
        # When engine slices, dxy may be longer than xau — trim to match
        if isinstance(dxy_close, pd.Series) and len(dxy_close) > len(xau_close):
            dxy_close = dxy_close.iloc[:len(xau_close)].reset_index(drop=True)
        if len(dxy_close) == len(xau_close) and not dxy_close.index.equals(xau_close.index):
            dxy_close.index = xau_close.index

        # Cache: recompute only when input length changes
        cur_len = len(xau_close)
        if self._cached_signal_series is not None and self._cached_signal_len == cur_len:
            signal_series = self._cached_signal_series
        else:
            config = CAMConfig(window=self.window, z_threshold=self.z_threshold, hold_days=self.hold_days)
            result = compute_cam_signals(xau_close, dxy_close, config)
            signal_series = result.signal
            self._cached_signal_len = cur_len
            self._cached_signal_series = signal_series

        if len(signal_series) == 0:
            return None
        current_signal = float(signal_series.iloc[-1])
        return _signal_with_atr_sl_tp(current_signal, symbol, self.id, ohlcv_data)


# ---------------------------------------------------------------------------
# 4. FOMC Drift Strategy Wrapper
# ---------------------------------------------------------------------------

class FOMCDriftStrategy(Strategy):
    """Wraps compute_fomc_drift_signals() into a Strategy for BacktestEngine.

    Requires timestamps — inject via set_external_data(timestamps=...) or indicators['_timestamps'].
    """

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
        self._timestamps: list | None = None
        self._cached_signal_len: int = -1
        self._cached_signal_series: pd.Series | None = None

    def set_external_data(self, **kwargs) -> None:
        """Inject timestamps before engine.run()."""
        if "timestamps" in kwargs:
            self._timestamps = kwargs["timestamps"]

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
        # Fast path: use pre-computed signal
        if indicators is not None and "_precomputed_signal" in indicators:
            precomp = indicators["_precomputed_signal"]
            if precomp:
                return _signal_with_atr_sl_tp(float(precomp[-1]), symbol, self.id, ohlcv_data)

        from .fomc_drift import FOMCDriftConfig, compute_fomc_drift_signals

        close = pd.Series(ohlcv_data.get("close", []), dtype=float)
        high = pd.Series(ohlcv_data.get("high", []), dtype=float)
        low = pd.Series(ohlcv_data.get("low", []), dtype=float)

        if len(close) < self.atr_period + 10:
            return None

        # Create DatetimeIndex for FOMC date matching
        # Prefer timestamps from indicators (auto-sliced by engine), then set_external_data, then kwargs
        ts = None
        if indicators is not None and "_timestamps" in indicators:
            ts = indicators["_timestamps"]
        elif self._timestamps is not None:
            # Fallback: slice full timestamps to match ohlcv length
            n = len(close)
            ts = self._timestamps[:n] if len(self._timestamps) >= n else None
        if ts is None:
            ts = kwargs.get("timestamps")

        if ts is not None and len(ts) == len(close):
            dt_idx = pd.DatetimeIndex(ts)
            close.index = dt_idx
            high.index = dt_idx
            low.index = dt_idx
        elif not isinstance(close.index, pd.DatetimeIndex):
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
        # Cache: recompute only when input length changes
        cur_len = len(close)
        if self._cached_signal_series is not None and self._cached_signal_len == cur_len:
            signal_series = self._cached_signal_series
        else:
            result = compute_fomc_drift_signals(close, high, low, config)
            signal_series = result.signal
            self._cached_signal_len = cur_len
            self._cached_signal_series = signal_series

        if len(signal_series) == 0:
            return None
        current_signal = float(signal_series.iloc[-1])
        return _signal_with_atr_sl_tp(current_signal, symbol, self.id, ohlcv_data)


# ---------------------------------------------------------------------------
# 5. COT Positioning Strategy Wrapper
# ---------------------------------------------------------------------------

class COTPositioningStrategy(Strategy):
    """Wraps compute_cot_positioning_signals() into a Strategy for BacktestEngine.

    Requires COT data — inject via set_external_data() or indicators dict.
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
        self._cot_dates: pd.Series | None = None
        self._cot_net_positioning: pd.Series | None = None
        self._cached_signal_len: int = -1
        self._cached_signal_series: pd.Series | None = None

    def set_external_data(self, **kwargs) -> None:
        """Inject COT data before engine.run()."""
        if "cot_dates" in kwargs:
            self._cot_dates = kwargs["cot_dates"]
        if "cot_net_positioning" in kwargs:
            self._cot_net_positioning = kwargs["cot_net_positioning"]

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
        # Fast path: use pre-computed signal
        if indicators is not None and "_precomputed_signal" in indicators:
            precomp = indicators["_precomputed_signal"]
            if precomp:
                return _signal_with_atr_sl_tp(float(precomp[-1]), symbol, self.id, ohlcv_data)

        from .cot_positioning import COTPositioningConfig, compute_cot_positioning_signals

        # Prefer external data, fall back to indicators
        cot_dates = self._cot_dates
        net_positioning = self._cot_net_positioning
        if cot_dates is None and indicators is not None:
            cot_dates = indicators.get("cot_dates")
        if net_positioning is None and indicators is not None:
            net_positioning = indicators.get("cot_net_positioning")

        if cot_dates is None or net_positioning is None:
            return None

        # Convert list to Series if needed (engine slices indicators as lists)
        if isinstance(cot_dates, list):
            cot_dates = pd.Series(cot_dates)
        if isinstance(net_positioning, list):
            net_positioning = pd.Series(net_positioning, dtype=float)

        if len(cot_dates) < self.lookback_weeks + 5:
            return None

        # Cache: recompute only when input length changes
        cur_len = len(cot_dates)
        if self._cached_signal_series is not None and self._cached_signal_len == cur_len:
            signal_series = self._cached_signal_series
        else:
            config = COTPositioningConfig(
                lookback_weeks=self.lookback_weeks,
                entry_z=self.entry_z,
                exit_z=self.exit_z,
                min_hold_weeks=self.min_hold_weeks,
                max_hold_weeks=self.max_hold_weeks,
            )
            result = compute_cot_positioning_signals(cot_dates, net_positioning, config)
            signal_series = result.signal
            self._cached_signal_len = cur_len
            self._cached_signal_series = signal_series

        if len(signal_series) == 0:
            return None
        current_signal = float(signal_series.iloc[-1])
        return _signal_with_atr_sl_tp(current_signal, symbol, self.id, ohlcv_data)


# ---------------------------------------------------------------------------
# 6. Vol Risk Premium Strategy Wrapper
# ---------------------------------------------------------------------------

class VolRiskPremiumStrategy(Strategy):
    """Wraps VRP signal computation into a Strategy for BacktestEngine.

    Requires GVZ data — inject via set_external_data(gvz_close=...) or indicators['gvz_close'].
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
        self._gvz_close: pd.Series | None = None
        self._cached_signal_len: int = -1
        self._cached_signal_series: pd.Series | None = None

    def set_external_data(self, **kwargs) -> None:
        """Inject GVZ data before engine.run()."""
        if "gvz_close" in kwargs:
            self._gvz_close = kwargs["gvz_close"]

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
        # Fast path: use pre-computed signal
        if indicators is not None and "_precomputed_signal" in indicators:
            precomp = indicators["_precomputed_signal"]
            if precomp:
                return _signal_with_atr_sl_tp(float(precomp[-1]), symbol, self.id, ohlcv_data)

        # Prefer external data, fall back to indicators
        gvz = self._gvz_close
        if gvz is None and indicators is not None:
            gvz = indicators.get("gvz_close")
        if gvz is None:
            return None

        # Convert list to Series if needed (engine slices indicators as lists)
        if isinstance(gvz, list):
            gvz = pd.Series(gvz, dtype=float)

        close = pd.Series(ohlcv_data.get("close", []), dtype=float)

        if len(close) < self.realized_vol_window + 5 or len(gvz) < self.gvz_smoothing + 5:
            return None

        # Align GVZ to close's index (fix index mismatch between DatetimeIndex and RangeIndex)
        # When engine slices, close may have fewer bars than full gvz Series
        if isinstance(gvz, pd.Series) and isinstance(close.index, pd.RangeIndex) and not isinstance(gvz.index, pd.RangeIndex):
            # GVZ has DatetimeIndex, close has RangeIndex — slice GVZ to match close length
            gvz = gvz.iloc[:len(close)].reset_index(drop=True)
        elif len(gvz) == len(close) and not gvz.index.equals(close.index):
            gvz.index = close.index

        # Cache: recompute only when input length changes
        cur_len = len(close)
        if self._cached_signal_series is not None and self._cached_signal_len == cur_len:
            current_signal = float(self._cached_signal_series.iloc[-1])
            return _signal_with_atr_sl_tp(current_signal, symbol, self.id, ohlcv_data)

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

        # Mean-reversion regime (VRP positive -> expect range-bound)
        mr_entry = vrp_z > self.entry_z
        mr_exit = vrp_z < self.exit_z

        # Trend-following regime (VRP negative -> expect vol expansion)
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
                    # Mean-revert: short vol -> long gold (expect range -> gold stays)
                    in_position = True
                    position_dir = 1
                elif tf_entry.iloc[i]:
                    # Trend-follow: expect vol expansion -> follow trend
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

        self._cached_signal_len = cur_len
        self._cached_signal_series = signal

        if len(signal) == 0:
            return None
        current_signal = float(signal.iloc[-1])
        return _signal_with_atr_sl_tp(current_signal, symbol, self.id, ohlcv_data)
