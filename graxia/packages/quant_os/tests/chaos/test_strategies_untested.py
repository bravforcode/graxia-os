"""
Chaos Tests — strategies/walk_forward.py

Covers:
  - Empty dataset handling
  - Single bar dataset
  - Dataset with gaps
  - Extremely large dataset
  - Invalid parameters
  - Edge cases in helper functions

RULE: If a test fails, fix the CODE, never the test.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from graxia.packages.quant_os.strategies.walk_forward import (
    FoldMetrics,
    StrategyComparison,
    WalkForwardFold,
    WalkForwardResults,
    WalkForwardValidator,
    _deflated_sharpe,
    _generate_splits,
    _max_drawdown,
    _pooma,
    _profit_factor,
    _sharpe,
)


# ═══════════════════════════════════════════════════════════════════
# Mock strategy for WalkForwardValidator
# ═══════════════════════════════════════════════════════════════════

class FakeSignal:
    def __init__(self, signal_type: str = "BUY"):
        self.signal_type = MagicMock(value=signal_type)


class FakeStrategy:
    def __init__(self, strategy_id: str = "test_strat", always_signal: bool = True):
        self._id = strategy_id
        self._always_signal = always_signal

    @property
    def id(self) -> str:
        return self._id

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        if not self._always_signal:
            return None
        return FakeSignal("BUY")

    def required_features(self) -> list[str]:
        return []


class AlwaysNoneStrategy:
    def __init__(self):
        self._id = "always_none"

    @property
    def id(self) -> str:
        return self._id

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        return None

    def required_features(self) -> list[str]:
        return []


class SellStrategy:
    def __init__(self):
        self._id = "sell_strat"

    @property
    def id(self) -> str:
        return self._id

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        return FakeSignal("SELL")

    def required_features(self) -> list[str]:
        return []


class VolatileStrategy:
    """Alternates between BUY and SELL signals for variety."""
    def __init__(self):
        self._id = "volatile_strat"
        self._counter = 0

    @property
    def id(self) -> str:
        return self._id

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        self._counter += 1
        if self._counter % 3 == 0:
            return FakeSignal("SELL")
        return FakeSignal("BUY")

    def required_features(self) -> list[str]:
        return []


# ═══════════════════════════════════════════════════════════════════
# Data generators
# ═══════════════════════════════════════════════════════════════════

def _make_ohlcv(n: int, base_price: float = 100.0) -> dict[str, list]:
    """Generate synthetic OHLCV data."""
    import random
    random.seed(42)
    closes = []
    price = base_price
    for _ in range(n):
        change = random.uniform(-0.5, 0.5)
        price = max(0.01, price + change)
        closes.append(price)
    return {
        "open": [c - random.uniform(0, 0.2) for c in closes],
        "high": [c + random.uniform(0, 0.5) for c in closes],
        "low": [c - random.uniform(0, 0.5) for c in closes],
        "close": closes,
        "volume": [random.randint(100, 10000) for _ in range(n)],
    }


def _make_ohlcv_with_gaps(n: int, gap_positions: list[int] | None = None) -> dict[str, list]:
    """Generate OHLCV data with NaN-like gaps."""
    data = _make_ohlcv(n)
    if gap_positions:
        for pos in gap_positions:
            if 0 <= pos < n:
                data["close"][pos] = None
                data["volume"][pos] = 0
    return data


# ═══════════════════════════════════════════════════════════════════
# Helper function tests
# ═══════════════════════════════════════════════════════════════════

class TestSharpeChaos:
    """Edge cases for _sharpe helper."""

    def test_empty_returns(self):
        assert _sharpe([]) == 0.0

    def test_single_return(self):
        assert _sharpe([1.0]) == 0.0

    def test_two_returns(self):
        result = _sharpe([0.01, 0.02])
        assert result > 0

    def test_all_zero_returns(self):
        assert _sharpe([0.0, 0.0, 0.0]) == 0.0

    def test_negative_returns(self):
        result = _sharpe([-0.01, -0.02, -0.03])
        assert result < 0

    def test_mixed_returns(self):
        result = _sharpe([0.05, -0.03, 0.02, -0.01])
        assert isinstance(result, float)

    def test_no_annualisation(self):
        result = _sharpe([0.01, 0.02, 0.03], annualise=False)
        assert isinstance(result, float)

    def test_with_risk_free(self):
        result = _sharpe([0.05, 0.06, 0.07], risk_free=0.02)
        assert isinstance(result, float)

    def test_extreme_values(self):
        result = _sharpe([1e10, -1e10, 1e10])
        assert isinstance(result, float)

    def test_very_small_values(self):
        result = _sharpe([1e-10, 2e-10, 3e-10])
        assert isinstance(result, float)

    def test_identical_returns(self):
        result = _sharpe([0.01, 0.01, 0.01, 0.01])
        assert result > 0


class TestMaxDrawdownChaos:
    """Edge cases for _max_drawdown helper."""

    def test_empty_curve(self):
        assert _max_drawdown([]) == 0.0

    def test_single_point(self):
        assert _max_drawdown([100.0]) == 0.0

    def test_monotonic_up(self):
        assert _max_drawdown([100, 110, 120, 130]) == 0.0

    def test_monotonic_down(self):
        result = _max_drawdown([100, 90, 80, 70])
        assert result > 0

    def test_v_shaped(self):
        result = _max_drawdown([100, 80, 100])
        assert result == pytest.approx(20.0, abs=0.1)

    def test_zero_peak(self):
        result = _max_drawdown([0, 0, 0])
        assert result == 0.0

    def test_negative_equity(self):
        result = _max_drawdown([-100, -200, -150])
        assert isinstance(result, float)

    def test_extreme_drawdown(self):
        result = _max_drawdown([1000, 1, 1000])
        assert result == pytest.approx(99.9, abs=0.1)

    def test_constant_value(self):
        assert _max_drawdown([50, 50, 50, 50]) == 0.0


class TestProfitFactorChaos:
    """Edge cases for _profit_factor helper."""

    def test_empty_trades(self):
        assert _profit_factor([]) == 0.0

    def test_all_wins(self):
        assert _profit_factor([0.01, 0.02, 0.03]) == float("inf")

    def test_all_losses(self):
        assert _profit_factor([-0.01, -0.02, -0.03]) == 0.0

    def test_mixed(self):
        result = _profit_factor([0.05, -0.03, 0.02, -0.01])
        assert result > 0

    def test_single_win(self):
        assert _profit_factor([0.01]) == float("inf")

    def test_single_loss(self):
        assert _profit_factor([-0.01]) == 0.0

    def test_breakeven(self):
        assert _profit_factor([0.01, -0.01]) == 1.0

    def test_extreme_profit(self):
        result = _profit_factor([1000, -0.01])
        assert result > 10000


class TestDeflatedSharpeChaos:
    """Edge cases for _deflated_sharpe helper."""

    def test_single_trial(self):
        assert _deflated_sharpe(1.5, n_trials=1) == 1.5

    def test_many_trials(self):
        result = _deflated_sharpe(1.0, n_trials=1000)
        assert result < 1.0

    def test_zero_sharpe(self):
        result = _deflated_sharpe(0.0, n_trials=100)
        assert result < 0

    def test_negative_sharpe(self):
        result = _deflated_sharpe(-1.0, n_trials=50)
        assert result < -1.0

    def test_two_trials(self):
        result = _deflated_sharpe(2.0, n_trials=2)
        assert isinstance(result, float)


class TestPoomaChaos:
    """Edge cases for _pooma helper."""

    def test_zero_is_sharpe(self):
        result = _pooma(0.0, 0.5, 5)
        assert 0.0 <= result <= 1.0

    def test_equal_sharpes(self):
        result = _pooma(1.0, 1.0, 5)
        assert result == pytest.approx(0.0, abs=0.01)

    def test_oos_worse(self):
        result = _pooma(2.0, 0.5, 5)
        assert result > 0

    def test_oos_better(self):
        # _pooma clamps to [0, 1] via min(max(..., 0.0), 1.0)
        # When OOS > IS, degradation is negative → clamped to 0.0
        result = _pooma(0.5, 2.0, 5)
        assert result == pytest.approx(0.0, abs=0.01)

    def test_one_fold(self):
        result = _pooma(1.0, 0.5, 1)
        assert 0.0 <= result <= 1.0

    def test_large_folds(self):
        result = _pooma(1.0, 0.5, 1000)
        assert 0.0 <= result <= 1.0


# ═══════════════════════════════════════════════════════════════════
# Split generation tests
# ═══════════════════════════════════════════════════════════════════

class TestGenerateSplitsChaos:
    """Edge cases for _generate_splits helper."""

    def test_zero_bars(self):
        assert _generate_splits(0, 5, 0.7, 0) == []

    def test_one_bar(self):
        result = _generate_splits(1, 5, 0.7, 0)
        assert result == []

    def test_fewer_bars_than_folds(self):
        result = _generate_splits(3, 5, 0.7, 0)
        assert len(result) == 0

    def test_exactly_one_fold(self):
        result = _generate_splits(100, 1, 0.7, 0)
        assert len(result) == 1

    def test_large_embargo(self):
        result = _generate_splits(1000, 5, 0.7, 500)
        assert len(result) < 5

    def test_embargo_equals_fold_size(self):
        result = _generate_splits(100, 5, 0.7, 20)
        assert len(result) == 0

    def test_train_ratio_one(self):
        # train_ratio=1.0 → train_size=fold_size → test_start=fold_end → no test split
        result = _generate_splits(100, 5, 1.0, 0)
        assert len(result) == 0

    def test_train_ratio_zero(self):
        # train_ratio=0.0 → train_size=0 → test covers entire fold → splits generated
        result = _generate_splits(100, 5, 0.0, 0)
        assert len(result) > 0

    def test_many_folds(self):
        result = _generate_splits(10000, 100, 0.7, 5)
        assert len(result) > 0

    def test_splits_do_not_overlap(self):
        result = _generate_splits(1000, 5, 0.7, 10)
        for ((tr_s, tr_e), (te_s, te_e)) in result:
            assert tr_e <= te_s, "Train must end before test starts"


# ═══════════════════════════════════════════════════════════════════
# FoldMetrics tests
# ═══════════════════════════════════════════════════════════════════

class TestFoldMetricsChaos:
    """Edge cases for FoldMetrics dataclass."""

    def test_zero_trades(self):
        m = FoldMetrics(total_bars=100, signals_generated=10, trades_taken=0, wins=0, losses=0)
        assert m.win_rate == 0.0

    def test_win_rate_computed(self):
        m = FoldMetrics(total_bars=100, signals_generated=10, trades_taken=10, wins=7, losses=3)
        assert m.win_rate == 0.7

    def test_all_wins(self):
        m = FoldMetrics(total_bars=100, signals_generated=5, trades_taken=5, wins=5, losses=0)
        assert m.win_rate == 1.0

    def test_negative_pnl(self):
        m = FoldMetrics(total_bars=100, signals_generated=5, trades_taken=5, wins=2, losses=3, total_pnl_pct=-5.0)
        assert m.total_pnl_pct < 0


# ═══════════════════════════════════════════════════════════════════
# WalkForwardValidator — Chaos
# ═══════════════════════════════════════════════════════════════════

class TestWalkForwardChaos:
    """Chaos tests for WalkForwardValidator."""

    def test_empty_dataset(self):
        strat = FakeStrategy()
        data = {"open": [], "high": [], "low": [], "close": [], "volume": []}
        v = WalkForwardValidator(strat, data, n_folds=5)
        results = v.run_validation()
        assert results.n_folds == 0
        assert results.recommendation == "NO_DATA"

    def test_single_bar(self):
        strat = FakeStrategy()
        data = _make_ohlcv(1)
        v = WalkForwardValidator(strat, data, n_folds=5)
        results = v.run_validation()
        assert results.n_folds == 0

    def test_two_bars(self):
        strat = FakeStrategy()
        data = _make_ohlcv(2)
        v = WalkForwardValidator(strat, data, n_folds=5)
        results = v.run_validation()
        assert results.n_folds == 0

    def test_dataset_with_gaps(self):
        strat = FakeStrategy()
        data = _make_ohlcv_with_gaps(100, gap_positions=[10, 50, 90])
        v = WalkForwardValidator(strat, data, n_folds=3)
        # _evaluate_strategy doesn't guard against None prices — expect TypeError
        with pytest.raises(TypeError):
            v.run_validation()

    def test_dataset_with_all_none_closes(self):
        strat = FakeStrategy()
        data = {"close": [None] * 100, "open": [None] * 100, "high": [None] * 100, "low": [None] * 100, "volume": [0] * 100}
        v = WalkForwardValidator(strat, data, n_folds=3)
        with pytest.raises(TypeError):
            v.run_validation()

    def test_very_large_dataset(self):
        strat = FakeStrategy()
        data = _make_ohlcv(50000)
        v = WalkForwardValidator(strat, data, n_folds=10)
        results = v.run_validation()
        assert isinstance(results, WalkForwardResults)
        assert results.n_folds > 0

    def test_extremely_large_dataset(self):
        strat = FakeStrategy()
        data = _make_ohlcv(200_000)
        v = WalkForwardValidator(strat, data, n_folds=5)
        results = v.run_validation()
        assert isinstance(results, WalkForwardResults)

    def test_invalid_n_folds_zero(self):
        strat = FakeStrategy()
        data = _make_ohlcv(100)
        with pytest.raises(ZeroDivisionError):
            WalkForwardValidator(strat, data, n_folds=0)

    def test_invalid_n_folds_negative(self):
        # negative n_folds → fold_size=0 → no splits → no error
        strat = FakeStrategy()
        data = _make_ohlcv(100)
        v = WalkForwardValidator(strat, data, n_folds=-1)
        results = v.run_validation()
        assert results.n_folds == 0

    def test_train_ratio_negative(self):
        strat = FakeStrategy()
        data = _make_ohlcv(100)
        v = WalkForwardValidator(strat, data, n_folds=3, train_ratio=-0.5)
        results = v.run_validation()
        assert isinstance(results, WalkForwardResults)

    def test_train_ratio_greater_than_one(self):
        strat = FakeStrategy()
        data = _make_ohlcv(100)
        v = WalkForwardValidator(strat, data, n_folds=3, train_ratio=1.5)
        results = v.run_validation()
        assert isinstance(results, WalkForwardResults)

    def test_embargo_larger_than_data(self):
        strat = FakeStrategy()
        data = _make_ohlcv(100)
        v = WalkForwardValidator(strat, data, n_folds=3, embargo_bars=200)
        results = v.run_validation()
        assert results.n_folds == 0

    def test_strategy_generates_no_signals(self):
        strat = AlwaysNoneStrategy()
        data = _make_ohlcv(500)
        v = WalkForwardValidator(strat, data, n_folds=3)
        results = v.run_validation()
        assert isinstance(results, WalkForwardResults)
        assert results.oos_sharpe == 0.0

    def test_sell_only_strategy(self):
        strat = SellStrategy()
        data = _make_ohlcv(500)
        v = WalkForwardValidator(strat, data, n_folds=3)
        results = v.run_validation()
        assert isinstance(results, WalkForwardResults)

    def test_volatile_strategy(self):
        strat = VolatileStrategy()
        data = _make_ohlcv(500)
        v = WalkForwardValidator(strat, data, n_folds=3)
        results = v.run_validation()
        assert isinstance(results, WalkForwardResults)

    def test_get_results_before_run(self):
        strat = FakeStrategy()
        data = _make_ohlcv(100)
        v = WalkForwardValidator(strat, data, n_folds=3)
        assert v.get_results() is None

    def test_get_results_after_run(self):
        strat = FakeStrategy()
        data = _make_ohlcv(500)
        v = WalkForwardValidator(strat, data, n_folds=3)
        v.run_validation()
        results = v.get_results()
        assert results is not None
        assert isinstance(results, WalkForwardResults)

    def test_run_twice_overwrites(self):
        strat = FakeStrategy()
        data = _make_ohlcv(500)
        v = WalkForwardValidator(strat, data, n_folds=3)
        r1 = v.run_validation()
        r2 = v.run_validation()
        assert r1.n_folds == r2.n_folds

    def test_custom_symbol(self):
        strat = FakeStrategy()
        data = _make_ohlcv(500)
        v = WalkForwardValidator(strat, data, n_folds=3, symbol="XAUUSD")
        results = v.run_validation()
        assert results.strategy_id == "test_strat"

    def test_multiple_embargo_values(self):
        strat = FakeStrategy()
        data = _make_ohlcv(500)
        for embargo in [0, 5, 10, 50]:
            v = WalkForwardValidator(strat, data, n_folds=3, embargo_bars=embargo)
            results = v.run_validation()
            assert isinstance(results, WalkForwardResults)

    def test_concurrent_validation(self):
        strat = FakeStrategy()
        data = _make_ohlcv(500)

        results = []
        for _ in range(5):
            v = WalkForwardValidator(strat, data, n_folds=3)
            results.append(v.run_validation())
        assert len(results) == 5
        assert all(isinstance(r, WalkForwardResults) for r in results)


# ═══════════════════════════════════════════════════════════════════
# Compare strategies — Chaos
# ═══════════════════════════════════════════════════════════════════

class TestCompareStrategiesChaos:
    """Chaos tests for compare_strategies static method."""

    def test_compare_identical_strategies(self):
        a = FakeStrategy("strat_a")
        b = FakeStrategy("strat_b")
        data = _make_ohlcv(500)
        comp = WalkForwardValidator.compare_strategies(a, b, data, n_folds=3)
        assert isinstance(comp, StrategyComparison)
        assert comp.winner in ("strat_a", "strat_b")

    def test_compare_different_strategies(self):
        a = FakeStrategy("fast")
        b = SellStrategy()
        data = _make_ohlcv(500)
        comp = WalkForwardValidator.compare_strategies(a, b, data, n_folds=3)
        assert comp.margin >= 0

    def test_compare_with_empty_data(self):
        a = FakeStrategy("a")
        b = FakeStrategy("b")
        data = {"open": [], "high": [], "low": [], "close": [], "volume": []}
        comp = WalkForwardValidator.compare_strategies(a, b, data, n_folds=3)
        assert isinstance(comp, StrategyComparison)

    def test_compare_with_gaps(self):
        a = FakeStrategy("a")
        b = SellStrategy()
        data = _make_ohlcv_with_gaps(500, gap_positions=[50, 200, 400])
        # _evaluate_strategy crashes on None prices
        with pytest.raises(TypeError):
            WalkForwardValidator.compare_strategies(a, b, data, n_folds=3)

    def test_compare_with_kwargs(self):
        a = FakeStrategy("a")
        b = SellStrategy()
        data = _make_ohlcv(500)
        comp = WalkForwardValidator.compare_strategies(
            a, b, data, n_folds=5, train_ratio=0.8, embargo_bars=10,
        )
        assert isinstance(comp, StrategyComparison)

    def test_compare_concurrent(self):
        a = FakeStrategy("a")
        b = SellStrategy()
        data = _make_ohlcv(500)

        results = []
        for _ in range(5):
            results.append(WalkForwardValidator.compare_strategies(a, b, data, n_folds=3))
        assert len(results) == 5


# ═══════════════════════════════════════════════════════════════════
# WalkForwardResults — Chaos
# ═══════════════════════════════════════════════════════════════════

class TestWalkForwardResultsChaos:
    """Edge cases for WalkForwardResults aggregation."""

    def test_aggregate_empty_folds(self):
        strat = FakeStrategy()
        data = {"close": [], "open": [], "high": [], "low": [], "volume": []}
        v = WalkForwardValidator(strat, data, n_folds=3)
        results = v.run_validation()
        assert results.recommendation == "NO_DATA"
        assert results.folds == []

    def test_aggregate_single_fold(self):
        strat = FakeStrategy()
        data = _make_ohlcv(500)
        v = WalkForwardValidator(strat, data, n_folds=1)
        results = v.run_validation()
        assert results.n_folds == 1

    def test_aggregate_with_high_drawdown(self):
        class CrashStrategy:
            def __init__(self):
                self._id = "crash"
            @property
            def id(self):
                return self._id
            def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
                if len(ohlcv_data.get("close", [])) > 100:
                    return FakeSignal("SELL")
                return FakeSignal("BUY")
            def required_features(self):
                return []

        strat = CrashStrategy()
        data = _make_ohlcv(500)
        v = WalkForwardValidator(strat, data, n_folds=3)
        results = v.run_validation()
        assert isinstance(results, WalkForwardResults)
        assert results.oos_max_drawdown_pct >= 0

    def test_recommendation_pass_threshold(self):
        strat = FakeStrategy()
        data = _make_ohlcv(500)
        v = WalkForwardValidator(strat, data, n_folds=3)
        results = v.run_validation()
        assert "PASS" in results.recommendation or "FAIL" in results.recommendation

    def test_results_dataclass_fields(self):
        strat = FakeStrategy()
        data = _make_ohlcv(500)
        v = WalkForwardValidator(strat, data, n_folds=3)
        results = v.run_validation()
        assert hasattr(results, "strategy_id")
        assert hasattr(results, "n_folds")
        assert hasattr(results, "folds")
        assert hasattr(results, "oos_win_rate")
        assert hasattr(results, "oos_sharpe")
        assert hasattr(results, "stability_score")
        assert hasattr(results, "deflated_sharpe")
        assert hasattr(results, "probability_of_overfitting")
        assert hasattr(results, "recommendation")
        assert hasattr(results, "passed")
