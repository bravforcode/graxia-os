"""Tests for revalidation runner."""
from graxia.packages.quant_os.validation.revalidation_runner import RevalidationRunner, RunResult


def _good_result():
    return RunResult(
        run_id="R0", trade_count=150, time_segments=15,
        median_segment_expectancy=0.5, expectancy_after_stress_1=0.3,
        profit_factor_after_stress_1=1.2, max_single_trade_pnl_pct=15,
        max_single_month_pnl_pct=25, majority_positive_oos=True,
        oracle_match=True, ledger_integrity=True, data_incidents=0,
        verdict="",
    )


def test_runner_creates():
    runner = RevalidationRunner()
    assert runner is not None


def test_runner_evaluate_pass():
    runner = RevalidationRunner()
    result = _good_result()
    verdict = runner.add_result(result)
    assert verdict == "CONTINUE_TO_SHADOW"


def test_runner_evaluate_insufficient_trades():
    runner = RevalidationRunner()
    result = _good_result()
    result.trade_count = 10  # below 100
    verdict = runner.add_result(result)
    assert verdict == "INSUFFICIENT_SAMPLE"


def test_runner_evaluate_no_edge():
    runner = RevalidationRunner()
    result = _good_result()
    result.median_segment_expectancy = -0.1
    verdict = runner.add_result(result)
    assert verdict == "ARCHIVE_NO_EDGE"


def test_runner_final_verdict():
    runner = RevalidationRunner()
    for i in range(5):
        runner.add_result(_good_result())
    assert runner.final_verdict() == "CONTINUE_TO_SHADOW"
