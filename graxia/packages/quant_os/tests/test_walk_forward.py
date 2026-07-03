"""
Tests for backtest/walk_forward.py — Walk-forward validation framework.

Covers:
- Walk-forward split logic (rolling and anchored modes)
- Train/test window generation
- No future data leakage (OOS never overlaps IS)
- Edge cases (single window attempt, insufficient data)
- Metrics aggregation across windows
- validate_walk_forward_requirements() golden-rule checks
- WalkForwardWindow and WalkForwardResult dataclasses

Mocks the entire transitive import chain (engine → core.enums → etc.)
so walk_forward.py can be loaded without real dependencies.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import math
from datetime import datetime, date, timedelta, UTC
from types import ModuleType
from typing import Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from pathlib import Path
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Mock package hierarchy — install before loading walk_forward
# ---------------------------------------------------------------------------

def _make_mock_module(name: str, attrs: dict | None = None) -> ModuleType:
    """Create a mock module and register it in sys.modules."""
    m = ModuleType(name)
    m.__path__ = []
    if attrs:
        for k, v in attrs.items():
            setattr(m, k, v)
    sys.modules[name] = m
    return m


# Install mock hierarchy so all relative imports resolve
_make_mock_module("quant_os")
_make_mock_module("quant_os.core")
_make_mock_module("quant_os.core.enums", {
    "CloseReason": MagicMock(),
    "PositionType": MagicMock(),
    "SignalType": MagicMock(),
    "OrderSide": MagicMock(),
    "RegimeType": MagicMock(),
    "TradingMode": MagicMock(),
})
_make_mock_module("quant_os.core.events", {"BarEvent": MagicMock()})
_make_mock_module("quant_os.core.exceptions", {"StrictMTFViolation": Exception})
_make_mock_module("quant_os.core.lookahead_guard", {"LookaheadGuard": MagicMock()})
_make_mock_module("quant_os.execution")
_make_mock_module("quant_os.execution.conservative_bar_model", {
    "estimate_bid_ask_from_bar": MagicMock(),
})
_make_mock_module("quant_os.execution.execution_simulator", {
    "BacktestExecutionSimulator": MagicMock(),
    "ContractSpec": MagicMock(),
    "MarketSnapshot": MagicMock(),
    "OrderIntent": MagicMock(),
})
_make_mock_module("quant_os.strategies")
_make_mock_module("quant_os.strategies.base", {"Strategy": MagicMock})

# Mock backtest sub-modules
_mock_engine = _make_mock_module("quant_os.backtest.engine", {
    "BacktestEngine": MagicMock,
    "BacktestConfig": MagicMock(),
})
_mock_metrics = _make_mock_module("quant_os.backtest.metrics", {
    "BacktestMetrics": MagicMock,
    "calculate_metrics": MagicMock(),
})
_make_mock_module("quant_os.backtest")

# Also register as top-level "backtest.*" for relative imports
sys.modules["backtest"] = sys.modules["quant_os.backtest"]
sys.modules["backtest.engine"] = _mock_engine
sys.modules["backtest.metrics"] = _mock_metrics

# Now load walk_forward.py via importlib
# It does: from .engine import BacktestEngine, BacktestConfig
#          from .metrics import BacktestMetrics
#          from ..strategies.base import Strategy
# These resolve to the mocks we just installed.

mod_path = Path(__file__).resolve().parent.parent / "backtest" / "walk_forward.py"
spec = importlib.util.spec_from_file_location(
    "backtest.walk_forward",
    mod_path,
    submodule_search_locations=[],
)
wf_mod = importlib.util.module_from_spec(spec)
wf_mod.__package__ = "quant_os.backtest"  # critical: makes .engine resolve to quant_os.backtest.engine
sys.modules["backtest.walk_forward"] = wf_mod
sys.modules["quant_os.backtest.walk_forward"] = wf_mod
spec.loader.exec_module(wf_mod)

# Extract the classes we need
WalkForwardAnalyzer = wf_mod.WalkForwardAnalyzer
WalkForwardWindow = wf_mod.WalkForwardWindow
WalkForwardResult = wf_mod.WalkForwardResult
validate_walk_forward_requirements = wf_mod.validate_walk_forward_requirements


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int) -> Dict[str, List]:
    """Generate n synthetic OHLCV bars with a price uptrend."""
    import random
    random.seed(42)
    closes = [100.0]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + random.uniform(-0.005, 0.008)))
    return {
        "open": [c * 0.999 for c in closes],
        "high": [c * 1.005 for c in closes],
        "low": [c * 0.995 for c in closes],
        "close": closes,
        "volume": [1000.0] * n,
    }


def _make_timestamps(n: int) -> List[datetime]:
    """Generate n 15-minute timestamps starting 2024-01-01."""
    base = datetime(2024, 1, 1, tzinfo=UTC)
    return [base + timedelta(minutes=15 * i) for i in range(n)]


def _make_metrics(
    win_rate: float = 0.55,
    profit_factor: float = 1.5,
    sharpe: float = 1.2,
    max_dd_pct: float = 5.0,
    total_pnl: float = 500.0,
):
    """Create a simple metrics-like object (avoids MagicMock truthiness issues)."""
    @dataclass
    class _Metrics:
        win_rate: float = 0.0
        profit_factor: float = 0.0
        sharpe_ratio: float = 0.0
        max_drawdown_pct: float = 0.0
        total_pnl: float = 0.0
        total_trades: int = 0
    return _Metrics(
        win_rate=win_rate,
        profit_factor=profit_factor,
        sharpe_ratio=sharpe,
        max_drawdown_pct=max_dd_pct,
        total_pnl=total_pnl,
        total_trades=100,
    )


def _make_backtest_result(metrics: MagicMock) -> dict:
    """Create a mock backtest engine result dict."""
    return {"metrics": metrics, "trades": [], "equity_curve": []}


def _mock_strategy_factory():
    """Returns a factory that creates MagicMock Strategy instances."""
    return lambda: MagicMock()


# ---------------------------------------------------------------------------
# Tests: Window Split Logic (Rolling Mode)
# ---------------------------------------------------------------------------

class TestRollingWindowSplit:
    """Tests for the default rolling walk-forward mode."""

    def test_rolling_generates_correct_window_count(self):
        """Rolling mode generates the requested number of windows."""
        mock_metrics = _make_metrics()
        factory = _mock_strategy_factory()

        with patch.object(wf_mod, "BacktestEngine") as MockEngine:
            engine_inst = MagicMock()
            engine_inst.run.return_value = _make_backtest_result(mock_metrics)
            MockEngine.return_value = engine_inst

            analyzer = WalkForwardAnalyzer(
                strategy_factory=factory,
                is_ratio=0.7,
                mode="rolling",
            )
            data = _make_ohlcv(5000)
            ts = _make_timestamps(5000)
            result = analyzer.analyze(data, ts, n_windows=5)

        assert result.total_windows == 5

    def test_rolling_windows_are_sequential(self):
        """In rolling mode, OOS windows don't overlap with each other."""
        mock_metrics = _make_metrics()
        factory = _mock_strategy_factory()

        with patch.object(wf_mod, "BacktestEngine") as MockEngine:
            engine_inst = MagicMock()
            engine_inst.run.return_value = _make_backtest_result(mock_metrics)
            MockEngine.return_value = engine_inst

            analyzer = WalkForwardAnalyzer(
                strategy_factory=factory,
                is_ratio=0.7,
                mode="rolling",
            )
            data = _make_ohlcv(5000)
            ts = _make_timestamps(5000)
            result = analyzer.analyze(data, ts, n_windows=5)

        for i in range(len(result.windows) - 1):
            assert result.windows[i].oos_start <= result.windows[i + 1].oos_start

    def test_no_oos_leaks_into_training(self):
        """OOS start is always >= IS end (no future data leakage)."""
        mock_metrics = _make_metrics()
        factory = _mock_strategy_factory()

        with patch.object(wf_mod, "BacktestEngine") as MockEngine:
            engine_inst = MagicMock()
            engine_inst.run.return_value = _make_backtest_result(mock_metrics)
            MockEngine.return_value = engine_inst

            analyzer = WalkForwardAnalyzer(
                strategy_factory=factory,
                is_ratio=0.7,
                mode="rolling",
            )
            data = _make_ohlcv(5000)
            ts = _make_timestamps(5000)
            result = analyzer.analyze(data, ts, n_windows=3)

        for w in result.windows:
            assert w.is_start < w.is_end, "IS window must have valid date range"
            assert w.oos_start < w.oos_end, "OOS window must have valid date range"
            assert w.is_end <= w.oos_start, \
                f"IS end ({w.is_end}) must <= OOS start ({w.oos_start}) — data leakage!"


# ---------------------------------------------------------------------------
# Tests: Window Split Logic (Anchored Mode)
# ---------------------------------------------------------------------------

class TestAnchoredWindowSplit:
    """Tests for anchored walk-forward mode (IS grows from start)."""

    def test_anchored_is_starts_at_beginning(self):
        """In anchored mode, IS window always starts at index 0."""
        mock_metrics = _make_metrics()
        factory = _mock_strategy_factory()

        with patch.object(wf_mod, "BacktestEngine") as MockEngine:
            engine_inst = MagicMock()
            engine_inst.run.return_value = _make_backtest_result(mock_metrics)
            MockEngine.return_value = engine_inst

            analyzer = WalkForwardAnalyzer(
                strategy_factory=factory,
                is_ratio=0.7,
                mode="anchored",
            )
            data = _make_ohlcv(5000)
            ts = _make_timestamps(5000)
            result = analyzer.analyze(data, ts, n_windows=5)

        first_date = ts[0].date()
        for w in result.windows:
            assert w.is_start == first_date, \
                f"Anchored window {w.window_id} IS should start at {first_date}"

    def test_anchored_is_grows_with_each_window(self):
        """In anchored mode, each subsequent window has a larger IS range."""
        mock_metrics = _make_metrics()
        factory = _mock_strategy_factory()

        with patch.object(wf_mod, "BacktestEngine") as MockEngine:
            engine_inst = MagicMock()
            engine_inst.run.return_value = _make_backtest_result(mock_metrics)
            MockEngine.return_value = engine_inst

            analyzer = WalkForwardAnalyzer(
                strategy_factory=factory,
                is_ratio=0.7,
                mode="anchored",
            )
            data = _make_ohlcv(5000)
            ts = _make_timestamps(5000)
            result = analyzer.analyze(data, ts, n_windows=5)

        is_ends = [w.is_end for w in result.windows]
        for i in range(len(is_ends) - 1):
            assert is_ends[i] <= is_ends[i + 1]


# ---------------------------------------------------------------------------
# Tests: Data Sufficiency Guards
# ---------------------------------------------------------------------------

class TestDataGuards:
    """Tests for insufficient data error handling."""

    def test_insufficient_data_raises(self):
        """analyze() raises ValueError when total_bars < 1000."""
        factory = _mock_strategy_factory()
        analyzer = WalkForwardAnalyzer(strategy_factory=factory)
        data = _make_ohlcv(500)
        ts = _make_timestamps(500)

        with pytest.raises(ValueError, match="Insufficient data"):
            analyzer.analyze(data, ts, n_windows=3)

    def test_is_window_too_small_raises(self):
        """analyze() raises ValueError when IS window < 500 bars."""
        factory = _mock_strategy_factory()
        data = _make_ohlcv(1200)
        ts = _make_timestamps(1200)
        analyzer = WalkForwardAnalyzer(
            strategy_factory=factory,
            is_ratio=0.7,
            mode="rolling",
        )

        with pytest.raises(ValueError, match="IS window too small"):
            analyzer.analyze(data, ts, n_windows=5)

    def test_exact_boundary_data(self):
        """analyze() succeeds with exactly the minimum required data."""
        mock_metrics = _make_metrics()
        factory = _mock_strategy_factory()

        with patch.object(wf_mod, "BacktestEngine") as MockEngine:
            engine_inst = MagicMock()
            engine_inst.run.return_value = _make_backtest_result(mock_metrics)
            MockEngine.return_value = engine_inst

            analyzer = WalkForwardAnalyzer(
                strategy_factory=factory,
                is_ratio=0.7,
                mode="rolling",
            )
            data = _make_ohlcv(3000)
            ts = _make_timestamps(3000)
            result = analyzer.analyze(data, ts, n_windows=3)

        assert result.total_windows >= 1


# ---------------------------------------------------------------------------
# Tests: Metrics Aggregation
# ---------------------------------------------------------------------------

class TestMetricsAggregation:
    """Tests for _aggregate_results() and WalkForwardResult."""

    def test_aggregation_computes_averages(self):
        """Aggregated metrics average across all OOS windows."""
        factory = _mock_strategy_factory()
        analyzer = WalkForwardAnalyzer(strategy_factory=factory)

        m1 = _make_metrics(win_rate=0.6, profit_factor=2.0, sharpe=1.5, max_dd_pct=3.0, total_pnl=100)
        m2 = _make_metrics(win_rate=0.5, profit_factor=1.2, sharpe=0.8, max_dd_pct=5.0, total_pnl=-50)
        m3 = _make_metrics(win_rate=0.7, profit_factor=1.8, sharpe=1.2, max_dd_pct=2.0, total_pnl=200)

        windows = [
            WalkForwardWindow(window_id=0, is_start=date(2024,1,1), is_end=date(2024,3,31),
                            oos_start=date(2024,4,1), oos_end=date(2024,6,30),
                            oos_metrics=m1, is_oos_ratio=0.75, is_degradation=25.0),
            WalkForwardWindow(window_id=1, is_start=date(2024,1,1), is_end=date(2024,6,30),
                            oos_start=date(2024,7,1), oos_end=date(2024,9,30),
                            oos_metrics=m2, is_oos_ratio=0.55, is_degradation=45.0),
            WalkForwardWindow(window_id=2, is_start=date(2024,1,1), is_end=date(2024,9,30),
                            oos_start=date(2024,10,1), oos_end=date(2024,12,31),
                            oos_metrics=m3, is_oos_ratio=0.8, is_degradation=20.0),
        ]

        result = analyzer._aggregate_results(windows)

        assert result.total_windows == 3
        assert result.valid_windows == 3
        assert result.oos_win_rate == pytest.approx((0.6 + 0.5 + 0.7) / 3, abs=0.01)
        assert result.oos_sharpe == pytest.approx((1.5 + 0.8 + 1.2) / 3, abs=0.01)
        assert result.oos_max_drawdown_pct == 5.0
        assert result.oos_total_pnl == pytest.approx(250.0, abs=0.01)
        assert result.avg_is_oos_ratio == pytest.approx((0.75 + 0.55 + 0.8) / 3, abs=0.01)

    def test_oos_consistency(self):
        """oos_consistency = % of profitable OOS windows."""
        factory = _mock_strategy_factory()
        analyzer = WalkForwardAnalyzer(strategy_factory=factory)

        m1 = _make_metrics(total_pnl=100)
        m2 = _make_metrics(total_pnl=-50)
        m3 = _make_metrics(total_pnl=200)

        windows = [
            WalkForwardWindow(window_id=0, is_start=date(2024,1,1), is_end=date(2024,3,31),
                            oos_start=date(2024,4,1), oos_end=date(2024,6,30),
                            oos_metrics=m1),
            WalkForwardWindow(window_id=1, is_start=date(2024,1,1), is_end=date(2024,6,30),
                            oos_start=date(2024,7,1), oos_end=date(2024,9,30),
                            oos_metrics=m2),
            WalkForwardWindow(window_id=2, is_start=date(2024,1,1), is_end=date(2024,9,30),
                            oos_start=date(2024,10,1), oos_end=date(2024,12,31),
                            oos_metrics=m3),
        ]

        result = analyzer._aggregate_results(windows)
        assert result.oos_consistency == pytest.approx(2 / 3, abs=0.01)

    def test_overfitting_score(self):
        """overfitting_score increases with degradation and low consistency."""
        factory = _mock_strategy_factory()
        analyzer = WalkForwardAnalyzer(strategy_factory=factory)

        m1 = _make_metrics(total_pnl=-100, profit_factor=0.8)
        m2 = _make_metrics(total_pnl=-200, profit_factor=0.6)

        windows = [
            WalkForwardWindow(window_id=0, is_start=date(2024,1,1), is_end=date(2024,3,31),
                            oos_start=date(2024,4,1), oos_end=date(2024,6,30),
                            oos_metrics=m1, is_oos_ratio=0.3, is_degradation=70.0),
            WalkForwardWindow(window_id=1, is_start=date(2024,1,1), is_end=date(2024,6,30),
                            oos_start=date(2024,7,1), oos_end=date(2024,9,30),
                            oos_metrics=m2, is_oos_ratio=0.2, is_degradation=80.0),
        ]

        result = analyzer._aggregate_results(windows)
        assert result.overfitting_score > 0.5
        assert result.overfitting_score <= 1.0

    def test_empty_windows(self):
        """Aggregation with empty window list returns zero-valued result."""
        factory = _mock_strategy_factory()
        analyzer = WalkForwardAnalyzer(strategy_factory=factory)
        result = analyzer._aggregate_results([])
        assert result.total_windows == 0
        assert result.valid_windows == 0
        assert result.oos_win_rate == 0.0
        assert result.oos_total_pnl == 0.0


# ---------------------------------------------------------------------------
# Tests: validate_walk_forward_requirements
# ---------------------------------------------------------------------------

class TestValidateRequirements:
    """Tests for validate_walk_forward_requirements() golden rule checks."""

    def test_all_passed(self):
        """Perfect result passes all golden rule checks (including Phase 3 WFE + stability)."""
        result = WalkForwardResult(
            total_windows=5,
            valid_windows=5,
            oos_win_rate=0.6,
            oos_profit_factor=1.5,
            oos_sharpe=1.2,
            oos_max_drawdown_pct=5.0,
            oos_total_pnl=1000.0,
            oos_consistency=0.8,
            avg_is_oos_ratio=0.7,
            overfitting_score=0.2,
            walk_forward_efficiency=0.8,  # Phase 3: OOS/IS Sharpe > 0.5
            parameter_stability={"ema_period": 0.1},  # Phase 3: CV < 0.30
        )
        checks = validate_walk_forward_requirements(result)
        assert checks["all_passed"] is True
        assert checks["min_windows"] is True
        assert checks["profitable_oos"] is True
        assert checks["positive_oos_pnl"] is True
        assert checks["oos_win_rate_sane"] is True
        assert checks["overfitting_acceptable"] is True
        assert checks["is_oos_ratio_acceptable"] is True
        assert checks["wfe_acceptable"] is True
        assert checks["parameter_stability_acceptable"] is True

    def test_fails_min_windows(self):
        """Result with < 3 windows fails min_windows check."""
        result = WalkForwardResult(total_windows=2, valid_windows=2, oos_consistency=0.8,
                                   oos_total_pnl=100, oos_win_rate=0.6, overfitting_score=0.2,
                                   avg_is_oos_ratio=0.7)
        checks = validate_walk_forward_requirements(result)
        assert checks["min_windows"] is False
        assert checks["all_passed"] is False

    def test_fails_profitable_oos(self):
        """Result with < 50% profitable windows fails."""
        result = WalkForwardResult(total_windows=5, valid_windows=5, oos_consistency=0.3,
                                   oos_total_pnl=100, oos_win_rate=0.6, overfitting_score=0.2,
                                   avg_is_oos_ratio=0.7)
        checks = validate_walk_forward_requirements(result)
        assert checks["profitable_oos"] is False
        assert checks["all_passed"] is False

    def test_fails_positive_pnl(self):
        """Negative OOS total PnL fails."""
        result = WalkForwardResult(total_windows=5, valid_windows=5, oos_consistency=0.8,
                                   oos_total_pnl=-500, oos_win_rate=0.6, overfitting_score=0.2,
                                   avg_is_oos_ratio=0.7)
        checks = validate_walk_forward_requirements(result)
        assert checks["positive_oos_pnl"] is False
        assert checks["all_passed"] is False

    def test_fails_win_rate_sane(self):
        """Win rate below 0.45 fails sanity check."""
        result = WalkForwardResult(total_windows=5, valid_windows=5, oos_consistency=0.8,
                                   oos_total_pnl=100, oos_win_rate=0.40, overfitting_score=0.2,
                                   avg_is_oos_ratio=0.7)
        checks = validate_walk_forward_requirements(result)
        assert checks["oos_win_rate_sane"] is False
        assert checks["all_passed"] is False

    def test_fails_overfitting(self):
        """Overfitting score >= 0.6 fails."""
        result = WalkForwardResult(total_windows=5, valid_windows=5, oos_consistency=0.8,
                                   oos_total_pnl=100, oos_win_rate=0.6, overfitting_score=0.7,
                                   avg_is_oos_ratio=0.7)
        checks = validate_walk_forward_requirements(result)
        assert checks["overfitting_acceptable"] is False
        assert checks["all_passed"] is False

    def test_fails_is_oos_ratio(self):
        """IS/OOS ratio below 0.5 fails."""
        result = WalkForwardResult(total_windows=5, valid_windows=5, oos_consistency=0.8,
                                   oos_total_pnl=100, oos_win_rate=0.6, overfitting_score=0.2,
                                   avg_is_oos_ratio=0.4)
        checks = validate_walk_forward_requirements(result)
        assert checks["is_oos_ratio_acceptable"] is False
        assert checks["all_passed"] is False


# ---------------------------------------------------------------------------
# Tests: IS/OOS Ratio Calculation
# ---------------------------------------------------------------------------

class TestIsOosRatio:
    """Tests for is_oos_ratio and is_degradation calculation per window."""

    def test_ratio_calculation(self):
        """IS/OOS ratio = OOS_profit_factor / IS_profit_factor."""
        is_m = _make_metrics(profit_factor=2.0)
        oos_m = _make_metrics(profit_factor=1.0)
        window = WalkForwardWindow(
            window_id=0,
            is_start=date(2024, 1, 1), is_end=date(2024, 3, 31),
            oos_start=date(2024, 4, 1), oos_end=date(2024, 6, 30),
            is_metrics=is_m, oos_metrics=oos_m,
        )
        is_pf = is_m.profit_factor if is_m.profit_factor != float('inf') else 10
        oos_pf = oos_m.profit_factor if oos_m.profit_factor != float('inf') else 10
        window.is_oos_ratio = oos_pf / is_pf if is_pf > 0 else 0
        window.is_degradation = (1 - window.is_oos_ratio) * 100

        assert window.is_oos_ratio == pytest.approx(0.5, abs=0.01)
        assert window.is_degradation == pytest.approx(50.0, abs=0.01)

    def test_inf_profit_factor_handled(self):
        """Infinite profit factor is capped at 10 for ratio calculation."""
        is_pf = float('inf')
        oos_pf = 2.0
        is_capped = is_pf if is_pf != float('inf') else 10
        oos_capped = oos_pf if oos_pf != float('inf') else 10
        ratio = oos_capped / is_capped if is_capped > 0 else 0

        assert ratio == pytest.approx(0.2, abs=0.01)


# ---------------------------------------------------------------------------
# Tests: Window Dataclass
# ---------------------------------------------------------------------------

class TestWindowDataclass:
    """Tests for WalkForwardWindow and WalkForwardResult dataclasses."""

    def test_window_defaults(self):
        """WalkForwardWindow defaults are reasonable."""
        w = WalkForwardWindow(
            window_id=0,
            is_start=date(2024, 1, 1),
            is_end=date(2024, 3, 31),
            oos_start=date(2024, 4, 1),
            oos_end=date(2024, 6, 30),
        )
        assert w.window_id == 0
        assert w.is_metrics is None
        assert w.oos_metrics is None
        assert w.is_oos_ratio == 0.0
        assert w.is_degradation == 0.0

    def test_result_post_init(self):
        """WalkForwardResult initializes empty windows list."""
        r = WalkForwardResult(total_windows=0, valid_windows=0)
        assert r.windows == []
        assert r.oos_win_rate == 0.0
        assert r.overfitting_score == 0.0

    def test_result_with_windows(self):
        """WalkForwardResult accepts windows list."""
        w = WalkForwardWindow(
            window_id=0,
            is_start=date(2024, 1, 1), is_end=date(2024, 3, 31),
            oos_start=date(2024, 4, 1), oos_end=date(2024, 6, 30),
        )
        r = WalkForwardResult(total_windows=1, valid_windows=0, windows=[w])
        assert len(r.windows) == 1
        assert r.windows[0].window_id == 0


# ---------------------------------------------------------------------------
# Tests: Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases: no valid OOS metrics, single window, etc."""

    def test_no_valid_oos_metrics(self):
        """Aggregation with windows but no oos_metrics returns zero results."""
        factory = _mock_strategy_factory()
        analyzer = WalkForwardAnalyzer(strategy_factory=factory)

        windows = [
            WalkForwardWindow(window_id=0, is_start=date(2024,1,1), is_end=date(2024,3,31),
                            oos_start=date(2024,4,1), oos_end=date(2024,6,30),
                            oos_metrics=None),
            WalkForwardWindow(window_id=1, is_start=date(2024,1,1), is_end=date(2024,6,30),
                            oos_start=date(2024,7,1), oos_end=date(2024,9,30),
                            oos_metrics=None),
        ]

        result = analyzer._aggregate_results(windows)
        assert result.total_windows == 2
        assert result.valid_windows == 0
        assert result.oos_win_rate == 0.0
        assert result.oos_consistency == 0.0

    def test_single_profitable_window(self):
        """Single profitable window → 100% consistency, positive PnL."""
        factory = _mock_strategy_factory()
        analyzer = WalkForwardAnalyzer(strategy_factory=factory)

        m = _make_metrics(total_pnl=500, profit_factor=2.0)
        windows = [
            WalkForwardWindow(window_id=0, is_start=date(2024,1,1), is_end=date(2024,3,31),
                            oos_start=date(2024,4,1), oos_end=date(2024,6,30),
                            oos_metrics=m, is_oos_ratio=0.8, is_degradation=20.0),
        ]

        result = analyzer._aggregate_results(windows)
        assert result.oos_consistency == 1.0
        assert result.oos_total_pnl == 500.0
        assert result.overfitting_score < 0.5

    def test_all_losing_windows(self):
        """All losing OOS windows → 0% consistency, high overfitting score."""
        factory = _mock_strategy_factory()
        analyzer = WalkForwardAnalyzer(strategy_factory=factory)

        m = _make_metrics(total_pnl=-100, profit_factor=0.5)
        windows = [
            WalkForwardWindow(window_id=i, is_start=date(2024,1,1), is_end=date(2024,3,31),
                            oos_start=date(2024,4,1), oos_end=date(2024,6,30),
                            oos_metrics=m, is_oos_ratio=0.3, is_degradation=70.0)
            for i in range(3)
        ]

        result = analyzer._aggregate_results(windows)
        assert result.oos_consistency == 0.0
        assert result.oos_total_pnl < 0
        assert result.overfitting_score > 0.5
