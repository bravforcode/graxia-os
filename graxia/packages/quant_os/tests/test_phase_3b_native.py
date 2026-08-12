import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from graxia.packages.quant_os.core.enums import RegimeType, SignalType
from graxia.packages.quant_os.strategies.base import Signal, Strategy
from graxia.packages.quant_os.validation.cost_scenarios import ALL_SCENARIOS, BASE, STRESS_1
from graxia.packages.quant_os.validation.locked_inputs import LockedInputs
from graxia.packages.quant_os.validation.native_runner import NativeRunner, ValidationResult
from graxia.packages.quant_os.validation.run_config import RunConfig


class _StubStrategy(Strategy):
    """Minimal strategy for testing — buys on down candles, sells on up candles."""

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict[str, Any] | None = None,
        regime: RegimeType | None = None,
        **kwargs,
    ) -> Signal | None:
        close = ohlcv_data.get("close", [])
        open_p = ohlcv_data.get("open", [])
        low = ohlcv_data.get("low", [])
        if len(close) < 3:
            return None

        idx = len(close) - 1
        prev_close = close[idx - 1]
        prev_open = open_p[idx - 1] if idx - 1 < len(open_p) else prev_close
        cur_close = close[idx]

        if cur_close < prev_close and cur_close < prev_open:
            entry = Decimal(str(cur_close))
            sl = Decimal(str(low[idx])) if low[idx] < cur_close else entry * Decimal("0.999")
            tp = entry * Decimal("1.003")
            return Signal(
                id=f"stub_buy_{idx}",
                strategy_id=self.id,
                symbol=symbol,
                signal_type=SignalType.BUY,
                timestamp=kwargs.get("current_time", datetime.now(UTC)),
                entry_price=entry,
                stop_loss=sl,
                take_profit=tp,
                confidence=0.6,
            )

        if cur_close > prev_close and cur_close > prev_open:
            entry = Decimal(str(cur_close))
            sl = entry * Decimal("1.001")
            tp = entry * Decimal("0.997")
            return Signal(
                id=f"stub_sell_{idx}",
                strategy_id=self.id,
                symbol=symbol,
                signal_type=SignalType.SELL,
                timestamp=kwargs.get("current_time", datetime.now(UTC)),
                entry_price=entry,
                stop_loss=sl,
                take_profit=tp,
                confidence=0.6,
            )

        return None

    def required_features(self) -> list[str]:
        return []


def _make_locked_inputs():
    return LockedInputs(
        strategy_source_hash="abc123",
        strategy_param_hash="def456",
        dataset_manifest_hash="ghi789",
        timeframe_alignment_hash="jkl012",
        execution_model_version="1.0.0",
        contract_snapshot_version="1.0.0",
        risk_policy_version="1.0.0",
        event_filter_version="1.0.0",
        random_seed=42,
    )


def _make_data(n=300):
    random.seed(42)
    data = {"open": [], "high": [], "low": [], "close": [], "volume": []}
    price = 2350.0
    for _ in range(n):
        change = random.gauss(0.0005, 0.001)
        o = price
        c = price * (1 + change)
        h = max(o, c) * 1.0005
        l = min(o, c) * 0.9995
        data["open"].append(round(o, 2))
        data["close"].append(round(c, 2))
        data["high"].append(round(h, 2))
        data["low"].append(round(l, 2))
        data["volume"].append(100000)
        price = c
    return data


def _make_timestamps(n=300):
    base = datetime(2025, 1, 1)
    return [base + timedelta(hours=i) for i in range(n)]


class TestLockedInputs:
    def test_master_hash_deterministic(self):
        li = _make_locked_inputs()
        h1 = li.master_hash()
        h2 = li.master_hash()
        assert h1 == h2

    def test_verify_identical(self):
        li1 = _make_locked_inputs()
        li2 = _make_locked_inputs()
        match, mismatches = li1.verify(li2)
        assert match is True
        assert len(mismatches) == 0

    def test_verify_mismatch(self):
        li1 = _make_locked_inputs()
        li2 = LockedInputs(
            strategy_source_hash="DIFFERENT",
            strategy_param_hash="def456",
            dataset_manifest_hash="ghi789",
            timeframe_alignment_hash="jkl012",
            execution_model_version="1.0.0",
            contract_snapshot_version="1.0.0",
            risk_policy_version="1.0.0",
            event_filter_version="1.0.0",
            random_seed=42,
        )
        match, mismatches = li1.verify(li2)
        assert match is False
        assert "strategy_source_hash" in mismatches


class TestCostScenarios:
    def test_all_scenarios_count(self):
        assert len(ALL_SCENARIOS) == 4

    def test_base_scenario(self):
        assert BASE.spread_multiplier == Decimal("1.0")

    def test_stress_multipliers(self):
        assert STRESS_1.spread_multiplier == Decimal("1.5")


class TestRunConfig:
    def test_description(self):
        li = _make_locked_inputs()
        config = RunConfig(run_id="r1", run_type="native", locked_inputs=li)
        desc = config.description()
        assert "native" in desc
        assert "quant_os" in desc


class TestValidationResult:
    def test_compute_hash(self):
        li = _make_locked_inputs()
        config = RunConfig(run_id="r1", run_type="native", locked_inputs=li)
        result = ValidationResult(run_config=config, total_trades=10, win_rate=0.6)
        h = result.compute_hash()
        assert len(h) == 64
        assert h == result.metrics_hash


class TestNativeRunner:
    def test_single_run(self):
        li = _make_locked_inputs()
        config = RunConfig(run_id="t1", run_type="native", locked_inputs=li)
        strategy = _StubStrategy()
        data = _make_data()
        timestamps = _make_timestamps()

        runner = NativeRunner()
        result = runner.run(config, strategy, data, timestamps)

        assert result.error is None
        assert result.total_trades >= 0
        assert result.metrics_hash != ""
        assert len(result.metrics_hash) == 64

    def test_run_all_cost_scenarios(self):
        li = _make_locked_inputs()
        strategy = _StubStrategy()
        data = _make_data()
        timestamps = _make_timestamps()

        runner = NativeRunner()
        results = runner.run_all_cost_scenarios(strategy, data, timestamps, li)

        assert len(results) == 4
        scenario_names = [r.run_config.cost_scenario.name for r in results]
        assert scenario_names == ["base", "stress_1", "stress_2", "stress_3"]
        for r in results:
            assert r.error is None

    def test_results_accumulated(self):
        li = _make_locked_inputs()
        strategy = _StubStrategy()
        data = _make_data()
        timestamps = _make_timestamps()

        runner = NativeRunner()
        config = RunConfig(run_id="a1", run_type="native", locked_inputs=li)
        runner.run(config, strategy, data, timestamps)
        assert len(runner.get_results()) == 1

    def test_cost_attribution_populated(self):
        li = _make_locked_inputs()
        config = RunConfig(run_id="c1", run_type="native", locked_inputs=li)
        strategy = _StubStrategy()
        data = _make_data()
        timestamps = _make_timestamps()

        runner = NativeRunner()
        result = runner.run(config, strategy, data, timestamps)

        assert "spread_cost" in result.cost_attribution
        assert "total_fees" in result.cost_attribution
