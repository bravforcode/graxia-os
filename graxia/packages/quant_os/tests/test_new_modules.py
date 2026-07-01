"""
Tests for new modules: Regime Filter, Monte Carlo, Signal Filter, Stability
"""

import pytest
import random
random.seed(42)

from quant_os.core.regime_filter import RegimeFilter, MarketRegime
from quant_os.core.monte_carlo import MonteCarloSimulator
from quant_os.core.stability import WalkForwardStability
from quant_os.core.signal_filter import FakeSignalFilter
from quant_os.core.dashboard import Dashboard, DashboardMetrics


def generate_mock_data(bars=200, trend=0.001):
    """Generate mock OHLCV data"""
    data = {"open": [], "high": [], "low": [], "close": [], "volume": []}
    price = 2350.0

    for _ in range(bars):
        change = random.gauss(trend, 0.001)
        o = price
        c = price * (1 + change)
        h = max(o, c) * (1 + abs(random.gauss(0, 0.0005)))
        l = min(o, c) * (1 - abs(random.gauss(0, 0.0005)))
        v = 100000 * (1 + random.gauss(0, 0.3))

        data["open"].append(round(o, 2))
        data["close"].append(round(c, 2))
        data["high"].append(round(h, 2))
        data["low"].append(round(l, 2))
        data["volume"].append(max(0, v))

        price = c

    return data


class TestRegimeFilter:
    def test_init(self):
        rf = RegimeFilter()
        assert rf.adx_trend_threshold == 25.0

    def test_detect_returns_regime(self):
        rf = RegimeFilter()
        data = generate_mock_data(200)
        result = rf.detect(data)
        assert result.regime in MarketRegime
        assert 0 <= result.confidence <= 1

    def test_insufficient_data(self):
        rf = RegimeFilter()
        data = generate_mock_data(10)
        result = rf.detect(data)
        assert result.regime == MarketRegime.RANGING

    def test_trending_data(self):
        rf = RegimeFilter()
        data = generate_mock_data(200, trend=0.005)  # Strong uptrend
        result = rf.detect(data)
        # Should detect some form of trend
        assert result.regime in [MarketRegime.TRENDING_UP, MarketRegime.HIGH_VOLATILITY, MarketRegime.RANGING]

    def test_get_allowed_strategies(self):
        rf = RegimeFilter()
        strategies = rf.get_allowed_strategies(MarketRegime.TRENDING_UP)
        assert "ema_cross" in strategies
        assert "multi_tf_align" in strategies

    def test_crisis_no_trading(self):
        rf = RegimeFilter()
        strategies = rf.get_allowed_strategies(MarketRegime.CRISIS)
        assert len(strategies) == 0


class TestMonteCarlo:
    def test_init(self):
        mc = MonteCarloSimulator(seed=42)
        assert mc.seed == 42

    def test_run_with_trades(self):
        mc = MonteCarloSimulator(seed=42)
        trades = [{"pnl": random.uniform(-100, 200)} for _ in range(50)]
        result = mc.run(trades, n_simulations=1000)

        assert result.n_simulations == 1000
        assert result.n_trades == 50
        assert 0 <= result.prob_profit <= 1
        assert 0 <= result.p_value <= 1
        assert result.survival_rate >= 0

    def test_run_empty_trades(self):
        mc = MonteCarloSimulator(seed=42)
        result = mc.run([], n_simulations=1000)
        assert result.n_trades == 0
        assert result.prob_profit == 0

    def test_validate_strategy(self):
        mc = MonteCarloSimulator(seed=42)
        trades = [{"pnl": random.uniform(-50, 150)} for _ in range(100)]
        result = mc.run(trades, n_simulations=5000)
        validation = mc.validate_strategy(result)

        assert "p_value_pass" in validation
        assert "survival_pass" in validation
        assert "all_pass" in validation


class TestWalkForwardStability:
    def test_init(self):
        wf = WalkForwardStability()
        assert wf.max_gap == 0.3

    def test_calculate(self):
        wf = WalkForwardStability()
        is_results = [{"sharpe": 2.0, "return": 0.15}, {"sharpe": 1.8, "return": 0.12}]
        os_results = [{"sharpe": 1.5, "return": 0.10}, {"sharpe": 1.2, "return": 0.08}]

        result = wf.calculate(is_results, os_results)

        assert result.n_windows == 2
        assert result.is_sharpe > 0
        assert result.os_sharpe > 0
        assert 0 <= result.stability_gap <= 1

    def test_empty_results(self):
        wf = WalkForwardStability()
        result = wf.calculate([], [])
        assert result.passed == False


class TestFakeSignalFilter:
    def test_init(self):
        f = FakeSignalFilter()
        assert f.max_stability_gap == 0.3

    def test_evaluate_all_pass(self):
        f = FakeSignalFilter()

        from quant_os.core.stability import StabilityResult
        from quant_os.core.monte_carlo import MonteCarloResult

        stability = StabilityResult(
            stability_gap=0.2,
            is_performance=0.15,
            os_performance=0.12,
            n_windows=3,
            os_consistency=0.8,
            is_sharpe=2.0,
            os_sharpe=1.8,
            is_os_ratio=0.9,
            passed=True,
        )

        mc = MonteCarloResult(
            n_simulations=1000,
            n_trades=50,
            prob_profit=0.97,
            p_value=0.97,
            median_return=0.10,
            mean_return=0.08,
            std_return=0.05,
            ci_5th=-0.05,
            ci_95th=0.20,
            median_max_dd=0.08,
            worst_max_dd=0.15,
            ci_95_max_dd=0.12,
            survival_rate=0.95,
        )

        metrics = {
            "profit_factor": 1.8,
            "expectancy": 50.0,
        }

        result = f.evaluate(stability, mc, metrics)
        assert result.score >= 5
        assert result.grade in ["S", "A"]

    def test_quick_check(self):
        f = FakeSignalFilter()

        # Good metrics
        assert f.quick_check({"profit_factor": 1.5, "win_rate": 0.55, "expectancy": 30, "max_drawdown_pct": 8}) == True

        # Bad metrics
        assert f.quick_check({"profit_factor": 0.8, "win_rate": 0.3, "expectancy": -50, "max_drawdown_pct": 30}) == False


class TestDashboard:
    def test_init(self):
        d = Dashboard()
        assert len(d.history) == 0

    def test_update(self):
        d = Dashboard()
        metrics = DashboardMetrics(
            timestamp=__import__("datetime").datetime.utcnow(),
            balance=10000,
            equity=10100,
            unrealized_pnl=100,
            daily_pnl=50,
            total_pnl=100,
            drawdown_pct=2.0,
            max_drawdown_pct=5.0,
            daily_loss_pct=0.5,
            open_positions=1,
            total_trades=10,
            win_rate=0.6,
            profit_factor=1.5,
            sharpe_ratio=1.2,
            active_strategies=10,
            total_strategies=13,
            top_strategy="mtm",
            strategy_scores={"mtm": 80, "mrb": 60},
            current_regime="TRENDING_UP",
            regime_confidence=0.8,
        )

        d.update(metrics)
        assert len(d.history) == 1

    def test_render(self):
        d = Dashboard()
        metrics = DashboardMetrics(
            timestamp=__import__("datetime").datetime.utcnow(),
            balance=10000,
            equity=10100,
            unrealized_pnl=100,
            daily_pnl=50,
            total_pnl=100,
            drawdown_pct=2.0,
            max_drawdown_pct=5.0,
            daily_loss_pct=0.5,
            open_positions=1,
            total_trades=10,
            win_rate=0.6,
            profit_factor=1.5,
            sharpe_ratio=1.2,
            active_strategies=10,
            total_strategies=13,
            top_strategy="mtm",
            strategy_scores={"mtm": 80, "mrb": 60},
            current_regime="TRENDING_UP",
            regime_confidence=0.8,
        )

        output = d.render(metrics)
        assert "GOLD BOT" in output
        assert "Balance" in output
        assert "TRENDING_UP" in output
