"""
Time-series momentum + DXY-divergence filter, engine-compatible port —
P1 rigor pass for tsm_dxy_divergence (comprehensive_edge_search.py's
prong_holdout(): 4-lookback vol-scaled TSM ensemble, sign-gated by whether
the traded symbol's return diverges from DXY's same-bar return).

ADMITTED PROXIES — this candidate, unlike the two Donchian variants, has no
native price level to use as a stop and no native "flatten to neutral"
signal path is available in BacktestEngine (main loop only dispatches
BUY/SELL; _execute_signal rejects any signal with a missing/invalid
stop_loss). Both approximations below are deliberately looser than the
original, so a REJECT verdict remains conservative evidence, not an
artifact of an over-tight port:

  - stop_loss: TSM's real exit is "tomorrow's TSM sign recomputes
    differently" — not a price level. A wide ATR-based stop (default
    atr_sl_mult=4.0) is attached purely to satisfy the engine's hard-SL
    requirement; it is sized to rarely bind so the TSM sign-flip stays the
    dominant exit path.
  - divergence filter: the original forces position to flat (0) on every
    bar where the symbol's return does not diverge from DXY's. This port
    only suppresses NEW entries on non-divergent bars and holds an
    already-open position through them — a strict superset of the
    original's exposure.
  - Requires data/DXY_D1.csv. Bars with no matching DXY date abstain (no
    signal) rather than silently falling back to unfiltered TSM — this caps
    effective coverage to DXY's own history window.
  - Applying a DXY-divergence filter to non-FX/non-metals assets (equity
    indices, crypto) is a questionable premise carried over unchanged from
    the original construction; treat pooled results for NAS100/US30/BTCUSD
    as lower-confidence for this reason.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from ..core.enums import RegimeType, SignalType
from .base import Signal, Strategy, StrategyConfig

_DEFAULT_LOOKBACKS = (20, 40, 60, 120)


class TSMDXYDivergence(Strategy):
    def __init__(
        self,
        lookbacks: tuple[int, ...] = _DEFAULT_LOOKBACKS,
        atr_period: int = 14,
        atr_sl_mult: float = 4.0,
        dxy_returns: dict | None = None,
        dxy_csv_path: str | None = None,
        config: StrategyConfig | None = None,
    ):
        super().__init__(
            config
            or StrategyConfig(
                name="TSMDXYDivergence",
                version="1.0.0",
                symbols=["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30", "BTCUSD"],
                min_confidence=0.6,
            )
        )
        self.lookbacks = tuple(lookbacks)
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self._dxy_returns = dxy_returns if dxy_returns is not None else self._load_dxy_returns(dxy_csv_path)

        # Running state — safe because pooled_strategy_test.py's
        # strategy_factory() contract creates one fresh instance per
        # single, strictly-sequential BacktestEngine.run() pass.
        self._eff_pos = 0

    @staticmethod
    def _load_dxy_returns(csv_path: str | None) -> dict:
        path = Path(csv_path) if csv_path else Path(__file__).resolve().parent.parent / "data" / "DXY_D1.csv"
        if not path.exists():
            return {}
        df = pd.read_csv(path)
        ts_col = "time" if "time" in df.columns else "date"
        df[ts_col] = pd.to_datetime(df[ts_col])
        df = df.sort_values(ts_col)
        df["ret"] = df["close"].pct_change()
        return {row[ts_col].date(): row["ret"] for _, row in df.iterrows() if pd.notna(row["ret"])}

    def _tsm_direction(self, close: list) -> int:
        arr = np.asarray(close, dtype=float)
        if len(arr) < max(self.lookbacks) + 1:
            return 0
        rets = np.diff(arr) / arr[:-1]
        total = 0.0
        for lb in self.lookbacks:
            window = rets[-lb:]
            r_vol = window.std()
            if r_vol == 0:
                continue
            total += window.sum() / r_vol
        if total == 0.0:
            return 0
        return 1 if total > 0 else -1

    def _atr(self, high: list, low: list, close: list) -> float:
        h = np.asarray(high[-(self.atr_period + 1) :], dtype=float)
        l = np.asarray(low[-(self.atr_period + 1) :], dtype=float)
        c = np.asarray(close[-(self.atr_period + 1) :], dtype=float)
        tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
        return float(tr.mean())

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
        min_len = max(self.lookbacks) + self.atr_period + 2
        if n < min_len:
            return None

        current_time = kwargs.get("current_time")
        if current_time is None:
            return None
        bar_date = current_time.date() if hasattr(current_time, "date") else current_time
        dxy_ret = self._dxy_returns.get(bar_date)
        if dxy_ret is None:
            return None  # abstain: no DXY data for this bar

        tsm_dir = self._tsm_direction(close)
        if tsm_dir == 0:
            return None

        # "returns" in the original prong = same-bar simple return of the
        # traded symbol, compared against DXY's same-bar simple return.
        sym_ret = (close[-1] - close[-2]) / close[-2] if close[-2] != 0 else 0.0
        sym_sign = 1 if sym_ret > 0 else (-1 if sym_ret < 0 else 0)
        dxy_sign = 1 if dxy_ret > 0 else (-1 if dxy_ret < 0 else 0)
        divergence = sym_sign * (-dxy_sign)

        if divergence < 0:
            return None  # confirmation failed: hold current position, no new entry

        if tsm_dir == self._eff_pos:
            return None  # already positioned this way

        atr = self._atr(high, low, close)
        if atr <= 0:
            return None

        self._eff_pos = tsm_dir
        current_price = Decimal(str(close[-1]))
        sl_dist = Decimal(str(atr * self.atr_sl_mult))

        if tsm_dir == 1:
            return Signal.create(
                strategy_id=self.config.name,
                symbol=symbol,
                signal_type=SignalType.BUY,
                confidence=0.6,
                entry_price=current_price,
                stop_loss=current_price - sl_dist,
                notes=f"TSM+DXYdiv long, atr={atr:.5f}",
                indicator_values={"tsm_dir": tsm_dir, "dxy_ret": dxy_ret, "sym_ret": sym_ret},
            )
        else:
            return Signal.create(
                strategy_id=self.config.name,
                symbol=symbol,
                signal_type=SignalType.SELL,
                confidence=0.6,
                entry_price=current_price,
                stop_loss=current_price + sl_dist,
                notes=f"TSM+DXYdiv short, atr={atr:.5f}",
                indicator_values={"tsm_dir": tsm_dir, "dxy_ret": dxy_ret, "sym_ret": sym_ret},
            )

    def required_features(self) -> list[str]:
        return ["high", "low", "close"]
