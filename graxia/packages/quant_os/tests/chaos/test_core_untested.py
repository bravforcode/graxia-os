"""Chaos-mode tests for ALL untested core/ modules."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from graxia.packages.quant_os.core.agents.researcher import BullBearResearcherAgent
from graxia.packages.quant_os.core.config import QuantConfig
from graxia.packages.quant_os.core.correlation import CorrelationFilter
from graxia.packages.quant_os.core.cost_model import (
    COST_PER_TRADE_BY_SESSION,
    get_backtest_cost,
    get_live_round_trip_cost,
    get_live_spread_as_return,
    get_session,
)
from graxia.packages.quant_os.core.enums import SignalType
from graxia.packages.quant_os.core.events import Event, SignalEvent
from graxia.packages.quant_os.core.kelly import (
    MAX_FRACTION,
    MIN_FRACTION,
    kelly_adjust_for_regime,
    kelly_fraction,
    kelly_size,
)
from graxia.packages.quant_os.core.lifecycle import StrategyLifecycle
from graxia.packages.quant_os.core.lookahead_guard import LookaheadGuard, LookaheadViolation
from graxia.packages.quant_os.core.monte_carlo import MonteCarloResult
from graxia.packages.quant_os.core.observability import FileSink, LokiSink, setup_logging
from graxia.packages.quant_os.core.pair_filter import (
    BacktestSupport,
    MinVolumeFilter,
    PairFilter,
    PairFilterPipeline,
    SpreadFilter,
)
from graxia.packages.quant_os.core.param_sweep import ParamSweep
from graxia.packages.quant_os.core.portfolio_risk import PortfolioRisk
from graxia.packages.quant_os.core.portfolio_risk import Position as PortfolioPosition
from graxia.packages.quant_os.core.position_manager import Position, PositionManager
from graxia.packages.quant_os.core.production_readiness import CheckResult, ProductionReadiness
from graxia.packages.quant_os.core.reconciler import StateReconciler
from graxia.packages.quant_os.core.regime_filter import MarketRegime, RegimeFilter, RegimeResult
from graxia.packages.quant_os.core.risk.swap_cost import (
    estimate_overnight_cost,
    get_live_swap_rates,
    get_swap_cost_for_trade,
)
from graxia.packages.quant_os.core.rollover_filter import RolloverFilter, RolloverStatus
from graxia.packages.quant_os.core.signal_filter import FakeSignalFilter, FilterResult
from graxia.packages.quant_os.core.stability import StabilityResult
from graxia.packages.quant_os.core.structured_trades import TradeRecord, TradeRecords
from graxia.packages.quant_os.core.telegram_callback import (
    CallbackAction,
    CallbackResult,
    PendingSignal,
    TelegramCallbackHandler,
)
from graxia.packages.quant_os.core.telegram_notify import TelegramNotifier, _load_config
from graxia.packages.quant_os.core.walk_forward_production import WalkForwardDashboard
from graxia.packages.quant_os.core.walk_forward_viz import WalkForwardViz


# === 1. core/kelly.py ===
class TestKellyChaos:
    def test_import(self):
        assert callable(kelly_fraction) and callable(kelly_size)

    @pytest.mark.parametrize("wr", [0.0, -1.0, 1.0, 2.0, float("inf")])
    def test_invalid_win_rate(self, wr):
        assert kelly_fraction(win_rate=wr, avg_rr=1.5) == MIN_FRACTION

    @pytest.mark.parametrize("rr", [0.0, -1.0, float("-inf")])
    def test_invalid_avg_rr(self, rr):
        assert kelly_fraction(win_rate=0.6, avg_rr=rr) == MIN_FRACTION

    def test_none_types_raise(self):
        with pytest.raises((TypeError, ValueError)):
            kelly_fraction(win_rate=None, avg_rr=1.5)

    def test_extreme_edge_clamped(self):
        assert kelly_fraction(win_rate=0.99, avg_rr=10.0, use_half=False) == MAX_FRACTION

    def test_half_kelly(self):
        full = kelly_fraction(win_rate=0.6, avg_rr=2.0, use_half=False)
        half = kelly_fraction(win_rate=0.6, avg_rr=2.0, use_half=True)
        # half <= full (clamping may make them equal)
        assert half <= full

    def test_negative_edge_returns_min(self):
        assert kelly_fraction(win_rate=0.4, avg_rr=0.5) == MIN_FRACTION

    def test_kelly_size_zero_sl(self):
        assert kelly_size(capital=10000, win_rate=0.6, avg_rr=2.0, sl_pips=0)["lots"] == 0.0

    def test_kelly_size_zero_pip_value(self):
        assert kelly_size(capital=10000, win_rate=0.6, avg_rr=2.0, sl_pips=100, pip_value=0)["lots"] == 0.0

    def test_kelly_size_zero_capital(self):
        assert kelly_size(capital=0, win_rate=0.6, avg_rr=2.0, sl_pips=100)["risk_dollars"] == 0.0

    def test_kelly_adjust_regime(self):
        assert kelly_adjust_for_regime(0.03, "NORMAL") == 0.03
        assert kelly_adjust_for_regime(0.04, "HIGH_UNCERTAINTY") == 0.02
        assert kelly_adjust_for_regime(0.04, "CRISIS") == MIN_FRACTION
        assert kelly_adjust_for_regime(0.04, "UNKNOWN") == 0.02

    def test_kelly_size_keys(self):
        r = kelly_size(capital=10000, win_rate=0.6, avg_rr=2.0, sl_pips=100)
        assert set(r.keys()) == {"kelly_fraction", "risk_dollars", "lots", "capital", "win_rate", "avg_rr", "sl_pips"}

    def test_stress_many_calls(self):
        for i in range(1000):
            kelly_fraction(win_rate=0.5 + (i % 50) / 100, avg_rr=0.5 + (i % 100) / 50)

    def test_bounded_output(self):
        for i in range(500):
            wr = 0.01 + abs(hash(i)) % 98 / 100
            rr = 0.1 + abs(hash(i + 1)) % 100
            r = kelly_fraction(win_rate=wr, avg_rr=rr)
            assert MIN_FRACTION <= r <= MAX_FRACTION


# === 2. core/lifecycle.py ===
class TestLifecycleChaos:
    def test_subclass(self):
        class S(StrategyLifecycle):
            pass

        assert isinstance(S(), StrategyLifecycle)

    def test_default_hooks(self):
        s = StrategyLifecycle()
        s.bot_start()
        s.bot_loop_start(datetime.now(UTC))
        assert s.confirm_trade_entry("XAUUSD", "BUY", 0.01, 2000.0) is True
        assert s.confirm_trade_exit("XAUUSD", "t1", "TP") is True
        s.on_trade_open("XAUUSD", "o1")
        s.on_trade_close("XAUUSD", "o1", 10.0)

    def test_override_reject(self):
        class R(StrategyLifecycle):
            def confirm_trade_entry(self, *a):
                return False

        assert R().confirm_trade_entry("X", "B", 1, 1) is False

    def test_hooks_receive_correct_types(self):
        calls = []

        class T(StrategyLifecycle):
            def bot_loop_start(self, ct):
                calls.append(type(ct).__name__)

            def on_trade_close(self, s, o, p):
                calls.append(p)

        t = T()
        t.bot_loop_start(datetime(2025, 1, 1, tzinfo=UTC))
        t.on_trade_close("X", "o1", 42.5)
        assert calls[0] == "datetime"
        assert calls[1] == 42.5


# === 3. core/lookahead_guard.py ===
class TestLookaheadGuardChaos:
    def test_import(self):
        assert issubclass(LookaheadViolation, Exception)

    def test_advance(self):
        g = LookaheadGuard()
        g.initialize(10)
        for _ in range(10):
            g.advance()
        assert g._current_index == 10

    def test_advance_beyond(self):
        g = LookaheadGuard()
        g.initialize(5)
        for _ in range(10):
            g.advance()
        assert g._current_index == 5

    def test_violation(self):
        g = LookaheadGuard()
        g.initialize(10)
        g.advance()
        assert g.check_data_access(5, "test") is False
        assert g.has_violations

    def test_strict_raises(self):
        g = LookaheadGuard(strict=True)
        g.initialize(10)
        g.advance()
        with pytest.raises(LookaheadViolation):
            g.check_data_access(5, "test")

    def test_violations_accumulate(self):
        g = LookaheadGuard()
        g.initialize(10)
        g.advance()
        g.check_data_access(5, "t1")
        g.check_data_access(8, "t2")
        assert len(g.violations) == 2

    def test_reset(self):
        g = LookaheadGuard()
        g.initialize(10)
        g.advance()
        g.check_data_access(5, "t")
        g.reset()
        assert g._current_index == 0
        assert not g.has_violations

    def test_get_slice(self):
        g = LookaheadGuard()
        g.initialize(10)
        for _ in range(5):
            g.advance()
        data = {"a": list(range(10))}
        assert len(g.get_slice(data)["a"]) == 6

    def test_stress(self):
        g = LookaheadGuard()
        g.initialize(1000)
        for i in range(1000):
            g.advance()
            g.check_data_access(i, "s")


# === 4. core/correlation.py ===
class TestCorrelationChaos:
    def test_empty(self):
        cf = CorrelationFilter()
        cf.set_open(["XAUUSD"])
        assert cf.get_multiplier("XAUUSD", ["XAUUSD"]) == 1.0

    def test_single_symbol(self):
        cf = CorrelationFilter()
        for i in range(50):
            cf.update("X", 2000.0 + i)
        assert cf.get_multiplier("X", ["X"]) == 1.0

    def test_perfectly_correlated(self):
        cf = CorrelationFilter(lookback=100)
        for i in range(50):
            cf.update("A", 2000.0 + i * 0.1)
            cf.update("B", 25.0 + i * 0.001)
        assert cf.get_multiplier("A", ["B"]) == 0.0

    def test_no_open_symbols(self):
        assert CorrelationFilter().get_multiplier("X", []) == 1.0

    def test_bounded(self):
        cf = CorrelationFilter(lookback=20)
        for i in range(200):
            cf.update("X", 2000.0 + i)
        assert len(cf._prices["X"]) <= 40

    def test_all_correlations(self):
        cf = CorrelationFilter()
        for i in range(30):
            cf.update("A", 100.0 + i)
            cf.update("B", 200.0 + i * 2)
        r = cf.get_all_correlations()
        assert ("A", "B") in r

    def test_too_few_points(self):
        cf = CorrelationFilter()
        cf.update("A", 100.0)
        cf.update("B", 200.0)
        assert cf._correlation("A", "B") == 0.0

    def test_stress_many_symbols(self):
        cf = CorrelationFilter()
        syms = [f"S{i}" for i in range(50)]
        for i in range(30):
            for s in syms:
                cf.update(s, 100.0 + hash((s, i)) % 100)
        cf.get_multiplier("S0", syms)
        cf.get_all_correlations()


# === 5. core/cost_model.py ===
class TestCostModelChaos:
    @pytest.mark.parametrize(
        "hour,expected",
        [
            (0, "asian"),
            (6, "asian"),
            (7, "london"),
            (11, "london"),
            (12, "overlap"),
            (15, "overlap"),
            (16, "ny"),
            (20, "ny"),
            (21, "asian"),
            (23, "asian"),
        ],
    )
    def test_session(self, hour, expected):
        assert get_session(hour_utc=hour) == expected

    def test_all_hours(self):
        for h in range(24):
            assert get_session(h) in COST_PER_TRADE_BY_SESSION

    def test_backtest_cost_positive(self):
        ts = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        assert get_backtest_cost(timestamp=ts) > 0

    def test_backtest_cost_no_timestamp(self):
        assert get_backtest_cost(timestamp=None) > 0

    def test_no_mt5(self):
        with patch.dict("sys.modules", {"MetaTrader5": None}):
            assert get_live_round_trip_cost() is None
            assert get_live_spread_as_return() is None


# === 6. core/pair_filter.py ===
class TestPairFilterChaos:
    def test_volume_empty(self):
        assert MinVolumeFilter().filter([], {}) == []

    def test_volume_pass(self):
        f = MinVolumeFilter(min_volume=100)
        ctx = {"tickers": {"A": {"volume": 200}, "B": {"volume": 50}}}
        assert f.filter(["A", "B"], ctx) == ["A"]

    def test_spread_pass(self):
        f = SpreadFilter(max_spread_pct=0.5)
        ctx = {"tickers": {"A": {"spread_pct": 0.3}, "B": {"spread_pct": 1.0}}}
        assert f.filter(["A", "B"], ctx) == ["A"]

    def test_pipeline_chained(self):
        pipe = PairFilterPipeline([MinVolumeFilter(100), SpreadFilter(0.5)])
        ctx = {"tickers": {"A": {"volume": 200, "spread_pct": 0.3}, "B": {"volume": 200, "spread_pct": 1.0}}}
        assert pipe.apply(["A", "B"], ctx) == ["A"]

    def test_pipeline_empty(self):
        assert PairFilterPipeline().apply(["A"], {}) == ["A"]

    def test_missing_tickers(self):
        assert MinVolumeFilter().filter(["A"], {}) == []

    def test_validate_backtest(self):
        class Biased(PairFilter):
            backtest_support = BacktestSupport.BIASED

            def filter(self, pairs, context):
                return pairs

        class Unsupported(PairFilter):
            backtest_support = BacktestSupport.UNSUPPORTED

            def filter(self, pairs, context):
                return pairs

        pipe = PairFilterPipeline([Biased(), Unsupported()])
        assert len(pipe.validate_for_backtest()) == 2

    def test_stress(self):
        pairs = [f"S{i}" for i in range(1000)]
        ctx = {"tickers": {f"S{i}": {"volume": i} for i in range(1000)}}
        assert len(MinVolumeFilter(1).filter(pairs, ctx)) == 999


# === 7. core/signal_filter.py ===
class TestSignalFilterChaos:
    def test_grades(self):
        assert FilterResult(True, 6, {}, {}).grade == "S"
        assert FilterResult(True, 5, {}, {}).grade == "A"
        assert FilterResult(False, 4, {}, {}).grade == "B"
        assert FilterResult(False, 3, {}, {}).grade == "C"
        assert FilterResult(False, 0, {}, {}).grade == "F"

    def test_evaluate_all_none(self):
        r = FakeSignalFilter().evaluate()
        assert r.score == 0 and r.grade == "F"

    def test_quick_check_good(self):
        assert FakeSignalFilter().quick_check(
            {"profit_factor": 2.0, "win_rate": 0.6, "expectancy": 100, "max_drawdown_pct": 10}
        )

    def test_quick_check_bad(self):
        assert not FakeSignalFilter().quick_check({"profit_factor": 0.5})

    def test_quick_check_empty(self):
        assert not FakeSignalFilter().quick_check({})

    def test_evaluate_with_monte_carlo(self):
        mc = MonteCarloResult(
            n_simulations=100,
            n_trades=50,
            prob_profit=0.8,
            p_value=0.01,
            median_return=0.05,
            mean_return=0.04,
            std_return=0.02,
            ci_5th=-0.01,
            ci_95th=0.1,
            median_max_dd=0.1,
            worst_max_dd=0.2,
            ci_95_max_dd=0.15,
            survival_rate=0.95,
        )
        stab = StabilityResult(
            stability_gap=0.15,
            is_performance=0.6,
            os_performance=0.55,
            n_windows=5,
            os_consistency=0.8,
            is_sharpe=2.0,
            os_sharpe=1.8,
            is_os_ratio=0.9,
            passed=True,
        )
        r = FakeSignalFilter().evaluate(
            stability=stab, monte_carlo=mc, metrics={"profit_factor": 1.5, "expectancy": 50}
        )
        assert r.score >= 4


# === 8. core/position_manager.py ===
class TestPositionManagerChaos:
    def test_position_pnl_buy(self):
        p = Position(symbol="X", side="BUY", quantity=0.01, entry_price=2000.0)
        p.update_pnl(2010.0)
        assert p.unrealized_pnl == pytest.approx(0.1)

    def test_position_pnl_sell(self):
        p = Position(symbol="X", side="SELL", quantity=0.01, entry_price=2000.0)
        p.update_pnl(1990.0)
        assert p.unrealized_pnl == pytest.approx(0.1)

    def test_position_zero_qty(self):
        p = Position(symbol="X", side="BUY", quantity=0, entry_price=2000.0)
        p.update_pnl(2010.0)
        assert p.unrealized_pnl == 0.0

    def test_manager_init(self, tmp_path):
        assert PositionManager(data_dir=tmp_path).get_open_positions_count() == 0

    def test_manager_reset(self, tmp_path):
        pm = PositionManager(data_dir=tmp_path)
        pm._positions["X:BUY"] = Position(symbol="X", side="BUY", quantity=0.01, entry_price=2000.0)
        pm.reset()
        assert pm.get_open_positions_count() == 0

    def test_update_prices(self, tmp_path):
        pm = PositionManager(data_dir=tmp_path)
        pm._positions["X:BUY"] = Position(symbol="X", side="BUY", quantity=0.01, entry_price=2000.0)
        pm.update_prices({"X": 2050.0})
        assert pm._positions["X:BUY"].unrealized_pnl == pytest.approx(0.5)

    def test_sync_account(self, tmp_path):
        pm = PositionManager(data_dir=tmp_path)
        pm.sync_account_state(equity=15000)
        assert pm.get_equity() == 15000

    def test_drawdown(self, tmp_path):
        pm = PositionManager(data_dir=tmp_path)
        pm.sync_account_state(equity=9000)
        assert pm.get_drawdown_pct() > 0

    def test_on_fill_wrong_type(self, tmp_path):
        pm = PositionManager(data_dir=tmp_path)
        pm.on_fill(Event())
        assert pm.get_open_positions_count() == 0

    def test_on_close_wrong_type(self, tmp_path):
        PositionManager(data_dir=tmp_path).on_close(Event())

    def test_stress(self, tmp_path):
        pm = PositionManager(data_dir=tmp_path)
        for i in range(200):
            pm._positions[f"S{i}:BUY"] = Position(symbol=f"S{i}", side="BUY", quantity=0.01, entry_price=100.0 + i)
        assert pm.get_open_positions_count() == 200


# === 9. core/production_readiness.py ===
class TestProductionReadinessChaos:
    def test_render_empty(self):
        assert "PRODUCTION READINESS" in ProductionReadiness().render([])

    def test_render_results(self):
        results = [CheckResult("A", True, "ok", True), CheckResult("B", False, "fail", False)]
        text = ProductionReadiness().render(results)
        assert "PASS" in text and "WARN" in text


# === 10. core/reconciler.py ===
class TestReconcilerChaos:
    def test_empty_reconcile(self):
        mock_con = MagicMock()
        mock_con.execute.return_value.fetchall.return_value = []
        r = StateReconciler(mock_con, mt5_module=None)
        result = r.reconcile(mt5_positions=[])
        assert result["ghosts_found"] == 0 and result["orphans_found"] == 0

    def test_ghost_detected(self):
        mock_con = MagicMock()
        mock_con.execute.return_value.fetchall.return_value = [("T1", "X", "BUY", 2000, 0.01, "OPEN")]
        assert StateReconciler(mock_con).reconcile(mt5_positions=[])["ghosts_found"] == 1

    def test_orphan_detected(self):
        mock_con = MagicMock()
        mock_con.execute.return_value.fetchall.return_value = []
        mt5 = [
            {"symbol": "X", "volume": 0.01, "ticket": 123, "profit": 0, "sl": 0, "tp": 0, "price_open": 2000, "time": 0}
        ]
        assert StateReconciler(mock_con).reconcile(mt5_positions=mt5)["orphans_found"] == 1

    def test_history(self):
        mock_con = MagicMock()
        mock_con.execute.return_value.fetchall.return_value = []
        r = StateReconciler(mock_con)
        r.reconcile(mt5_positions=[])
        r.reconcile(mt5_positions=[])
        assert len(r.get_reconciliation_history()) == 2

    def test_mt5_error(self):
        mock_con = MagicMock()
        mock_con.execute.return_value.fetchall.return_value = []
        mock_mt5 = MagicMock()
        mock_mt5.positions_get.side_effect = Exception("err")
        assert StateReconciler(mock_con, mock_mt5).reconcile()["orphans_found"] == 0


# === 11. core/regime_filter.py ===
class TestRegimeFilterChaos:
    def test_insufficient_data(self):
        r = RegimeFilter().detect(
            {"close": [100, 101], "high": [101, 102], "low": [99, 100], "open": [100, 101], "volume": [100, 100]}
        )
        assert r.regime == MarketRegime.RANGING and r.confidence == 0.3

    def test_empty_data(self):
        r = RegimeFilter().detect({"close": [], "high": [], "low": [], "open": [], "volume": []})
        assert r.regime == MarketRegime.RANGING

    def test_trending_up(self):
        prices = [100 + i * 0.5 for i in range(100)]
        data = {
            "close": prices,
            "high": [p + 0.5 for p in prices],
            "low": [p - 0.5 for p in prices],
            "open": prices,
            "volume": [100] * 100,
        }
        r = RegimeFilter().detect(data)
        assert r.regime in (MarketRegime.TRENDING_UP, MarketRegime.HIGH_VOLATILITY)

    def test_position_multiplier_all(self):
        rf = RegimeFilter()
        for regime in MarketRegime:
            m = rf.get_position_multiplier(regime, 0.8)
            assert 0.0 <= m <= 1.0

    def test_crisis_zero(self):
        assert RegimeFilter().get_position_multiplier(MarketRegime.CRISIS) == 0.0

    def test_allowed_strategies(self):
        rf = RegimeFilter()
        for regime in MarketRegime:
            s = rf.get_allowed_strategies(regime)
            assert isinstance(s, list)
            if regime == MarketRegime.CRISIS:
                assert s == []

    def test_shift_risk_insufficient(self):
        assert RegimeFilter().detect_regime_shift_risk([100.0] * 50)["risk_score"] == 0.0

    def test_regime_result_details(self):
        r = RegimeResult(regime=MarketRegime.RANGING, confidence=0.5)
        assert r.details == {}


# === 12. core/rollover_filter.py ===
class TestRolloverFilterChaos:
    def test_clear(self):
        assert RolloverFilter().get_status(datetime(2025, 6, 1, 10, 0, tzinfo=UTC)) == RolloverStatus.CLEAR

    def test_blocked(self):
        assert RolloverFilter().get_status(datetime(2025, 6, 1, 22, 0, tzinfo=UTC)) == RolloverStatus.BLOCKED

    def test_warning(self):
        assert RolloverFilter().get_status(datetime(2025, 6, 1, 21, 47, tzinfo=UTC)) == RolloverStatus.WARNING

    def test_is_blocked(self):
        rf = RolloverFilter()
        assert rf.is_blocked(datetime(2025, 6, 1, 22, 5, tzinfo=UTC))
        assert not rf.is_blocked(datetime(2025, 6, 1, 23, 0, tzinfo=UTC))

    def test_is_warning_not_blocked(self):
        rf = RolloverFilter()
        assert rf.is_warning(datetime(2025, 6, 1, 21, 47, tzinfo=UTC))
        assert not rf.is_warning(datetime(2025, 6, 1, 22, 5, tzinfo=UTC))

    def test_check_result(self):
        c = RolloverFilter().check(datetime(2025, 6, 1, 22, 5, tzinfo=UTC))
        assert c.is_blocked and c.reason != ""

    def test_minutes_until_clear(self):
        m = RolloverFilter().minutes_until_clear(datetime(2025, 6, 1, 22, 0, tzinfo=UTC))
        assert m > 0

    def test_minutes_already_clear(self):
        assert RolloverFilter().minutes_until_clear(datetime(2025, 6, 1, 10, 0, tzinfo=UTC)) == 0.0

    def test_boundary_times(self):
        rf = RolloverFilter()
        assert rf.get_status(datetime(2025, 6, 1, 21, 50, tzinfo=UTC)) == RolloverStatus.BLOCKED
        assert rf.get_status(datetime(2025, 6, 1, 22, 15, tzinfo=UTC)) == RolloverStatus.WARNING
        assert rf.get_status(datetime(2025, 6, 1, 22, 20, tzinfo=UTC)) == RolloverStatus.CLEAR

    def test_custom_window(self):
        rf = RolloverFilter(
            block_start=dtime(10, 0), block_end=dtime(10, 5), warn_start=dtime(9, 55), warn_end=dtime(10, 10)
        )
        assert rf.get_status(datetime(2025, 6, 1, 10, 2, tzinfo=UTC)) == RolloverStatus.BLOCKED

    def test_stress_all_hours(self):
        rf = RolloverFilter()
        for h in range(24):
            for m in range(0, 60, 15):
                assert rf.get_status(datetime(2025, 6, 1, h, m, tzinfo=UTC)) is not None


# === 13. core/structured_trades.py ===
class TestStructuredTradesChaos:
    def test_empty(self):
        r = TradeRecords()
        assert r.count == 0 and r.total_pnl == 0.0 and r.win_rate == 0.0

    def test_add_and_stats(self):
        r = TradeRecords()
        r.add(
            TradeRecord(
                id="1",
                symbol="A",
                side="BUY",
                entry_price=100,
                exit_price=110,
                quantity=1,
                entry_time=0,
                exit_time=1,
                pnl=10,
            )
        )
        r.add(
            TradeRecord(
                id="2",
                symbol="A",
                side="BUY",
                entry_price=100,
                exit_price=95,
                quantity=1,
                entry_time=0,
                exit_time=1,
                pnl=-5,
            )
        )
        assert r.count == 2 and r.total_pnl == 5

    def test_filter(self):
        r = TradeRecords()
        r.add(
            TradeRecord(
                id="1", symbol="A", side="BUY", entry_price=100, exit_price=110, quantity=1, entry_time=0, exit_time=1
            )
        )
        r.add(
            TradeRecord(
                id="2", symbol="B", side="SELL", entry_price=100, exit_price=90, quantity=1, entry_time=0, exit_time=1
            )
        )
        assert len(r.filter(symbol="A")) == 1

    def test_group_by(self):
        r = TradeRecords()
        r.add(
            TradeRecord(
                id="1",
                symbol="A",
                side="BUY",
                entry_price=100,
                exit_price=110,
                quantity=1,
                entry_time=0,
                exit_time=1,
                strategy_id="s1",
            )
        )
        r.add(
            TradeRecord(
                id="2",
                symbol="B",
                side="SELL",
                entry_price=100,
                exit_price=90,
                quantity=1,
                entry_time=0,
                exit_time=1,
                strategy_id="s2",
            )
        )
        g = r.group_by("strategy_id")
        assert len(g["s1"]) == 1 and len(g["s2"]) == 1

    def test_to_json(self, tmp_path):
        r = TradeRecords()
        r.add(
            TradeRecord(
                id="1", symbol="A", side="BUY", entry_price=100, exit_price=110, quantity=1, entry_time=0, exit_time=1
            )
        )
        p = str(tmp_path / "t.json")
        r.to_json(p)
        assert len(json.load(open(p))) == 1

    def test_win_rate(self):
        r = TradeRecords()
        r.add(
            TradeRecord(
                id="1",
                symbol="A",
                side="BUY",
                entry_price=100,
                exit_price=110,
                quantity=1,
                entry_time=0,
                exit_time=1,
                pnl=10,
            )
        )
        r.add(
            TradeRecord(
                id="2",
                symbol="A",
                side="BUY",
                entry_price=100,
                exit_price=95,
                quantity=1,
                entry_time=0,
                exit_time=1,
                pnl=-5,
            )
        )
        assert r.win_rate == 0.5

    def test_stress(self):
        r = TradeRecords()
        for i in range(5000):
            r.add(
                TradeRecord(
                    id=str(i),
                    symbol=f"S{i%10}",
                    side="BUY",
                    entry_price=100,
                    exit_price=100 + i % 10,
                    quantity=0.01,
                    entry_time=i,
                    exit_time=i + 1,
                    pnl=i % 10,
                )
            )
        assert r.count == 5000


# === 14. core/observability.py ===
class TestObservabilityChaos:
    def test_loki_no_url(self):
        sink = LokiSink(url="")
        assert sink(None, "info", {"level": "info"}) == {"level": "info"}

    def test_loki_buffer(self):
        sink = LokiSink(url="http://localhost:3100")
        for _ in range(10):
            sink(None, "info", {"level": "info"})
        assert len(sink._buffer) == 10

    def test_file_writes(self, tmp_path):
        sink = FileSink(path=str(tmp_path / "t.jsonl"))
        sink(None, "info", {"level": "info"})
        assert (tmp_path / "t.jsonl").exists()

    def test_file_rotation(self, tmp_path):
        sink = FileSink(path=str(tmp_path / "t.jsonl"), max_bytes=100)
        for _ in range(50):
            sink(None, "info", {"level": "info", "msg": "x" * 100})
        assert (tmp_path / "t.jsonl.1").exists()

    @patch("graxia.packages.quant_os.core.observability.structlog.configure")
    def test_setup(self, mock_configure):
        setup_logging()
        mock_configure.assert_called_once()


# === 15. core/telegram_notify.py ===
class TestTelegramNotifyChaos:
    def test_load_missing(self):
        assert _load_config(Path("/nonexistent")) == {}

    @patch.dict("os.environ", {}, clear=True)
    @patch("graxia.packages.quant_os.core.telegram_notify._load_config", return_value={})
    def test_requires_creds(self, mock_cfg):
        with pytest.raises(RuntimeError):
            TelegramNotifier(token="", chat_id="")

    @patch("graxia.packages.quant_os.core.telegram_notify.requests.post")
    def test_send_ok(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        assert TelegramNotifier(token="a:b", chat_id="1").send("hi")

    @patch("graxia.packages.quant_os.core.telegram_notify.requests.post")
    def test_send_error(self, mock_post):
        mock_post.side_effect = Exception("net")
        assert not TelegramNotifier(token="a:b", chat_id="1").send("hi")

    @patch("graxia.packages.quant_os.core.telegram_notify.requests.post")
    def test_trade_opened(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        TelegramNotifier(token="a:b", chat_id="1").trade_opened("BUY", 2000, 1990, 2020, 0.85, 0.01, "N")
        mock_post.assert_called_once()

    @patch("graxia.packages.quant_os.core.telegram_notify.requests.post")
    def test_risk_alert(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        TelegramNotifier(token="a:b", chat_id="1").risk_alert("test")
        mock_post.assert_called_once()


# === 16. core/telegram_callback.py ===
class TestTelegramCallbackChaos:
    def test_action_enum(self):
        assert CallbackAction.APPROVE.value == "approve"

    def test_result_dc(self):
        r = CallbackResult(action=CallbackAction.APPROVE, asset="X", direction="BUY")
        assert r.timestamp is not None

    def test_register(self):
        h = TelegramCallbackHandler()
        ps = PendingSignal(
            message_id=1,
            asset="X",
            direction="BUY",
            confidence=0.8,
            entry=2000,
            stop_loss=1990,
            take_profit=2020,
            regime="N",
            strategy_source="s",
            metadata={},
        )
        h.register_signal(ps)
        assert "X:BUY" in h._pending

    def test_clear(self):
        h = TelegramCallbackHandler()
        h._results.append(CallbackResult(action=CallbackAction.SKIP, asset="X", direction="BUY"))
        h.clear_results()
        assert len(h._results) == 0

    @pytest.mark.asyncio
    async def test_invalid_data(self):
        assert await TelegramCallbackHandler().handle_callback({"id": "1", "data": "", "message": {}}) is None

    @pytest.mark.asyncio
    async def test_bad_format(self):
        assert await TelegramCallbackHandler().handle_callback({"id": "1", "data": "bad", "message": {}}) is None

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        assert await TelegramCallbackHandler().handle_callback({"id": "1", "data": "foo:X:BUY", "message": {}}) is None

    @pytest.mark.asyncio
    async def test_expired(self):
        h = TelegramCallbackHandler()
        ps = PendingSignal(
            message_id=1,
            asset="X",
            direction="BUY",
            confidence=0.8,
            entry=2000,
            stop_loss=1990,
            take_profit=2020,
            regime="N",
            strategy_source="s",
            metadata={},
            sent_at=datetime.now(UTC) - timedelta(seconds=400),
        )
        h.register_signal(ps)
        expired = await h.check_expired()
        assert len(expired) == 1

    @pytest.mark.asyncio
    async def test_shutdown(self):
        await TelegramCallbackHandler().shutdown()


# === 17. core/walk_forward_production.py ===
class TestWalkForwardProductionChaos:
    def test_empty(self):
        assert "Walk-Forward" in WalkForwardDashboard().render_html()

    def test_add_render(self):
        d = WalkForwardDashboard()
        d.add_window(accuracy=0.59, oos_accuracy=0.55, window=1)
        d.add_window(accuracy=0.55, window=2, drifted=True)
        assert "DRIFT" in d.render_html()

    def test_save(self, tmp_path):
        d = WalkForwardDashboard()
        d.add_window(accuracy=0.59, window=1)
        p = str(tmp_path / "d.html")
        d.save_html(p)
        assert Path(p).exists()

    def test_stress(self):
        d = WalkForwardDashboard()
        for i in range(100):
            d.add_window(accuracy=0.5 + (i % 20) / 100, window=i + 1)
        assert "Walk-Forward" in d.render_html()


# === 18. core/walk_forward_viz.py ===
class TestWalkForwardVizChaos:
    def test_empty(self):
        assert "No walk-forward data" in WalkForwardViz().render()

    def test_render(self):
        v = WalkForwardViz()
        v.add_window(accuracy=0.59, oos_accuracy=0.55, window=1)
        v.add_window(accuracy=0.55, window=2, drifted=True)
        text = v.render()
        assert "W1" in text and "DRIFT" in text

    def test_bar_edge(self):
        v = WalkForwardViz()
        assert v._bar(0.40, "T").count("#") == 0
        assert v._bar(0.70, "T").count("#") == v.CHART_WIDTH

    def test_markdown(self):
        v = WalkForwardViz()
        v.add_window(accuracy=0.59, window=1)
        assert "Window" in v.to_markdown()


# === 19. core/orchestrator.py ===
class TestOrchestratorChaos:
    @patch("graxia.packages.quant_os.core.orchestrator.MT5Adapter")
    @patch("graxia.packages.quant_os.core.orchestrator.OMS")
    @patch("graxia.packages.quant_os.core.orchestrator.PositionManager")
    @patch("graxia.packages.quant_os.core.orchestrator.TradingLoop")
    @patch("graxia.packages.quant_os.core.orchestrator.PortfolioManagerAgent")
    @patch("graxia.packages.quant_os.core.orchestrator.RiskAuditorAgent")
    def test_init(self, *mocks):
        from graxia.packages.quant_os.core.orchestrator import TradingOrchestrator

        orch = TradingOrchestrator(config=QuantConfig())
        assert orch._running is False

    @patch("graxia.packages.quant_os.core.orchestrator.MT5Adapter")
    @patch("graxia.packages.quant_os.core.orchestrator.OMS")
    @patch("graxia.packages.quant_os.core.orchestrator.PositionManager")
    @patch("graxia.packages.quant_os.core.orchestrator.TradingLoop")
    @patch("graxia.packages.quant_os.core.orchestrator.PortfolioManagerAgent")
    @patch("graxia.packages.quant_os.core.orchestrator.RiskAuditorAgent")
    def test_start_stop(self, *mocks):
        from graxia.packages.quant_os.core.orchestrator import TradingOrchestrator

        orch = TradingOrchestrator()
        orch.start()
        assert orch._running
        orch.stop()
        assert not orch._running

    @patch("graxia.packages.quant_os.core.orchestrator.MT5Adapter")
    @patch("graxia.packages.quant_os.core.orchestrator.OMS")
    @patch("graxia.packages.quant_os.core.orchestrator.PositionManager")
    @patch("graxia.packages.quant_os.core.orchestrator.TradingLoop")
    @patch("graxia.packages.quant_os.core.orchestrator.PortfolioManagerAgent")
    @patch("graxia.packages.quant_os.core.orchestrator.RiskAuditorAgent")
    def test_status(self, *mocks):
        from graxia.packages.quant_os.core.orchestrator import TradingOrchestrator

        s = TradingOrchestrator().get_status()
        assert "running" in s and "trading_mode" in s


# === 20. core/param_sweep.py ===
class TestParamSweepChaos:
    def test_basic(self):
        assert ParamSweep({"a": [1, 2], "b": [3, 4]}).n_combinations == 4

    def test_run(self):
        r = ParamSweep({"a": [1, 2], "b": [3, 4]}).run(lambda p: p["a"] + p["b"], show_progress=False)
        assert r[0][1] >= r[-1][1]

    def test_best(self):
        r = ParamSweep({"a": [1, 2], "b": [3, 4]}).run(lambda p: p["a"] * p["b"], show_progress=False)
        assert r[0][1] == 8

    def test_empty(self):
        assert ParamSweep({"a": [1]}).get_best([]) == ({}, float("-inf"))

    def test_exception(self):
        r = ParamSweep({"a": [1, 2]}).run(lambda p: 1 / 0, show_progress=False)
        assert all(s == float("-inf") for _, s in r)

    def test_summary(self):
        r = ParamSweep({"a": [1, 2, 3]}).run(lambda p: p["a"] ** 2, show_progress=False)
        assert "Parameter Sweep" in ParamSweep({"a": [1]}).summary(r)

    def test_stress(self):
        r = ParamSweep({"a": list(range(50)), "b": list(range(20))}).run(lambda p: p["a"] + p["b"], show_progress=False)
        assert len(r) == 1000


# === 21. core/portfolio_risk.py ===
class TestPortfolioRiskChaos:
    def test_empty(self):
        pr = PortfolioRisk()
        assert pr.total_risk == 0.0
        assert pr.can_add("X", 100)["allowed"]

    def test_add_position(self):
        pr = PortfolioRisk(capital=10000)
        pr.add_position(
            PortfolioPosition(symbol="X", direction="BUY", entry_price=2000, risk_dollars=50, size_lots=0.01)
        )
        assert pr.total_risk == 50.0

    def test_total_risk_block(self):
        pr = PortfolioRisk(capital=10000)
        pr.add_position(
            PortfolioPosition(symbol="X", direction="BUY", entry_price=2000, risk_dollars=450, size_lots=0.01)
        )
        assert not pr.can_add("Y", 100)["allowed"]

    def test_per_symbol_block(self):
        pr = PortfolioRisk(capital=10000)
        pr.add_position(
            PortfolioPosition(symbol="X", direction="BUY", entry_price=2000, risk_dollars=190, size_lots=0.01)
        )
        assert not pr.can_add("X", 20)["allowed"]

    def test_correlated_block(self):
        pr = PortfolioRisk(capital=10000)
        pr.add_position(
            PortfolioPosition(symbol="EURUSD", direction="BUY", entry_price=1.1, risk_dollars=250, size_lots=0.01)
        )
        assert not pr.can_add("GBPUSD", 100)["allowed"]

    def test_daily_loss_block(self):
        pr = PortfolioRisk(capital=10000)
        pr.update_pnl(-250)
        assert not pr.can_add("X", 10)["allowed"]

    def test_drawdown_block(self):
        pr = PortfolioRisk(capital=10000)
        pr.update_pnl(-1100)
        assert not pr.can_add("X", 10)["allowed"]

    def test_update_pnl(self):
        pr = PortfolioRisk(capital=10000)
        pr.update_pnl(100)
        assert pr._current_equity == 10100

    def test_reset_daily(self):
        pr = PortfolioRisk(capital=10000)
        pr.update_pnl(-100)
        pr.reset_daily()
        assert pr._daily_pnl == 0.0

    def test_status(self):
        s = PortfolioRisk().get_status()
        assert "capital" in s and "total_risk" in s

    def test_remove_position(self):
        pr = PortfolioRisk()
        pr.add_position(
            PortfolioPosition(symbol="X", direction="BUY", entry_price=100, risk_dollars=10, size_lots=0.01)
        )
        pr.remove_position("X")
        assert pr.total_risk == 0.0

    def test_stress(self):
        pr = PortfolioRisk(capital=100000)
        for i in range(100):
            pr.add_position(
                PortfolioPosition(symbol=f"S{i}", direction="BUY", entry_price=100, risk_dollars=10, size_lots=0.01)
            )
        assert pr.total_risk == 1000.0


# === 22. core/risk/swap_cost.py ===
class TestSwapCostChaos:
    def test_no_mt5(self):
        with patch.dict("sys.modules", {"MetaTrader5": None}):
            assert get_live_swap_rates() == {}

    def test_estimate_zero_nights(self):
        rates = {"swap_long": -5.0, "swap_short": 2.0, "swap_mode": 0, "point": 0.01, "contract_size": 100}
        assert estimate_overnight_cost("BUY", 0.01, 0, 3, rates) == 0.0

    def test_estimate_zero_rate(self):
        rates = {"swap_long": 0, "swap_short": 0, "swap_mode": 0, "point": 0.01, "contract_size": 100}
        assert estimate_overnight_cost("BUY", 0.01, 5, 3, rates) == 0.0

    @pytest.mark.parametrize("mode", [0, 1, 2, 3, 99])
    def test_estimate_all_modes(self, mode):
        rates = {"swap_long": -5.0, "swap_short": 2.0, "swap_mode": mode, "point": 0.01, "contract_size": 100}
        cost = estimate_overnight_cost("BUY", 0.01, 1, 3, rates)
        assert isinstance(cost, float)

    def test_estimate_sell(self):
        rates = {"swap_long": -5.0, "swap_short": 2.0, "swap_mode": 0, "point": 0.01, "contract_size": 100}
        assert estimate_overnight_cost("SELL", 0.01, 1, 3, rates) != 0.0

    def test_get_swap_cost_for_trade(self):
        rates = {"swap_long": -5.0, "swap_short": 2.0, "swap_mode": 0, "point": 0.01, "contract_size": 100}
        entry = datetime(2025, 6, 1, 10, 0, tzinfo=UTC)
        exit_ = datetime(2025, 6, 3, 10, 0, tzinfo=UTC)
        assert isinstance(get_swap_cost_for_trade(entry, exit_, "BUY", 0.01, rates, 3), float)

    def test_get_swap_cost_zero_rate(self):
        rates = {"swap_long": 0, "swap_short": 0, "swap_mode": 0, "point": 0.01, "contract_size": 100}
        entry = datetime(2025, 6, 1, 10, 0, tzinfo=UTC)
        exit_ = datetime(2025, 6, 3, 10, 0, tzinfo=UTC)
        assert get_swap_cost_for_trade(entry, exit_, "BUY", 0.01, rates, 3) == 0.0

    def test_invalid_mode_trade(self):
        rates = {"swap_long": -5.0, "swap_short": 2.0, "swap_mode": 99, "point": 0.01, "contract_size": 100}
        entry = datetime(2025, 6, 1, 10, 0, tzinfo=UTC)
        exit_ = datetime(2025, 6, 3, 10, 0, tzinfo=UTC)
        assert get_swap_cost_for_trade(entry, exit_, "BUY", 0.01, rates, 3) == 0.0

    def test_stress(self):
        rates = {"swap_long": -5.0, "swap_short": 2.0, "swap_mode": 0, "point": 0.01, "contract_size": 100}
        for i in range(1000):
            estimate_overnight_cost("BUY", 0.01, i % 10, 3, rates)


# === 23. core/agents/researcher.py ===
class TestResearcherChaos:
    def test_init(self):
        a = BullBearResearcherAgent()
        assert a.name == "bull_bear_researcher"

    def test_insufficient_votes(self):
        assert BullBearResearcherAgent().act() is None

    def test_consensus(self):
        a = BullBearResearcherAgent()
        a.observe(SignalEvent(signal_type=SignalType.BUY, confidence=0.8, source="agent1"))
        a.observe(SignalEvent(signal_type=SignalType.BUY, confidence=0.7, source="agent2"))
        result = a.act()
        assert result is not None
        assert result.signal_type == SignalType.BUY

    def test_no_trade_abstentions(self):
        a = BullBearResearcherAgent()
        a.observe(SignalEvent(signal_type=SignalType.NO_TRADE, confidence=0.5, source="agent1"))
        a.observe(SignalEvent(signal_type=SignalType.NO_TRADE, confidence=0.5, source="agent2"))
        assert a.act() is None

    def test_mixed_votes(self):
        a = BullBearResearcherAgent()
        a.observe(SignalEvent(signal_type=SignalType.BUY, confidence=0.8, source="agent1"))
        a.observe(SignalEvent(signal_type=SignalType.SELL, confidence=0.9, source="agent2"))
        a.observe(SignalEvent(signal_type=SignalType.BUY, confidence=0.7, source="agent3"))
        result = a.act()
        assert result is not None
        assert result.signal_type == SignalType.BUY

    def test_ignore_self_source(self):
        a = BullBearResearcherAgent()
        a.observe(SignalEvent(signal_type=SignalType.BUY, confidence=0.8, source="bull_bear_researcher"))
        assert a.act() is None

    def test_reset(self):
        a = BullBearResearcherAgent()
        a.observe(SignalEvent(signal_type=SignalType.BUY, confidence=0.8, source="agent1"))
        a.reset()
        assert a.act() is None

    def test_ignore_non_signal_event(self):
        a = BullBearResearcherAgent()
        a.observe(Event())
        assert a.act() is None
