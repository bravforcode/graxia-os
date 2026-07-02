"""Tests for untested core/ modules: candle_pipeline, cross_validation,
ml_pipeline, monte_carlo, rolling_metrics, stability, slippage_model, state_store.
"""
import random

import numpy as np
import pytest

from graxia.packages.quant_os.core.candle_pipeline import (
    MovingBlockBootstrapPipeline,
    GaussianNoisePipeline,
)
from graxia.packages.quant_os.core.cross_validation import (
    _embargoed_purged_train_test_split,
    combine_purged_k_fold_cv,
    CPCVResult,
    CPCVFoldResult,
)
from graxia.packages.quant_os.core.ml_pipeline import MLPipeline
from graxia.packages.quant_os.core.monte_carlo import MonteCarloSimulator
from graxia.packages.quant_os.core.rolling_metrics import RollingMetrics
from graxia.packages.quant_os.core.stability import WalkForwardStability
from graxia.packages.quant_os.core.slippage_model import SlippageModel
from graxia.packages.quant_os.core.state_store import SystemState, save, load


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _seed():
    """Deterministic randomness for all tests."""
    random.seed(42)
    np.random.seed(42)


@pytest.fixture
def sample_candles():
    n = 50
    base = 1800.0
    closes = [base + i * 0.5 + random.gauss(0, 0.1) for i in range(n)]
    return {
        "open": [c - 0.1 for c in closes],
        "high": [c + 0.3 for c in closes],
        "low": [c - 0.3 for c in closes],
        "close": closes,
        "volume": [1000 + i for i in range(n)],
    }


@pytest.fixture
def sample_returns():
    return [random.gauss(0.0005, 0.01) for _ in range(100)]


# ===================================================================
# 1. candle_pipeline
# ===================================================================

class TestCandlePipeline:
    def test_bootstrap_regeneration(self, sample_candles):
        pipe = MovingBlockBootstrapPipeline(block_size=5)
        output: dict = {}
        modified = pipe.process(sample_candles, output)

        assert modified is True
        assert "close" in output
        assert "open" in output
        assert "high" in output
        assert "low" in output
        assert len(output["close"]) == len(sample_candles["close"])
        assert output["close"] != sample_candles["close"]
        assert output["open"][1] == output["close"][0]

    def test_gaussian_noise(self, sample_candles):
        pipe = GaussianNoisePipeline(noise_pct=0.001)
        output: dict = {}
        modified = pipe.process(sample_candles, output)

        assert modified is True
        for key in sample_candles:
            assert key in output
            assert len(output[key]) == len(sample_candles[key])
        for orig, noisy in zip(sample_candles["close"], output["close"]):
            assert noisy != pytest.approx(orig, abs=1e-10)
            assert noisy == pytest.approx(orig, rel=0.01)

    def test_bootstrap_short_candles_returns_false(self):
        pipe = MovingBlockBootstrapPipeline(block_size=10)
        candles = {"close": [1.0, 2.0], "high": [2.0, 3.0], "low": [0.5, 1.5]}
        output: dict = {}
        assert pipe.process(candles, output) is False

    def test_get_candles_index(self, sample_candles):
        pipe = MovingBlockBootstrapPipeline()
        result = pipe.get_candles(sample_candles, 0)
        assert result["close"] == sample_candles["close"][0]


# ===================================================================
# 2. cross_validation
# ===================================================================

class TestCrossValidation:
    def test_purged_cv_split(self):
        n_bars = 100
        test_idx = np.array([40, 41, 42, 43, 44])
        purged = 5
        embargo = 5

        train_idx, test_out = _embargoed_purged_train_test_split(
            np.zeros(n_bars), test_idx, n_bars, purged, embargo
        )

        for i in test_idx:
            assert i not in train_idx
        for i in range(max(0, 40 - purged), 40):
            assert i not in train_idx
        for i in range(45, min(n_bars, 45 + embargo)):
            assert i not in train_idx

    def test_embargo_gap(self):
        n_bars = 200
        test_idx = np.array([100, 101, 102])
        purged = 12
        embargo = 12

        train_idx, _ = _embargoed_purged_train_test_split(
            np.zeros(n_bars), test_idx, n_bars, purged, embargo
        )

        for i in range(103, 103 + embargo):
            assert i not in train_idx
        for i in range(100 - purged, 100):
            assert i not in train_idx

    def test_combine_purged_k_fold_cv(self):
        paths = combine_purged_k_fold_cv(
            n_bars=500, n_splits=6, n_test_splits=2,
            purged_size=12, embargo_size=12, random_state=42,
        )
        assert len(paths) == 15
        assert len(paths[0]) == 1

    def test_cpcv_result_distributions(self):
        folds = [
            CPCVFoldResult(fold=0, n_train=100, n_test=20, train_acc=0.9,
                           oos_acc=0.7, n_trades=10, accuracy=0.6, net_pnl=50.0,
                           gross_pnl=80.0, total_cost=30.0, win_rate=0.6,
                           sharpe_ratio=1.5, max_drawdown=-20.0,
                           train_start="2024-01-01", train_end="2024-06-01",
                           test_start="2024-06-01", test_end="2024-12-01"),
            CPCVFoldResult(fold=1, n_train=100, n_test=20, train_acc=0.85,
                           oos_acc=0.65, n_trades=8, accuracy=0.55, net_pnl=-10.0,
                           gross_pnl=60.0, total_cost=70.0, win_rate=0.4,
                           sharpe_ratio=-0.5, max_drawdown=-30.0,
                           train_start="2024-01-01", train_end="2024-06-01",
                           test_start="2024-06-01", test_end="2024-12-01"),
        ]
        result = CPCVResult(n_paths=1, n_folds_per_path=1, purged_size=12,
                            embargo_size=12, folds=folds)
        sharpe_dist = result.sharpe_distribution
        assert sharpe_dist["mean"] == pytest.approx(0.5, abs=0.01)
        pnl_dist = result.net_pnl_distribution
        assert pnl_dist["mean"] == pytest.approx(20.0, abs=0.01)

    def test_cpcv_result_empty_folds(self):
        result = CPCVResult(n_paths=0, n_folds_per_path=0, purged_size=12,
                            embargo_size=12, folds=[])
        assert result.sharpe_distribution["mean"] == 0.0
        assert result.net_pnl_distribution["mean"] == 0.0


# ===================================================================
# 3. ml_pipeline
# ===================================================================

class TestMLPipeline:
    def test_gather_data(self):
        pipe = MLPipeline()
        pipe.gather_start()
        pipe.record_features({"rsi": 65.0, "atr": 0.5})
        pipe.record_label("direction", 1.0)

        assert pipe.data_count == 1
        assert pipe.feature_names == []

        pipe.gather_start()
        pipe.record_features({"rsi": 30.0, "atr": 1.2})
        pipe.record_label("direction", 0.0)
        assert pipe.data_count == 2

    def test_gather_start_auto(self):
        pipe = MLPipeline()
        pipe.record_features({"rsi": 50.0})
        pipe.record_label("direction", 1.0)
        assert pipe.data_count == 1

    def test_gather_end_discards(self):
        pipe = MLPipeline()
        pipe.gather_start()
        pipe.record_features({"rsi": 50.0})
        pipe.gather_end()
        assert pipe.data_count == 0

    def test_export_import_csv(self, tmp_path):
        pipe = MLPipeline()
        for i in range(5):
            pipe.gather_start()
            pipe.record_features({"rsi": float(i), "atr": float(i * 0.1)})
            pipe.record_label("direction", float(i % 2))

        csv_path = str(tmp_path / "data.csv")
        pipe.export_csv(csv_path)

        pipe2 = MLPipeline()
        pipe2.import_csv(csv_path)
        assert pipe2.data_count == 5

    def test_prepare_training_data(self):
        pipe = MLPipeline()
        for i in range(20):
            pipe.gather_start()
            pipe.record_features({"rsi": float(i), "atr": float(i * 0.1)})
            pipe.record_label("direction", float(i % 2))
        pipe._feature_names = ["atr", "rsi"]

        X_train, X_test, y_train, y_test = pipe.prepare_training_data(test_ratio=0.2)
        assert len(X_train) == 16
        assert len(X_test) == 4
        assert len(y_train) == 16
        assert len(y_test) == 4


# ===================================================================
# 4. monte_carlo
# ===================================================================

class TestMonteCarlo:
    def test_shuffle_simulation(self):
        trades = [{"pnl": random.gauss(10, 50)} for _ in range(100)]
        sim = MonteCarloSimulator(seed=42)
        result = sim.run(trades, n_simulations=200, mode="shuffle")

        assert result.n_simulations == 200
        assert result.n_trades == 100
        assert 0.0 <= result.prob_profit <= 1.0
        assert 0.0 <= result.survival_rate <= 1.0
        assert len(result.returns) == 200
        assert len(result.max_drawdowns) == 200
        assert result.mode == "shuffle"

    def test_bootstrap_simulation(self):
        trades = [{"return_pct": random.gauss(0.5, 2.0)} for _ in range(50)]
        sim = MonteCarloSimulator(seed=123)
        result = sim.run(trades, n_simulations=300, mode="bootstrap")

        assert result.n_simulations == 300
        assert result.mode == "bootstrap"
        assert result.ci_5th <= result.median_return <= result.ci_95th

    def test_empty_trades(self):
        sim = MonteCarloSimulator(seed=42)
        result = sim.run([], n_simulations=100)
        assert result.n_trades == 0
        assert result.prob_profit == 0.0

    def test_validate_strategy(self):
        trades = [{"pnl": abs(random.gauss(50, 20)) + 10} for _ in range(100)]
        sim = MonteCarloSimulator(seed=42)
        result = sim.run(trades, n_simulations=500)
        validation = sim.validate_strategy(result)
        assert "p_value_pass" in validation
        assert "survival_pass" in validation
        assert "all_pass" in validation

    def test_pnl_entry_price_calculation(self):
        trades = [{"pnl": 100.0, "entry_price": 1800.0, "quantity": 1.0}]
        sim = MonteCarloSimulator(seed=42)
        result = sim.run(trades, n_simulations=10, mode="shuffle")
        assert result.n_trades == 1


# ===================================================================
# 5. rolling_metrics
# ===================================================================

class TestRollingMetrics:
    def test_rolling_sharpe(self, sample_returns):
        rm = RollingMetrics(sample_returns)
        sharpe = rm.rolling_sharpe(window=20)

        assert len(sharpe) == len(sample_returns)
        assert all(s is None for s in sharpe[:19])
        assert all(s is not None for s in sharpe[19:])

    def test_rolling_max_dd(self, sample_returns):
        rm = RollingMetrics(sample_returns)
        max_dd = rm.rolling_max_drawdown(window=20)

        assert len(max_dd) == len(sample_returns)
        assert all(m is None for m in max_dd[:19])
        for m in max_dd[19:]:
            assert m is not None
            assert 0.0 <= m <= 1.0

    def test_rolling_sortino(self, sample_returns):
        rm = RollingMetrics(sample_returns)
        sortino = rm.rolling_sortino(window=20)

        assert len(sortino) == len(sample_returns)
        assert all(s is None for s in sortino[:19])

    def test_rolling_volatility(self, sample_returns):
        rm = RollingMetrics(sample_returns)
        vol = rm.rolling_volatility(window=20)

        assert len(vol) == len(sample_returns)
        for v in vol[19:]:
            assert v >= 0.0

    def test_to_dict(self, sample_returns):
        rm = RollingMetrics(sample_returns)
        d = rm.to_dict(window=20)
        assert set(d.keys()) == {"sharpe", "sortino", "max_drawdown",
                                  "volatility", "win_rate", "profit_factor"}
        assert len(d["sharpe"]) == len(sample_returns)

    def test_zero_std_returns(self):
        rm = RollingMetrics([0.0] * 30)
        sharpe = rm.rolling_sharpe(window=10)
        # All zeros → std = 0.0 exactly → Sharpe = 0.0
        assert sharpe[-1] == 0.0


# ===================================================================
# 6. stability
# ===================================================================

class TestStability:
    def test_is_os_gap(self):
        wfs = WalkForwardStability(max_gap=0.3, min_os_sharpe=1.5)
        is_res = [{"sharpe": 2.0, "return": 0.05, "trades": 10}] * 3
        os_res = [{"sharpe": 1.8, "return": 0.04, "trades": 8}] * 3

        result = wfs.calculate(is_res, os_res)
        assert result.stability_gap == pytest.approx(0.1, abs=0.01)
        assert result.is_os_ratio == pytest.approx(0.9, abs=0.01)

    def test_stability_score(self):
        wfs = WalkForwardStability(max_gap=0.3, min_os_sharpe=1.5)

        is_res = [{"sharpe": 2.0, "return": 0.05}] * 3
        os_res = [{"sharpe": 1.9, "return": 0.04}] * 3
        result = wfs.calculate(is_res, os_res)
        assert result.passed is True

        is_res2 = [{"sharpe": 2.0, "return": 0.05}] * 3
        os_res2 = [{"sharpe": 0.5, "return": 0.01}] * 3
        result2 = wfs.calculate(is_res2, os_res2)
        assert result2.passed is False

    def test_empty_results(self):
        wfs = WalkForwardStability()
        result = wfs.calculate([], [])
        assert result.stability_gap == 1.0
        assert result.passed is False

    def test_os_consistency(self):
        wfs = WalkForwardStability(max_gap=0.5, min_os_sharpe=0.1)
        os_res = [
            {"sharpe": 1.0, "return": 0.01},
            {"sharpe": 1.0, "return": -0.01},
            {"sharpe": 1.0, "return": 0.02},
            {"sharpe": 1.0, "return": -0.005},
        ]
        is_res = [{"sharpe": 1.0, "return": 0.01}] * 4
        result = wfs.calculate(is_res, os_res)
        assert result.os_consistency == pytest.approx(0.5, abs=0.01)


# ===================================================================
# 7. slippage_model
# ===================================================================

class TestSlippageModel:
    def test_slippage_estimate(self):
        sm = SlippageModel()
        est = sm.estimate(
            symbol="XAUUSD",
            order_size_lots=0.1,
            volatility=0.15,
            session="london",
        )
        assert est.symbol == "XAUUSD"
        assert est.base_slippage_pips == 0.3
        assert est.session_multiplier == 0.8
        assert est.estimated_slippage_pips > 0
        assert est.estimated_slippage_price > 0

    def test_slippage_by_session(self):
        sm = SlippageModel()
        london = sm.estimate("XAUUSD", 0.1, 0.15, "london")
        asian = sm.estimate("XAUUSD", 0.1, 0.15, "asian")
        overlap = sm.estimate("XAUUSD", 0.1, 0.15, "overlap")

        assert asian.estimated_slippage_pips > london.estimated_slippage_pips
        assert overlap.estimated_slippage_pips < london.estimated_slippage_pips

    def test_slippage_by_size(self):
        sm = SlippageModel()
        micro = sm.estimate("XAUUSD", 0.05, 0.15, "london")
        inst = sm.estimate("XAUUSD", 10.0, 0.15, "london")

        assert inst.estimated_slippage_pips > micro.estimated_slippage_pips

    def test_slippage_unknown_symbol(self):
        sm = SlippageModel()
        est = sm.estimate("XYZUSD", 0.1, 0.15, "london")
        assert est.base_slippage_pips == 0.2

    def test_adjust_sl_tp(self):
        sm = SlippageModel()
        adj = sm.adjust_sl_tp(
            entry_price=1800.0, sl_pips=5.0, tp_pips=10.0,
            direction="BUY", symbol="XAUUSD", order_size_lots=0.1,
            volatility=0.15, session="london",
        )
        assert adj["adjusted_sl_pips"] > adj["original_sl_pips"]
        assert adj["adjusted_tp_pips"] < adj["original_tp_pips"]
        assert adj["slippage_cost_usd"] > 0


# ===================================================================
# 8. state_store
# ===================================================================

class TestStateStore:
    def test_save_load_state(self, tmp_path):
        state = SystemState(
            system_state="RUNNING",
            last_heartbeat="2024-06-01T12:00:00Z",
            kill_switch_active=False,
            environment="production",
            asset_states={"XAUUSD": "RUNNING"},
            circuit_breakers={"daily_loss": False},
            positions=[{"symbol": "XAUUSD", "qty": 0.1}],
            daily_pnl=150.0,
            weekly_pnl=500.0,
            peak_equity=10500.0,
        )

        path = tmp_path / "state.json"
        save(state, str(path))

        loaded = load(str(path))
        assert loaded.system_state == "RUNNING"
        assert loaded.environment == "production"
        assert loaded.asset_states == {"XAUUSD": "RUNNING"}
        assert loaded.daily_pnl == 150.0
        assert loaded.positions == [{"symbol": "XAUUSD", "qty": 0.1}]

    def test_atomic_write(self, tmp_path):
        path = tmp_path / "atomic.json"
        s1 = SystemState(system_state="INIT", daily_pnl=0.0)
        save(s1, str(path))

        s2 = SystemState(system_state="RUNNING", daily_pnl=100.0)
        save(s2, str(path))

        loaded = load(str(path))
        assert loaded.system_state == "RUNNING"
        assert loaded.daily_pnl == 100.0

    def test_load_missing_file(self, tmp_path):
        loaded = load(str(tmp_path / "nonexistent.json"))
        assert loaded.system_state == "INIT"
        assert loaded.daily_pnl == 0.0

    def test_load_corrupt_file(self, tmp_path):
        path = tmp_path / "corrupt.json"
        path.write_text("{invalid json", encoding="utf-8")
        loaded = load(str(path))
        assert loaded.system_state == "INIT"

    def test_default_state(self):
        state = SystemState.default("production")
        assert state.system_state == "INIT"
        assert state.environment == "production"
        assert state.kill_switch_active is False

    def test_to_json_roundtrip(self):
        state = SystemState(
            system_state="HALTED",
            asset_states={"BTCUSD": "HALTED"},
            positions=[{"sym": "BTCUSD", "side": "SELL"}],
        )
        json_str = state.to_json()
        restored = SystemState.from_dict(__import__("json").loads(json_str))
        assert restored.system_state == "HALTED"
        assert restored.asset_states == {"BTCUSD": "HALTED"}
