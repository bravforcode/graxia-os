"""Tests for WallStreet-style Asian-session scalper (trial 1035 pre-registration)."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from graxia.packages.quant_os.core.enums import SignalType
from graxia.packages.quant_os.strategies.asian_scalper import AsianScalper


def _ohlcv(close: list[float], high: list[float] | None = None, low: list[float] | None = None) -> dict:
    n = len(close)
    highs = high if high is not None else [c + 0.0005 for c in close]
    lows = low if low is not None else [c - 0.0005 for c in close]
    return {
        "open": close,
        "high": highs,
        "low": lows,
        "close": close,
        "volume": [0] * n,
    }


def _asian_open() -> datetime:
    return datetime(2025, 6, 2, 3, 0, tzinfo=UTC)  # Asian session


def _range_series(n: int = 80, base: float = 1.0850, half_range: float = 0.0015) -> list[float]:
    """Oscillating series inside a fixed channel."""
    rng = np.random.default_rng(5)
    out = []
    for i in range(n):
        out.append(base + half_range * np.sin(i / 3.0) + rng.normal(0, 0.0002))
    return out


def _oversold_break(series: list[float], drop_pct: float = 0.0025) -> list[float]:
    """Append bars that push close below the channel low (oversold)."""
    out = list(series)
    last = out[-1]
    for _ in range(3):
        last = last * (1 - drop_pct)
        out.append(last)
    return out


def _overbought_break(series: list[float], rise_pct: float = 0.0025) -> list[float]:
    out = list(series)
    last = out[-1]
    for _ in range(3):
        last = last * (1 + rise_pct)
        out.append(last)
    return out


class TestAsianScalperSession:
    def test_no_signal_outside_asian_session(self):
        """Frozen: Asian 00:00-08:00 UTC only."""
        strat = AsianScalper()
        close = _oversold_break(_range_series())
        # London hour 10:00 UTC
        sig = strat.generate_signal("EURUSD", _ohlcv(close), current_time=datetime(2025, 6, 2, 10, 0, tzinfo=UTC))
        assert sig is None

    def test_no_signal_weekend(self):
        strat = AsianScalper()
        close = _oversold_break(_range_series())
        sig = strat.generate_signal("EURUSD", _ohlcv(close), current_time=datetime(2025, 6, 7, 3, 0, tzinfo=UTC))
        assert sig is None


class TestAsianScalperEntries:
    def test_oversold_fade_long(self):
        strat = AsianScalper()
        close = _oversold_break(_range_series())
        sig = strat.generate_signal("EURUSD", _ohlcv(close), current_time=_asian_open())
        assert sig is not None
        assert sig.signal_type == SignalType.BUY
        assert sig.stop_loss is not None and sig.stop_loss < sig.entry_price
        assert sig.take_profit is not None and sig.take_profit > sig.entry_price

    def test_overbought_fade_short(self):
        strat = AsianScalper()
        close = _overbought_break(_range_series())
        sig = strat.generate_signal("EURUSD", _ohlcv(close), current_time=_asian_open())
        assert sig is not None
        assert sig.signal_type == SignalType.SELL
        assert sig.stop_loss is not None and sig.stop_loss > sig.entry_price
        assert sig.take_profit is not None and sig.take_profit < sig.entry_price

    def test_no_signal_within_range(self):
        """Close inside channel, RSI mid — no fade."""
        strat = AsianScalper()
        close = _range_series()
        sig = strat.generate_signal("EURUSD", _ohlcv(close), current_time=_asian_open())
        assert sig is None

    def test_no_signal_oversold_without_rsi_extreme(self):
        """Below channel but RSI(14) not < 30 — no long."""
        strat = AsianScalper()
        close = _range_series(n=90)  # longer series: RSI damps
        # Push gently below the low over many bars so RSI stays mid
        for _ in range(6):
            close.append(close[-1] * (1 - 0.00003))
        sig = strat.generate_signal("EURUSD", _ohlcv(close), current_time=_asian_open())
        assert sig is None


class TestAsianScalperRisk:
    def test_sl_tp_scale_with_atr(self):
        strat = AsianScalper()
        close = _oversold_break(_range_series())
        sig = strat.generate_signal("EURUSD", _ohlcv(close), current_time=_asian_open())
        assert sig is not None
        entry = float(sig.entry_price)
        sl = float(sig.stop_loss)
        tp = float(sig.take_profit)
        rr = (tp - entry) / (entry - sl)
        assert rr == pytest.approx(1.2, rel=0.05)

    def test_sl_always_present(self):
        strat = AsianScalper()
        close = _oversold_break(_range_series())
        sig = strat.generate_signal("EURUSD", _ohlcv(close), current_time=_asian_open())
        if sig is not None:
            assert sig.stop_loss is not None and sig.stop_loss > 0

    def test_insufficient_data_returns_none(self):
        strat = AsianScalper()
        close = [1.08 + i * 0.0001 for i in range(10)]
        sig = strat.generate_signal("EURUSD", _ohlcv(close), current_time=_asian_open())
        assert sig is None
