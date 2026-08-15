"""
Donchian breakout, engine-compatible port — P1 rigor pass for donchian_20 /
donchian_vol_filter (see comprehensive_edge_search.py's prong_holdout()).

BacktestEngine requires a real, correctly-directioned stop_loss on every
executed signal (_execute_signal rejects MISSING_SL/INVALID_SL_DIRECTION) and
has no native "flatten to neutral" signal path (main loop only dispatches
BUY/SELL). The original construction used no SL (pure flip-until-reversal,
tracked as a vectorized position series). Two documented approximations
bridge that gap, both chosen to err toward showing MORE edge than the
original, not less — so a REJECT verdict survives as conservative evidence,
not an artifact of an over-tight port:

  - stop_loss = the opposite Donchian band at signal time (the strategy's
    own exit trigger, not an invented overlay). Static at entry, unlike the
    original's per-bar-recomputed band — this holds trades longer than the
    dynamic band would, i.e. more chance to show edge, not less.
  - vol_filter_mode="skip_high_vol": the original forces position to flat
    (0) on every high-vol bar (vol_pctile > 0.7), regardless of the
    underlying breakout direction. This port only suppresses NEW entries on
    high-vol bars and holds an already-open position through them instead
    of force-flattening. Strict superset of the original's exposure.
"""

from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd

from ..core.enums import RegimeType, SignalType
from .base import Signal, Strategy, StrategyConfig


class DonchianBandStop(Strategy):
    """Donchian channel breakout with a band-based stop.

    vol_filter_mode:
      "none"          -> donchian_20 (plain, unfiltered)
      "skip_high_vol" -> donchian_vol_filter (suppress new entries when
                          trailing vol sits above vol_pctile_threshold of
                          its own vol_rank_window-bar history)
    """

    def __init__(
        self,
        period: int = 20,
        vol_filter_mode: str = "none",
        vol_lookback: int = 20,
        vol_rank_window: int = 100,
        vol_pctile_threshold: float = 0.7,
        config: StrategyConfig | None = None,
    ):
        super().__init__(
            config
            or StrategyConfig(
                name="DonchianBandStop",
                version="1.0.0",
                symbols=["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30", "BTCUSD"],
                min_confidence=0.65,
            )
        )
        if vol_filter_mode not in ("none", "skip_high_vol"):
            raise ValueError(f"vol_filter_mode must be 'none' or 'skip_high_vol', got {vol_filter_mode!r}")
        self.period = period
        self.vol_filter_mode = vol_filter_mode
        self.vol_lookback = vol_lookback
        self.vol_rank_window = vol_rank_window
        self.vol_pctile_threshold = vol_pctile_threshold

        # Running state — safe because pooled_strategy_test.py's
        # strategy_factory() contract creates one fresh instance per
        # single, strictly-sequential BacktestEngine.run() pass.
        self._raw_pos = 0
        self._eff_pos = 0

    def _is_high_vol(self, close: list) -> bool:
        needed = self.vol_lookback + self.vol_rank_window + 1
        if len(close) < needed:
            return False  # insufficient history -> don't filter (errs toward more trades)
        s = pd.Series(close[-needed:])
        rets = s.pct_change().dropna()
        vol = rets.rolling(self.vol_lookback).std().dropna()
        if len(vol) < self.vol_rank_window:
            return False
        tail = vol.iloc[-self.vol_rank_window :]
        pctile = tail.rank(pct=True).iloc[-1]
        return bool(pctile > self.vol_pctile_threshold)

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict | None = None,
        regime: RegimeType | None = None,
        **kwargs,
    ) -> Signal | None:
        close = ohlcv_data.get("close", [])
        high = ohlcv_data.get("high", [])
        low = ohlcv_data.get("low", [])
        n = len(close)
        if n < self.period + 1:
            return None

        hh = max(high[-(self.period + 1) : -1])
        ll = min(low[-(self.period + 1) : -1])
        c = close[-1]

        if c > hh:
            self._raw_pos = 1
        elif c < ll:
            self._raw_pos = -1

        if self.vol_filter_mode == "skip_high_vol" and self._is_high_vol(close):
            return None  # high-vol: hold current effective position, suppress catch-up

        if self._raw_pos == self._eff_pos or self._raw_pos == 0:
            return None

        self._eff_pos = self._raw_pos
        current_price = Decimal(str(c))

        if self._raw_pos == 1:
            return Signal.create(
                strategy_id=self.config.name,
                symbol=symbol,
                signal_type=SignalType.BUY,
                confidence=0.65,
                entry_price=current_price,
                stop_loss=Decimal(str(ll)),
                notes=f"Donchian({self.period}) flip long @ {c:.5f}, band=[{ll:.5f},{hh:.5f}]",
                indicator_values={"donchian_high": hh, "donchian_low": ll, "direction": "up"},
            )
        else:
            return Signal.create(
                strategy_id=self.config.name,
                symbol=symbol,
                signal_type=SignalType.SELL,
                confidence=0.65,
                entry_price=current_price,
                stop_loss=Decimal(str(hh)),
                notes=f"Donchian({self.period}) flip short @ {c:.5f}, band=[{ll:.5f},{hh:.5f}]",
                indicator_values={"donchian_high": hh, "donchian_low": ll, "direction": "down"},
            )

    def required_features(self) -> list[str]:
        return ["high", "low", "close"]
