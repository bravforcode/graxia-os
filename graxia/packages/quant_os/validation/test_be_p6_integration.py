"""Phase BE-P6 integration tests — true locked XAUUSD revalidation."""
from graxia.packages.quant_os.validation.run_matrix import RunMatrix
from graxia.packages.quant_os.validation.revalidation_runner import RevalidationRunner, RunResult
from graxia.packages.quant_os.validation.threshold_evaluator import ThresholdEvaluator
from graxia.packages.quant_os.validation.archive_reasons import ArchiveRecorder
from graxia.packages.quant_os.validation.dataset_protocol import DatasetProtocol


def _good_result():
    return RunResult(
        run_id="R0", trade_count=150, time_segments=15,
        median_segment_expectancy=0.5, expectancy_after_stress_1=0.3,
        profit_factor_after_stress_1=1.2, max_single_trade_pnl_pct=15,
        max_single_month_pnl_pct=25, majority_positive_oos=True,
        oracle_match=True, ledger_integrity=True, data_incidents=0,
        verdict="",
    )


def test_run_matrix_complete():
    runs = RunMatrix.default()
    assert len(runs) == 11
    assert RunMatrix.get_by_id("R0") is not None
    assert RunMatrix.get_by_id("R10") is not None


def test_revalidation_pass():
    runner = RevalidationRunner()
    for i in range(5):
        runner.add_result(_good_result())
    assert runner.final_verdict() == "CONTINUE_TO_SHADOW"


def test_revalidation_insufficient():
    runner = RevalidationRunner()
    r = _good_result()
    r.trade_count = 10
    runner.add_result(r)
    assert runner.final_verdict() == "INSUFFICIENT_SAMPLE"


def test_revalidation_no_edge():
    runner = RevalidationRunner()
    r = _good_result()
    r.median_segment_expectancy = -0.1
    runner.add_result(r)
    assert runner.final_verdict() == "ARCHIVE_NO_EDGE"


def test_threshold_evaluation():
    evaluator = ThresholdEvaluator({"min_trades": 100, "min_profit_factor": 1.1})
    evaluator.evaluate_gate("min_trades", 150, 100, "gte")
    evaluator.evaluate_gate("min_profit_factor", 1.2, 1.1, "gte")
    assert evaluator.all_passed()


def test_archive_recording():
    recorder = ArchiveRecorder()
    recorder.record("XAU_LIQSWEEP", "ARCHIVE_NO_EDGE", "negative expectancy")
    assert recorder.count() == 1
    assert recorder.has_archive("XAU_LIQSWEEP")


def test_dataset_protocol():
    protocol = DatasetProtocol.default_xauusd()
    assert len(protocol.get_splits()) == 3
    ok, issues = protocol.validate_no_overlap()
    assert ok
