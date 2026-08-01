"""Sanity test — StrategyValidator on a known-edge synthetic strategy.

Verifies the validation framework correctly detects a real edge:
- Synthetic data with positive drift (clear uptrend)
- Simple trend-following strategy with asymmetric risk-reward
- Strategy should produce positive trade-level Sharpe
- Validator should pass >= 2 of 5 gates (WF, DSR, PBO, Bootstrap, Cost)

This is NOT a statistical test -- it's a smoke test that the validator
wiring works end-to-end and doesn't silently produce wrong results.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
from quant_os.core.enums import SignalType
from quant_os.strategies.base import Signal, Strategy, StrategyConfig
from quant_os.validation.strategy_validator import (
    StrategyValidator,
    ValidationConfig,
    _compute_trade_returns_sharpe,
)

# -- Synthetic Data --------------------------------------------------------


def _make_trending_ohlcv(
    n_bars: int = 5000,
    base_price: float = 2000.0,
    daily_drift: float = 0.0005,  # +0.05%/day = ~13% annualized
    daily_vol: float = 0.01,  # 1% daily vol
    seed: int = 42,
) -> dict[str, list]:
    """Generate OHLCV with a clear uptrend (positive drift).

    The drift is strong enough that a trend-following strategy should
    capture it reliably, producing a positive Sharpe.
    """
    rng = np.random.RandomState(seed)
    closes = [base_price]
    for _ in range(n_bars - 1):
        ret = daily_drift + daily_vol * rng.randn()
        closes.append(closes[-1] * (1 + ret))

    # Build OHLCV around closes
    opens, highs, lows, volumes = [], [], [], []
    for i, c in enumerate(closes):
        intra_vol = daily_vol * 0.5
        o = c * (1 + rng.randn() * intra_vol * 0.3)
        h = max(o, c) * (1 + abs(rng.randn()) * intra_vol * 0.5)
        l = min(o, c) * (1 - abs(rng.randn()) * intra_vol * 0.5)
        opens.append(round(o, 2))
        highs.append(round(h, 2))
        lows.append(round(l, 2))
        volumes.append(rng.randint(500, 5000))

    return {
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    }


def _make_timestamps(n: int, freq_days: int = 1) -> list[datetime]:
    start = datetime(2010, 1, 4, tzinfo=UTC)
    return [start + timedelta(days=i * freq_days) for i in range(n)]


# -- Synthetic Strategy ----------------------------------------------------


class TrendEdgeStrategy(Strategy):
    """Simple trend-following with asymmetric risk-reward.

    - BUY when close > 20-SMA (uptrend)
    - SELL when close < 20-SMA (downtrend)
    - SL = 1x ATR, TP = 2x ATR (2:1 R:R)
    - This produces a genuine edge on trending data because the trend
      persists long enough to hit TP more often than SL.
    """

    def __init__(self, sma_period: int = 20, atr_period: int = 14, risk_reward: float = 2.0, **kwargs):
        config = StrategyConfig(
            name="TrendEdge",
            version="1.0",
            symbols=["XAUUSD"],
            timeframes=["D1"],
            risk_per_trade_pct=1.0,
            max_trades_per_day=1,
            min_confidence=0.0,
            min_risk_reward=0.0,
            require_trend_confirm=False,
        )
        super().__init__(config)
        self.sma_period = sma_period
        self.atr_period = atr_period
        self.risk_reward = risk_reward

    def required_features(self) -> list[str]:
        return []

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict | None = None,
        regime=None,
        **kwargs,
    ) -> Signal | None:
        close = ohlcv_data.get("close", [])
        high = ohlcv_data.get("high", close)
        low = ohlcv_data.get("low", close)

        n = len(close)
        if n < max(self.sma_period, self.atr_period) + 5:
            return None

        # Compute SMA
        sma = sum(close[-self.sma_period :]) / self.sma_period

        # Compute ATR
        trs = []
        for i in range(-self.atr_period, 0):
            tr = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1]),
            )
            trs.append(tr)
        atr = sum(trs) / len(trs)

        if atr <= 0:
            return None

        current_price = close[-1]
        sl_dist = atr
        tp_dist = atr * self.risk_reward

        if current_price > sma:
            # Uptrend: BUY
            entry = Decimal(str(round(current_price, 2)))
            sl = Decimal(str(round(current_price - sl_dist, 2)))
            tp = Decimal(str(round(current_price + tp_dist, 2)))
            sig_type = SignalType.BUY
        elif current_price < sma:
            # Downtrend: SELL
            entry = Decimal(str(round(current_price, 2)))
            sl = Decimal(str(round(current_price + sl_dist, 2)))
            tp = Decimal(str(round(current_price - tp_dist, 2)))
            sig_type = SignalType.SELL
        else:
            return None

        # Only signal every 5 bars to avoid overtrading
        if n % 5 != 0:
            return None

        return Signal.create(
            strategy_id=self.id,
            symbol=symbol,
            signal_type=sig_type,
            confidence=0.8,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
        )


class RandomStrategy(Strategy):
    """Truly random strategy with ZERO expected edge.

    Key design: uses SYMMETRIC SL/TP (equal distance), so even if it
    happens to win slightly more, the expectation is zero. Random
    entries with 1:1 R:R have zero expectancy by construction.
    """

    def __init__(self, **kwargs):
        super().__init__(
            StrategyConfig(
                name="Random",
                version="1.0",
                symbols=["XAUUSD"],
                timeframes=["D1"],
                min_confidence=0.0,
                min_risk_reward=0.0,
                require_trend_confirm=False,
            )
        )
        self._rng = random.Random(42)

    def required_features(self):
        return []

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        close = ohlcv_data.get("close", [])
        if len(close) < 30 or len(close) % 10 != 0:
            return None

        price = close[-1]
        if price <= 0:
            return None

        # Fixed SL/TP distance: 1% of price (symmetric = zero expectancy)
        sl_dist = price * 0.01
        tp_dist = price * 0.01  # Same distance = 1:1 R:R

        if self._rng.random() < 0.5:
            return Signal.create(
                strategy_id=self.id,
                symbol=symbol,
                signal_type=SignalType.BUY,
                confidence=0.5,
                entry_price=Decimal(str(round(price, 2))),
                stop_loss=Decimal(str(round(price - sl_dist, 2))),
                take_profit=Decimal(str(round(price + tp_dist, 2))),
            )
        return None


# -- Tests -----------------------------------------------------------------


class TestValidatorSanity:
    """Smoke tests for StrategyValidator on known-edge synthetic data."""

    def test_trend_strategy_detects_edge(self):
        """The trend-following strategy on trending data should pass >= 2 gates."""
        data = _make_trending_ohlcv(n_bars=5000, daily_drift=0.0008, seed=42)
        timestamps = _make_timestamps(len(data["close"]))

        # Strategy factory: returns a new TrendEdgeStrategy each call
        def factory(sma_period=20, atr_period=14, risk_reward=2.0, **kwargs):
            return TrendEdgeStrategy(
                sma_period=sma_period,
                atr_period=atr_period,
                risk_reward=risk_reward,
            )

        validator = StrategyValidator(
            strategy_factory=factory,
            param_grid=[
                {"sma_period": 15, "atr_period": 14, "risk_reward": 2.0},
                {"sma_period": 20, "atr_period": 14, "risk_reward": 2.0},
                {"sma_period": 25, "atr_period": 14, "risk_reward": 2.0},
                {"sma_period": 20, "atr_period": 10, "risk_reward": 1.5},
                {"sma_period": 20, "atr_period": 10, "risk_reward": 2.5},
            ],
            pbo_configs=[
                {"sma_period": 15, "atr_period": 14, "risk_reward": 2.0, "name": "fast"},
                {"sma_period": 20, "atr_period": 14, "risk_reward": 2.0, "name": "base"},
                {"sma_period": 25, "atr_period": 14, "risk_reward": 2.0, "name": "slow"},
            ],
            default_params={"sma_period": 20, "atr_period": 14, "risk_reward": 2.0},
            strategy_name="TrendEdge Sanity Test",
            config=ValidationConfig(
                strategy_symbol="XAUUSD",
                strategy_timeframe="D1",
                n_wf_folds=3,
                n_bootstrap_resamples=200,
            ),
        )

        result = validator.run(data=data, timestamps=timestamps)
        report = validator.generate_report(result)

        # --- Core assertions ---

        # 1. Should produce trades (not zero)
        assert result.baseline_trades > 10, f"Expected >10 trades, got {result.baseline_trades}"

        # 2. Trade-level Sharpe should be positive (edge exists)
        assert (
            result.baseline_sharpe_trade > 0
        ), f"Expected positive trade-level Sharpe, got {result.baseline_sharpe_trade}"

        # 3. At least 2 of 5 gates should pass
        assert result.gates_passed >= 2, (
            f"Expected >=2 gates passed, got {result.gates_passed}/5. "
            f"WF={result.wf_pass} DSR={result.dsr_pass} PBO={result.pbo_pass} "
            f"Boot={result.bootstrap_pass} Cost={result.cost_pass}"
        )

        # 4. Verdict should indicate some edge (not "NO EDGE")
        assert result.verdict != "NO EDGE", f"Expected edge detection, got verdict='{result.verdict}'"

        # 5. Report should contain key sections
        assert "EDGE VERIFICATION REPORT" in report
        assert "BASELINE METRICS" in report
        assert "WALK-FORWARD ANALYSIS" in report
        assert "DEFLATED SHARPE RATIO" in report
        assert "Sharpe Ratio:" in report

        # 6. DSR observations should match baseline trades
        assert result.dsr_n_observations == result.baseline_trades

        print("\n=== SANITY TEST PASSED ===")
        print(f"Trades: {result.baseline_trades}")
        print(f"Trade Sharpe: {result.baseline_sharpe_trade:.4f}")
        print(f"Bar Sharpe:   {result.baseline_sharpe_bar:.4f}")
        print(f"Gates: {result.gates_passed}/5 -> {result.verdict}")
        print(f"  WF={result.wf_pass} DSR={result.dsr_pass} PBO={result.pbo_pass}")
        print(f"  Bootstrap={result.bootstrap_pass} Cost={result.cost_pass}")

    def test_no_edge_strategy_rejects(self):
        """A random strategy on random data should not show strong edge.

        Uses symmetric SL/TP (1:1 R:R) so the strategy has zero
        expected edge by construction. We relax the assertion to
        <= 2 gates because variance can occasionally push a zero-edge
        strategy past 1 gate.
        """
        # Pure random walk (zero drift)
        data = _make_trending_ohlcv(n_bars=3000, daily_drift=0.0, daily_vol=0.01, seed=99)
        timestamps = _make_timestamps(len(data["close"]))

        def factory(**kwargs):
            return RandomStrategy()

        validator = StrategyValidator(
            strategy_factory=factory,
            param_grid=[{}],
            pbo_configs=[
                {"name": "a"},
                {"name": "b"},
                {"name": "c"},
            ],
            default_params={},
            strategy_name="Random Sanity Test",
            config=ValidationConfig(
                strategy_symbol="XAUUSD",
                strategy_timeframe="D1",
                n_wf_folds=3,
                n_bootstrap_resamples=100,
            ),
        )

        result = validator.run(data=data, timestamps=timestamps)

        # Random strategy should have <= 2 gates pass (0 expected, <=2 tolerated)
        assert result.gates_passed <= 2, f"Random strategy passed {result.gates_passed}/5 gates -- suspicious"
        print("\n=== NO-EDGE TEST PASSED ===")
        print(f"Trades: {result.baseline_trades}, Sharpe: {result.baseline_sharpe_trade:.4f}")
        print(f"Gates: {result.gates_passed}/5 -> {result.verdict}")

    def test_compute_trade_returns_sharpe_basic(self):
        """Verify _compute_trade_returns_sharpe helper."""
        # All positive returns -> positive Sharpe
        trades = [{"return_pct": 5.0}, {"return_pct": 3.0}, {"return_pct": 7.0}, {"return_pct": 2.0}]
        sharpe = _compute_trade_returns_sharpe(trades, annualization_factor=252)
        assert sharpe > 0

        # All negative returns -> negative Sharpe
        trades_neg = [{"return_pct": -5.0}, {"return_pct": -3.0}, {"return_pct": -7.0}]
        sharpe_neg = _compute_trade_returns_sharpe(trades_neg, annualization_factor=252)
        assert sharpe_neg < 0

        # Empty trades -> 0
        assert _compute_trade_returns_sharpe([], annualization_factor=252) == 0.0

        # Single trade -> 0 (need >= 2 for std)
        assert _compute_trade_returns_sharpe([{"return_pct": 5.0}], annualization_factor=252) == 0.0
