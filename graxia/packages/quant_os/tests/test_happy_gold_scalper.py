"""Tests for Happy Gold-style M15 XAUUSD scalper (trial 1034 pre-registration)."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from graxia.packages.quant_os.core.enums import SignalType
from graxia.packages.quant_os.strategies.happy_gold_scalper import HappyGoldScalper


def _ohlcv(close: list[float], high: list[float] | None = None, low: list[float] | None = None) -> dict:
    """Build OHLCV dict with default high/low = close +/- buffer."""
    n = len(close)
    highs = high if high is not None else [c + 0.5 for c in close]
    lows = low if low is not None else [c - 0.5 for c in close]
    return {
        "open": close,
        "high": highs,
        "low": lows,
        "close": close,
        "volume": [0] * n,
    }


def _london_open() -> datetime:
    return datetime(2025, 6, 2, 9, 0, tzinfo=UTC)  # London session


def _make_price_series(n: int = 80, start: float = 3300.0) -> list[float]:
    """Upward trend with a small pullback near the end, then a breakout."""
    rng = np.random.default_rng(42)
    rets = np.concatenate([rng.normal(0.0003, 0.001, n - 15), rng.normal(-0.0002, 0.0005, 10), [0.004] * 5])
    close = float(start) * np.cumprod(1 + rets)
    return close.tolist()


def _make_downtrend(n: int = 80, start: float = 3300.0) -> list[float]:
    rng = np.random.default_rng(7)
    rets = np.concatenate([rng.normal(-0.0003, 0.001, n - 15), rng.normal(0.0002, 0.0005, 10), [-0.004] * 5])
    return (float(start) * np.cumprod(1 + rets)).tolist()


class TestHappyGoldSessionFilter:
    def test_no_signal_outside_london_ny(self):
        """Frozen: sessions London 08:00-16:00 OR NY 13:00-21:00 UTC only."""
        strat = HappyGoldScalper()
        close = _make_price_series()
        # Asian/closed hours: 05:00 UTC
        sig = strat.generate_signal("XAUUSD", _ohlcv(close), current_time=datetime(2025, 6, 2, 5, 0, tzinfo=UTC))
        assert sig is None

    def test_no_signal_sunday_or_weekend(self):
        strat = HappyGoldScalper()
        close = _make_price_series()
        # Saturday 10:00 UTC (weekend close)
        sig = strat.generate_signal("XAUUSD", _ohlcv(close), current_time=datetime(2025, 6, 7, 10, 0, tzinfo=UTC))
        assert sig is None


class TestHappyGoldBreakoutEntry:
    def test_long_breakout_in_uptrend(self):
        strat = HappyGoldScalper()
        close = _make_price_series()
        sig = strat.generate_signal("XAUUSD", _ohlcv(close), current_time=_london_open())
        assert sig is not None
        assert sig.signal_type == SignalType.BUY
        assert sig.entry_price is not None
        assert sig.stop_loss is not None and sig.stop_loss < sig.entry_price
        assert sig.take_profit is not None and sig.take_profit > sig.entry_price

    def test_short_breakout_in_downtrend(self):
        strat = HappyGoldScalper()
        close = _make_downtrend()
        sig = strat.generate_signal("XAUUSD", _ohlcv(close), current_time=_london_open())
        assert sig is not None
        assert sig.signal_type == SignalType.SELL
        assert sig.stop_loss is not None and sig.stop_loss > sig.entry_price
        assert sig.take_profit is not None and sig.take_profit < sig.entry_price

    def test_no_signal_without_breakout(self):
        """Range-bound closes: no breakout -> None."""
        strat = HappyGoldScalper()
        rng = np.random.default_rng(3)
        close = (3300.0 + rng.normal(0, 1.0, 80)).tolist()
        sig = strat.generate_signal("XAUUSD", _ohlcv(close), current_time=_london_open())
        assert sig is None

    def test_no_long_when_below_ema(self):
        """Trend filter: long only if close > EMA(50).

        Deterministic shape: 40 bars flat at 3400, 25 bars crash -2.5%/bar,
        15 bars flat at crash level, then a +3% bounce that breaks the
        prior-20-bar high but stays BELOW the lagging EMA(50) → long blocked.
        """
        strat = HappyGoldScalper()
        flat = [3400.0] * 40
        crash = [flat[-1] * 0.975 ** (i + 1) for i in range(25)]
        flat2 = [crash[-1]] * 20  # prior-20 window = all flat bars
        bounce = [flat2[-1] * 1.03]
        close = flat + crash + flat2 + bounce
        # Sanity: EMA(50) above current close AND close above prior-20 high
        assert close[-1] > max(close[-21:-1])
        sig = strat.generate_signal("XAUUSD", _ohlcv(close), current_time=_london_open())
        assert sig is None


class TestHappyGoldRiskControls:
    def test_sl_tp_scale_with_atr(self):
        strat = HappyGoldScalper()
        close = _make_price_series()
        sig = strat.generate_signal("XAUUSD", _ohlcv(close), current_time=_london_open())
        assert sig is not None
        entry = float(sig.entry_price)
        sl = float(sig.stop_loss)
        tp = float(sig.take_profit)
        # RR ≈ 2.0 / 1.5 = 1.333
        rr = (tp - entry) / (entry - sl)
        assert rr == pytest.approx(2.0 / 1.5, rel=0.02)

    def test_sl_always_present(self):
        """Engine rejects signals without SL — never emit one."""
        strat = HappyGoldScalper()
        close = _make_price_series()
        sig = strat.generate_signal("XAUUSD", _ohlcv(close), current_time=_london_open())
        if sig is not None:
            assert sig.stop_loss is not None and sig.stop_loss > 0

    def test_insufficient_data_returns_none(self):
        strat = HappyGoldScalper()
        close = [3300.0 + i * 0.1 for i in range(10)]  # < warmup
        sig = strat.generate_signal("XAUUSD", _ohlcv(close), current_time=_london_open())
        assert sig is None
