from dataclasses import dataclass
from typing import Optional
from graxia.packages.quant_os.validation.exit_gate import ExitGateEvaluator
from graxia.packages.quant_os.validation.regime_analyzer import RegimeSlice, RegimeType, TradeConcentration


# Minimal stubs to avoid native_runner's broken backtest.engine import chain
@dataclass
class _RunConfig:
    run_id: str
    run_type: str

@dataclass
class _ValidationResult:
    run_config: _RunConfig
    total_trades: int = 0
    expectancy: float = 0.0
    error: Optional[str] = None


def _make_result(expectancy=0.01, trades=50, error=None):
    return _ValidationResult(
        run_config=_RunConfig(run_id="r1", run_type="native"),
        total_trades=trades,
        expectancy=expectancy,
        error=error,
    )


class TestExitGate:
    def test_all_passes_continue_research(self):
        evaluator = ExitGateEvaluator()
        evaluator.check_min_trades(50)
        evaluator.check_positive_stressed_expectancy([_make_result(0.01)])
        evaluator.check_no_engine_mismatch("h1", {"vectorbt": "h1", "backtesting_py": "h1"})
        evaluator.check_no_single_trade_dominates(TradeConcentration(100, 0.15, 500, 0.25, 0.3))
        evaluator.check_regime_stability([
            RegimeSlice(RegimeType.TRENDING_UP, 20, 0.6, 200, 10, 5),
            RegimeSlice(RegimeType.RANGING, 15, 0.5, 50, 3.3, 3),
        ])
        evaluator.check_no_parameter_change(True)
        evaluator.check_drawdown_within_limits(12.0)
        evaluator.check_ledger_integrity(True)
        result = evaluator.evaluate()
        assert result.verdict == "CONTINUE_RESEARCH"
        assert result.all_passed is True

    def test_insufficient_trades(self):
        evaluator = ExitGateEvaluator()
        evaluator.check_min_trades(5)
        result = evaluator.evaluate()
        assert result.verdict == "INSUFFICIENT_SAMPLE"

    def test_no_positive_expectancy(self):
        evaluator = ExitGateEvaluator()
        evaluator.check_min_trades(50)
        evaluator.check_positive_stressed_expectancy([_make_result(-0.01)])
        result = evaluator.evaluate()
        assert result.verdict == "ARCHIVE_NO_EDGE"

    def test_single_trade_dominates(self):
        evaluator = ExitGateEvaluator()
        evaluator.check_min_trades(50)
        evaluator.check_positive_stressed_expectancy([_make_result(0.01)])
        evaluator.check_no_single_trade_dominates(TradeConcentration(1000, 0.50, 500, 0.25, 0.6))
        result = evaluator.evaluate()
        assert result.verdict == "ARCHIVE_NO_EDGE"

    def test_fingerprint_deterministic(self):
        evaluator = ExitGateEvaluator()
        evaluator.check_min_trades(50)
        r1 = evaluator.evaluate()
        evaluator2 = ExitGateEvaluator()
        evaluator2.check_min_trades(50)
        r2 = evaluator2.evaluate()
        assert r1.fingerprint() == r2.fingerprint()

    def test_to_dict(self):
        evaluator = ExitGateEvaluator()
        evaluator.check_min_trades(50)
        result = evaluator.evaluate()
        d = result.to_dict()
        assert "checks" in d
        assert "verdict" in d
