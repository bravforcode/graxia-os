"""
Phase 3B backtest metrics — real-calculation regression tests.

Run:
  python -m pytest graxia/packages/quant_os/tests/chaos/test_backtest_metrics_fixed.py -v
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest

from graxia.packages.quant_os.backtest.phase_3b_metrics import (
    Phase3BMetrics,
    _max_drawdown,
    _sharpe_ratio,
    calculate_phase_3b_metrics,
)


class TestMaxDrawdown:
    def test_empty_curve_returns_zero(self):
        assert _max_drawdown([]) == 0.0

    def test_single_point_returns_zero(self):
        assert _max_drawdown([{"equity": 100}]) == 0.0

    def test_no_drawdown(self):
        curve = [{"equity": float(100 + i)} for i in range(5)]
        assert _max_drawdown(curve, initial_capital=100.0) == 0.0

    def test_peak_to_trough_absolute_decline(self):
        curve = [{"equity": v} for v in [100.0, 110.0, 105.0, 90.0, 95.0, 120.0]]
        assert _max_drawdown(curve, initial_capital=100.0) == 20.0

    def test_initial_capital_used_as_starting_peak(self):
        # First equity point is already below the starting capital.
        curve = [{"equity": 90.0}]
        assert _max_drawdown(curve, initial_capital=100.0) == 10.0

    def test_falls_back_to_first_equity_if_no_capital(self):
        curve = [{"equity": v} for v in [100.0, 80.0, 90.0]]
        assert _max_drawdown(curve) == 20.0


class TestSharpeRatio:
    def test_empty_or_single_curve_returns_zero(self):
        assert _sharpe_ratio([]) == 0.0
        assert _sharpe_ratio([{"equity": 100.0}]) == 0.0

    def test_constant_equity_returns_zero(self):
        curve = [
            {"equity": 100.0, "timestamp": datetime(2025, 1, 1) + timedelta(days=i)}
            for i in range(5)
        ]
        assert _sharpe_ratio(curve) == 0.0

    def test_positive_trend_yields_positive_sharpe(self):
        curve = [
            {"equity": float(100 + i), "timestamp": datetime(2025, 1, 1) + timedelta(days=i)}
            for i in range(30)
        ]
        assert _sharpe_ratio(curve) > 0.0

    def test_daily_periods_annualization(self):
        curve = [
            {"equity": 100.0, "timestamp": datetime(2025, 1, 1)},
            {"equity": 101.0, "timestamp": datetime(2025, 1, 2)},
            {"equity": 102.0, "timestamp": datetime(2025, 1, 3)},
        ]
        sr = _sharpe_ratio(curve)
        r1 = (101.0 - 100.0) / 100.0
        r2 = (102.0 - 101.0) / 101.0
        mean = (r1 + r2) / 2
        var = ((r1 - mean) ** 2 + (r2 - mean) ** 2) / 2
        std = math.sqrt(var)
        expected = (mean / std) * math.sqrt(365)
        assert sr == pytest.approx(expected, rel=1e-9)

    def test_no_timestamps_defaults_to_252(self):
        curve = [{"equity": 100.0}, {"equity": 101.0}, {"equity": 102.0}]
        sr = _sharpe_ratio(curve)
        assert sr > 0.0


class TestCalculatePhase3BMetrics:
    def test_calculates_drawdown_and_sharpe_from_result(self):
        result = {
            "config": {"initial_capital": 10000.0},
            "trades": [
                {
                    "pnl": 100.0,
                    "entry_spread_cost": 1.0,
                    "entry_slippage_cost": 0.5,
                    "exit_slippage_cost": 0.5,
                    "fees": 2.0,
                },
                {
                    "pnl": -50.0,
                    "entry_spread_cost": 1.0,
                    "entry_slippage_cost": 0.5,
                    "exit_slippage_cost": 0.5,
                    "fees": 2.0,
                },
            ],
            "equity_curve": [
                {"equity": 10000.0, "timestamp": datetime(2025, 1, 1)},
                {"equity": 10100.0, "timestamp": datetime(2025, 1, 2)},
                {"equity": 10050.0, "timestamp": datetime(2025, 1, 3)},
            ],
        }
        m = calculate_phase_3b_metrics(result, "R0_TEST")

        assert isinstance(m, Phase3BMetrics)
        assert m.scenario == "R0_TEST"
        assert m.max_drawdown == 50.0
        assert m.sharpe_ratio > 0.0
        assert m.trade_count == 2
        assert m.total_pnl == 50.0

    def test_empty_result_returns_zero_metrics(self):
        m = calculate_phase_3b_metrics({}, "EMPTY")
        assert m.max_drawdown == 0.0
        assert m.sharpe_ratio == 0.0
        assert m.trade_count == 0
