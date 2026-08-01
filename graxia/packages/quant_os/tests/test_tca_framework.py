"""Tests for execution/tca_framework.py — backtest-to-live gap measurement."""

from __future__ import annotations

import numpy as np

from graxia.packages.quant_os.execution.tca_framework import (
    BacktestToLiveGap,
    benchmark_order,
    calculate_twap,
    calculate_vwap,
)


class TestBacktestToLiveGap:
    """Backtest-to-live gap measurement tests."""

    def _make_trade(self, entry: float, exit_: float, slip: float = 0.5, fill: float = 1.0) -> dict:
        return {
            "entry_price": entry,
            "exit_price": exit_,
            "slippage_bps": slip,
            "fill_ratio": fill,
            "symbol": "XAUUSD",
            "side": "BUY",
        }

    def test_similar_backtest_and_live_produces_good_verdict(self):
        """Similar backtest and live → EXCELLENT."""
        bt = [self._make_trade(100, 101, 0.5) for _ in range(20)]
        live = [self._make_trade(100, 100.8, 1.0) for _ in range(20)]

        gap = BacktestToLiveGap()
        report = gap.measure(bt, live, strategy_id="test")

        assert report.gap is not None
        assert report.verdict == "EXCELLENT"
        assert report.passed

    def test_bad_live_performance_produces_critical(self):
        """Live performs much worse than backtest → CRITICAL."""
        np.random.seed(42)
        bt = []
        for i in range(20):
            entry = 100 + i * 0.1
            exit_ = entry + np.random.uniform(1, 3)  # Profitable with variance
            bt.append(self._make_trade(entry, exit_, 0.5))
        live = []
        for i in range(20):
            entry = 100 + i * 0.1
            exit_ = entry - np.random.uniform(2, 5)  # Losing
            live.append(self._make_trade(entry, exit_, 8.0, 0.7))

        gap = BacktestToLiveGap()
        report = gap.measure(bt, live, strategy_id="test")

        assert report.gap is not None
        assert report.verdict == "CRITICAL"
        # Sharpe degradation should be high
        assert report.gap.sharpe_degradation_pct > 25

    def test_insufficient_trades(self):
        """Fewer than 5 trades → INSUFFICIENT_DATA."""
        bt = [self._make_trade(100, 101, 0.5) for _ in range(2)]
        live = [self._make_trade(100, 100.8, 1.0) for _ in range(2)]

        gap = BacktestToLiveGap()
        report = gap.measure(bt, live, strategy_id="test")

        assert report.verdict == "INSUFFICIENT_DATA"

    def test_empty_trades(self):
        """Empty trade lists → INSUFFICIENT_DATA."""
        gap = BacktestToLiveGap()
        report = gap.measure([], [], strategy_id="test")
        assert report.verdict == "INSUFFICIENT_DATA"

    def test_sharpe_calculation(self):
        """Sharpe ratio computed from returns."""
        bt = [self._make_trade(100 + i, 101 + i + 0.5, 0.5) for i in range(20)]
        live = [self._make_trade(100 + i, 101 + i + 1.0, 1.0) for i in range(20)]

        gap = BacktestToLiveGap()
        report = gap.measure(bt, live, strategy_id="test")

        assert report.gap is not None
        assert isinstance(report.gap.backtest_sharpe, float)
        assert isinstance(report.gap.live_sharpe, float)

    def test_slippage_gap_metrics(self):
        """Slippage gap correctly computed."""
        bt = [self._make_trade(100, 101, slip) for slip in [0.3, 0.4, 0.5, 0.4, 0.6]]
        live = [self._make_trade(100, 101, slip) for slip in [1.0, 1.2, 1.5, 1.1, 1.3]]

        gap = BacktestToLiveGap()
        report = gap.measure(bt, live, strategy_id="test")

        assert report.gap is not None
        assert report.gap.slippage_multiple > 1.5  # Live slippage should be ~3x backtest

    def test_fill_rate_difference(self):
        """Fill rate gap measured correctly."""
        bt = [self._make_trade(100, 101, 0.5, 1.0) for _ in range(10)]
        live = [self._make_trade(100, 101, 0.5, 0.85) for _ in range(10)]

        gap = BacktestToLiveGap()
        report = gap.measure(bt, live, strategy_id="test")

        assert report.gap is not None
        expected_gap = 0.85 - 1.0
        assert abs(report.gap.fill_rate_gap - expected_gap) < 0.01


class TestVWAPTWAP:
    """VWAP/TWAP benchmark tests."""

    def test_vwap_simple(self):
        """Simple VWAP calculation."""
        prices = [100.0, 101.0, 102.0]
        volumes = [1000, 2000, 3000]
        expected = (100 * 1000 + 101 * 2000 + 102 * 3000) / 6000
        result = calculate_vwap(prices, volumes)
        assert abs(result - expected) < 0.001

    def test_vwap_empty(self):
        """Empty VWAP = 0."""
        assert calculate_vwap([], []) == 0.0

    def test_vwap_zero_volume(self):
        """Zero volume → equal-weighted average."""
        prices = [100.0, 101.0]
        volumes = [0, 0]
        result = calculate_vwap(prices, volumes)
        assert abs(result - 100.5) < 0.001

    def test_twap_simple(self):
        """Simple TWAP calculation."""
        prices = [100.0, 101.0, 102.0]
        times = [0.0, 1.0, 3.0]
        # Weighted by time intervals:
        # (100+101)/2 * 1s + (101+102)/2 * 2s  = 100.5*1 + 101.5*2 = 303.5
        # Total weight = 3
        # TWAP = 303.5 / 3 = 101.167
        result = calculate_twap(prices, times)
        expected = (100.5 * 1 + 101.5 * 2) / 3
        assert abs(result - expected) < 0.001

    def test_twap_empty(self):
        """Empty TWAP = 0."""
        assert calculate_twap([], []) == 0.0

    def test_benchmark_order(self):
        """Full benchmark calculation."""
        result = benchmark_order(
            symbol="XAUUSD",
            side="BUY",
            arrival_price=100.0,
            execution_price=100.5,
            market_prices=[100.0, 100.3, 100.6],
            market_volumes=[1000, 2000, 3000],
            timestamps=[0.0, 1.0, 2.0],
        )
        assert result.symbol == "XAUUSD"
        assert result.arrival_slippage_bps > 0  # Paid more than arrival
        assert result.marketability == "MARKETABLE"

    def test_benchmark_order_with_limit(self):
        """Limit price → LIMITED marketability."""
        result = benchmark_order(
            symbol="EURUSD",
            side="SELL",
            arrival_price=1.0850,
            execution_price=1.0848,
            market_prices=[1.0850, 1.0849, 1.0847],
            market_volumes=[5000, 5000, 5000],
            timestamps=[0.0, 0.5, 1.0],
            limit_price=1.0845,
        )
        assert result.marketability == "LIMITED"
