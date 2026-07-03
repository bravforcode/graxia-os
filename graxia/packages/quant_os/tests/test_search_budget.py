"""Tests for SearchBudgetTracker — strategy search budget tracking."""

from graxia.packages.quant_os.validation.search_budget import (
    SearchBudgetTracker,
)


def test_record_trial():
    """Recording a trial increments count."""
    tracker = SearchBudgetTracker()
    tracker.record_trial("s1", {"ema": 20}, is_sharpe=1.5)
    assert tracker.get_trial_count("s1") == 1


def test_multiple_trials():
    """Multiple trials for same strategy counted correctly."""
    tracker = SearchBudgetTracker()
    for i in range(50):
        tracker.record_trial("s1", {"ema": 20 + i}, is_sharpe=1.0 + i * 0.01)
    assert tracker.get_trial_count("s1") == 50


def test_total_trials():
    """get_total_trials sums across strategies."""
    tracker = SearchBudgetTracker()
    tracker.record_trial("s1", {}, is_sharpe=1.0)
    tracker.record_trial("s2", {}, is_sharpe=1.0)
    assert tracker.get_total_trials() == 2


def test_within_budget():
    """is_within_budget respects max_trials."""
    tracker = SearchBudgetTracker(max_trials=5)
    for _ in range(5):
        tracker.record_trial("s1", {}, is_sharpe=1.0)
    assert tracker.is_within_budget("s1") is True
    tracker.record_trial("s1", {}, is_sharpe=1.0)
    assert tracker.is_within_budget("s1") is False


def test_get_deflated_sharpe():
    """get_deflated_sharpe uses recorded trial count."""
    tracker = SearchBudgetTracker()
    for i in range(100):
        tracker.record_trial("s1", {"x": i}, is_sharpe=1.5)
    result = tracker.get_deflated_sharpe("s1", observed_sharpe=1.5, n_observations=5000)
    assert result.observed_sharpe == 1.5
    # Should have used n_trials=100
    assert result.multiple_testing_adjustment > 0


def test_summary():
    """summary returns correct structure."""
    tracker = SearchBudgetTracker(max_trials=100)
    tracker.record_trial("s1", {"a": 1}, is_sharpe=1.5, oos_sharpe=1.2)
    tracker.record_trial("s1", {"a": 2}, is_sharpe=1.8)
    s = tracker.summary("s1")
    assert s.strategy_id == "s1"
    assert s.total_trials == 2
    assert s.within_budget is True
    assert s.best_is_sharpe == 1.8


def test_summary_best_oos():
    """summary reports best OOS sharpe when provided."""
    tracker = SearchBudgetTracker()
    tracker.record_trial("s1", {"a": 1}, is_sharpe=1.5, oos_sharpe=1.2)
    tracker.record_trial("s1", {"a": 2}, is_sharpe=1.8, oos_sharpe=1.6)
    s = tracker.summary("s1")
    assert s.best_oos_sharpe == 1.6


def test_summary_no_oos():
    """summary returns None for best_oos_sharpe when no OOS recorded."""
    tracker = SearchBudgetTracker()
    tracker.record_trial("s1", {"a": 1}, is_sharpe=1.5)
    s = tracker.summary("s1")
    assert s.best_oos_sharpe is None


def test_summary_unique_param_sets():
    """summary counts unique parameter sets."""
    tracker = SearchBudgetTracker()
    tracker.record_trial("s1", {"a": 1}, is_sharpe=1.0)
    tracker.record_trial("s1", {"a": 1}, is_sharpe=1.0)  # duplicate params
    tracker.record_trial("s1", {"a": 2}, is_sharpe=1.0)  # different params
    s = tracker.summary("s1")
    assert s.unique_param_sets == 2


def test_reset():
    """reset clears trials for a specific strategy."""
    tracker = SearchBudgetTracker()
    tracker.record_trial("s1", {}, is_sharpe=1.0)
    tracker.reset("s1")
    assert tracker.get_trial_count("s1") == 0


def test_reset_all():
    """reset() with no arg clears all."""
    tracker = SearchBudgetTracker()
    tracker.record_trial("s1", {}, is_sharpe=1.0)
    tracker.record_trial("s2", {}, is_sharpe=1.0)
    tracker.reset()
    assert tracker.get_total_trials() == 0


def test_reset_nonexistent():
    """Reset on non-existent strategy does not error."""
    tracker = SearchBudgetTracker()
    tracker.reset("nonexistent")  # should not raise


def test_trial_count_unknown_strategy():
    """get_trial_count returns 0 for unknown strategy."""
    tracker = SearchBudgetTracker()
    assert tracker.get_trial_count("unknown") == 0


def test_within_budget_unknown_strategy():
    """is_within_budget returns True for unknown strategy (0 <= max)."""
    tracker = SearchBudgetTracker(max_trials=5)
    assert tracker.is_within_budget("unknown") is True


def test_get_deflated_sharpe_no_trials():
    """get_deflated_sharpe with no trials falls back to n_trials=1."""
    tracker = SearchBudgetTracker()
    result = tracker.get_deflated_sharpe("unknown", observed_sharpe=2.0, n_observations=5000)
    assert result.observed_sharpe == 2.0


def test_summary_unknown_strategy():
    """summary for unknown strategy returns zero counts."""
    tracker = SearchBudgetTracker(max_trials=100)
    s = tracker.summary("unknown")
    assert s.strategy_id == "unknown"
    assert s.total_trials == 0
    assert s.within_budget is True
    assert s.best_is_sharpe == 0.0
    assert s.best_oos_sharpe is None


def test_trial_record_dataclass():
    """TrialRecord has expected fields."""
    tracker = SearchBudgetTracker()
    tracker.record_trial("s1", {"x": 1}, is_sharpe=1.5, oos_sharpe=1.2)
    # Access internal records
    records = tracker._trials["s1"]
    assert len(records) == 1
    r = records[0]
    assert r.strategy_id == "s1"
    assert r.params == {"x": 1}
    assert r.in_sample_sharpe == 1.5
    assert r.out_of_sample_sharpe == 1.2
    assert r.timestamp  # not empty


def test_params_are_copied():
    """record_trial copies params dict (no mutation)."""
    tracker = SearchBudgetTracker()
    original = {"x": 1}
    tracker.record_trial("s1", original, is_sharpe=1.0)
    original["x"] = 999
    assert tracker._trials["s1"][0].params == {"x": 1}


def test_multiple_strategies():
    """Multiple strategies tracked independently."""
    tracker = SearchBudgetTracker(max_trials=10)
    for i in range(5):
        tracker.record_trial("s1", {"a": i}, is_sharpe=1.0)
    for i in range(3):
        tracker.record_trial("s2", {"b": i}, is_sharpe=2.0)
    assert tracker.get_trial_count("s1") == 5
    assert tracker.get_trial_count("s2") == 3
    assert tracker.get_total_trials() == 8
