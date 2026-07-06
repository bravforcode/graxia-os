"""
Regression test for BUG-003 (P0): backtest/engine.py fed the regime detector a
"return" computed as (bar_close - equity_at_prev_bar) / equity_at_prev_bar —
mixing a price with the strategy's own equity. That is not a market return; it
is contaminated by the strategy's own P&L, so the regime detector was learning
"what regime looks like when my strategy is currently winning or losing"
rather than the market's actual volatility/trend state.

The fix feeds the detector the genuine close-to-close market return:
(close[i] - close[i-1]) / close[i-1].

This test uses <200 bars deliberately: validation/regime_detector.py's
_detect_vol_regime/_detect_corr_regime/_annualized_vol index a
`collections.deque` with slice notation, which raises TypeError once enough
samples accumulate (deques don't support slicing) -- a separate, pre-existing
bug unrelated to BUG-003. Staying under vol_lookback_long (200) bars avoids
tripping it while still exercising RegimeDetector.update() every bar.
"""

from datetime import datetime, timedelta
from typing import Any

import pytest
from quant_os.backtest.engine import BacktestConfig, BacktestEngine
from quant_os.strategies.base import Strategy, StrategyConfig


def _make_timestamps(n: int, start: datetime | None = None) -> list[datetime]:
    if start is None:
        start = datetime(2024, 1, 1)
    return [start + timedelta(hours=i) for i in range(n)]


def _make_trending_ohlcv(n: int = 60, base_price: float = 1800.0) -> dict[str, list]:
    """Deterministic, monotonically increasing close series (no randomness
    needed -- we only need a close series whose bar-to-bar return is easy to
    hand-compute and is clearly NOT equal to any equity-derived value)."""
    close = [round(base_price + i * 1.5, 2) for i in range(n)]
    high = [round(c + 0.5, 2) for c in close]
    low = [round(c - 0.5, 2) for c in close]
    open_price = [round(c - 0.25, 2) for c in close]
    volume = [1000.0] * n
    return {"open": open_price, "high": high, "low": low, "close": close, "volume": volume}


class _NoTradeStrategy(Strategy):
    """Never emits a signal, so equity never moves away from initial_capital.

    This isolates the bug: under the old (buggy) code, bar_return was derived
    from equity, which stays flat here, so every bar would compute the SAME
    equity-vs-price mismatch. Under the fix, bar_return must track the actual
    (varying) close-to-close market return regardless of equity.
    """

    def __init__(self):
        super().__init__(StrategyConfig(name="NoTrade"))

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict[str, Any] | None = None,
        regime: Any = None,
        **kwargs,
    ):
        return None

    def required_features(self) -> list[str]:
        return []


def test_regime_detector_receives_market_return_not_equity_return(monkeypatch):
    """BUG-003 regression: RegimeDetector.update() must be called with the
    genuine market close-to-close return, not a value derived from the
    strategy's own equity curve."""
    from quant_os.validation.regime_detector import RegimeDetector

    calls: list[tuple[int, float]] = []
    original_update = RegimeDetector.update

    def spy_update(self, bar_return, bar_index=0):
        calls.append((bar_index, bar_return))
        return original_update(self, bar_return, bar_index)

    monkeypatch.setattr(RegimeDetector, "update", spy_update)

    data = _make_trending_ohlcv(60)
    ts = _make_timestamps(60)

    cfg = BacktestConfig(strict_mtf=False)
    engine = BacktestEngine(config=cfg)
    engine.set_strategy(_NoTradeStrategy())
    engine.load_data(data, ts)
    engine.run()

    assert calls, "RegimeDetector.update() was never called"

    close = data["close"]
    for bar_index, bar_return in calls:
        expected = (close[bar_index] - close[bar_index - 1]) / close[bar_index - 1]
        assert bar_return == pytest.approx(expected), (
            f"bar {bar_index}: regime detector got {bar_return}, "
            f"expected market return {expected} "
            f"(equity is flat in this test, so any value derived from equity "
            f"would not match a real, varying price return)"
        )

    # Sanity: with a flat/near-flat equity curve, the pre-fix formula
    # (close - equity) / equity would have produced a huge, ~constant value
    # (close ~1800+ vs equity ~10000) every bar -- nothing like the small,
    # varying true market returns asserted above.
    equity_like_values = {round(v, 6) for _, v in calls}
    assert len(equity_like_values) > 1, "expected varying per-bar market returns, not a constant"
