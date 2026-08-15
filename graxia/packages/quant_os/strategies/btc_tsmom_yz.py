"""BTCUSD TSMOM with Yang-Zhang vol estimator + vol targeting (Direction G trial 8003).

Frozen per research/pre_registration/trial_8003_btc_tsmom_yz.md (2026-08-06).
Evidence: Baltas-Kosowski (SSRN 2140091) — efficient vol estimators cut
turnover with no performance loss; Moreira-Muir (JF 2017) — scale exposure by
inverse of lagged realized variance raises Sharpe.

Frozen parameters:
    signal_tf:        D1  (slow momentum signal — 12-month lookback)
    momentum_lookback: 252 D1 bars (12 months)
    yz_lookback:      63 D1 bars (3 months) for Yang-Zhang vol
    target_vol_annual: 0.20 (vol targeting, Moreira-Muir)
    direction:        long when 12m return > 0, else flat (no crypto shorts)
    max_positions:    1
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import numpy as np

from ..core.enums import RegimeType, SignalType
from .base import Signal, Strategy, StrategyConfig

MOMENTUM_LOOKBACK = 252  # D1 bars = 12 months
YZ_LOOKBACK = 63  # D1 bars = 3 months
TARGET_VOL_ANNUAL = 0.20
TRADING_DAYS = 252


def _yang_zhang_vol(open_: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    """Efficient Yang-Zhang volatility estimator (Baltas-Kosowski preferred).

    YZ = sqrt(close-vol + open-vol + Rogers-Satchell), annualized.
    Returns NaN until `period` bars available. Handles zero open-to-close
    (log 0) defensively.
    """
    n = len(close)
    out = np.full(n, np.nan, dtype=np.float64)
    if n < period + 1:
        return out

    def _safe_log(x: np.ndarray) -> np.ndarray:
        return np.where(x > 0, np.log(x), 0.0)

    log_h_o = _safe_log(high[1:] / open_[1:])
    log_l_o = _safe_log(low[1:] / open_[1:])
    log_c_o = _safe_log(close[1:] / open_[1:])
    log_o_c = _safe_log(open_[1:] / close[:-1])

    # Rogers-Satchell (open-to-close overnight term)
    rs = log_h_o * (log_h_o - log_c_o) + log_l_o * (log_l_o - log_c_o)
    # Overnight (close-to-open) variance
    overnight = log_o_c**2
    # Intraday (open-to-close) variance
    intraday = log_c_o**2

    for i in range(period, n):
        s = slice(i - period + 1, i + 1)
        k = 0.34 / (1.34 + (period + 1) / (period - 1))
        var_rs = float(np.mean(rs[s]))
        var_overnight = float(np.mean(overnight[s]))
        var_intraday = float(np.mean(intraday[s]))
        var_total = var_overnight + k * var_intraday + (1 - k) * var_rs
        out[i] = float(np.sqrt(max(var_total, 0.0))) * np.sqrt(TRADING_DAYS)
    return out


class BtcTsmomYz(Strategy):
    """BTCUSD slow time-series momentum, Yang-Zhang vol, vol-targeted sizing."""

    def __init__(
        self,
        momentum_lookback: int = MOMENTUM_LOOKBACK,
        yz_lookback: int = YZ_LOOKBACK,
        target_vol_annual: float = TARGET_VOL_ANNUAL,
    ):
        config = StrategyConfig(
            name="BtcTsmomYz",
            version="1.0",
            symbols=["BTCUSD"],
            timeframes=["D1"],
            risk_per_trade_pct=1.0,
            max_trades_per_day=1,
            min_confidence=0.0,
            min_risk_reward=0.0,
            require_trend_confirm=False,
        )
        super().__init__(config)
        self.momentum_lookback = momentum_lookback
        self.yz_lookback = yz_lookback
        self.target_vol_annual = target_vol_annual

    def required_features(self) -> list[str]:
        return ["yang_zhang_vol"]

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict | None = None,
        regime: RegimeType | None = None,
        current_time: datetime | None = None,
        **kwargs,
    ) -> Signal | None:
        open_ = ohlcv_data.get("open", [])
        high = ohlcv_data.get("high", [])
        low = ohlcv_data.get("low", [])
        close = ohlcv_data.get("close", [])

        min_bars = self.momentum_lookback + self.yz_lookback + 5
        if len(close) < min_bars:
            return None

        close_arr = np.array([float(c) for c in close], dtype=np.float64)
        open_arr = np.array([float(o) for o in open_], dtype=np.float64)
        high_arr = np.array([float(h) for h in high], dtype=np.float64)
        low_arr = np.array([float(lo) for lo in low], dtype=np.float64)

        # Momentum: 12-month return (slow — position-level, not bar-level)
        mom_return = close_arr[-1] / close_arr[-1 - self.momentum_lookback] - 1.0
        if mom_return <= 0:
            return None  # flat when momentum non-positive (TSMOM long-only)

        # Yang-Zhang vol at current bar
        yz = _yang_zhang_vol(open_arr, high_arr, low_arr, close_arr, self.yz_lookback)
        yz_now = yz[-1]
        if np.isnan(yz_now) or yz_now <= 0:
            return None

        # Vol targeting: scale = target_vol / realized_vol (clamp 0.5-2.0)
        scale = float(np.clip(self.target_vol_annual / yz_now, 0.5, 2.0))

        entry = Decimal(str(close_arr[-1]))
        # Risk-based SL: 2x daily vol as stop distance (vol-scaled)
        daily_vol = yz_now / np.sqrt(TRADING_DAYS)
        sl_dist = Decimal(str(max(float(daily_vol) * 2.0, 1e-9)))
        tp_dist = sl_dist * 2  # R:R 1:2

        # Confidence from momentum strength (slow signal → lower confidence)
        confidence = float(np.clip(0.5 + mom_return * 2.0, 0.5, 0.9))

        return Signal.create(
            strategy_id=self.id,
            symbol=symbol,
            signal_type=SignalType.BUY,
            confidence=confidence,
            entry_price=entry,
            stop_loss=entry - sl_dist,
            take_profit=entry + tp_dist,
            indicator_values={
                "mom_12m": float(mom_return),
                "yang_zhang_vol_annual": float(yz_now),
                "vol_scale": scale,
            },
        )
