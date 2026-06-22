"""Tests for threshold evaluator."""
from graxia.packages.quant_os.validation.threshold_evaluator import ThresholdEvaluator


def test_evaluator_creates():
    evaluator = ThresholdEvaluator()
    assert evaluator is not None


def test_evaluator_gte_pass():
    evaluator = ThresholdEvaluator()
    result = evaluator.evaluate_gate("min_trades", 150, 100, "gte")
    assert result.passed


def test_evaluator_gte_fail():
    evaluator = ThresholdEvaluator()
    result = evaluator.evaluate_gate("min_trades", 50, 100, "gte")
    assert not result.passed


def test_evaluator_lte_pass():
    evaluator = ThresholdEvaluator()
    result = evaluator.evaluate_gate("max_dd", 5.0, 10.0, "lte")
    assert result.passed


def test_evaluator_all_passed():
    evaluator = ThresholdEvaluator()
    evaluator.evaluate_gate("a", 10, 5, "gte")
    evaluator.evaluate_gate("b", 3, 5, "lte")
    assert evaluator.all_passed()


def test_evaluator_summary():
    evaluator = ThresholdEvaluator()
    evaluator.evaluate_gate("a", 10, 5, "gte")
    evaluator.evaluate_gate("b", 1, 5, "gte")
    s = evaluator.summary()
    assert s["total"] == 2
    assert s["passed"] == 1
    assert s["failed"] == 1
    assert not s["all_passed"]
