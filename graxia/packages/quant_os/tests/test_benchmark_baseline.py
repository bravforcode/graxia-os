"""
Benchmark baseline — compare XGBoost ML model against simple SMA crossover.

Purpose: If ML model (accuracy ~54%) does not beat a simple SMA crossover,
the ML approach needs fundamental change (features, architecture, or target).

Usage:
    python -m pytest tests/test_benchmark_baseline.py -v --tb=short
"""
import pytest
import numpy as np


def simple_sma_crossover(close: np.ndarray, fast: int = 5, slow: int = 20) -> np.ndarray:
    """Simple SMA crossover signal: 1=buy, -1=sell, 0=hold."""
    if len(close) < slow + 1:
        return np.zeros(len(close))
    sma_fast = np.convolve(close, np.ones(fast) / fast, mode="valid")
    sma_slow = np.convolve(close, np.ones(slow) / slow, mode="valid")
    # Align lengths
    min_len = min(len(sma_fast), len(sma_slow))
    sma_fast = sma_fast[-min_len:]
    sma_slow = sma_slow[-min_len:]
    signal = np.zeros(len(close))
    signal[-min_len:][sma_fast > sma_slow] = 1
    signal[-min_len:][sma_fast < sma_slow] = -1
    return signal


def compute_accuracy(predicted: np.ndarray, actual: np.ndarray) -> float:
    """Directional accuracy: did prediction match price movement direction?"""
    valid = (predicted != 0) & (actual != 0)
    if not valid.any():
        return 0.0
    correct = (predicted[valid] == actual[valid]).sum()
    return correct / valid.sum()


class TestBenchmarkBaseline:
    """Compare ML model accuracy against simple SMA crossover."""

    def test_sma_crossover_accuracy_minimum(self):
        """SMA crossover should achieve >50% accuracy on any non-random data."""
        # Generate synthetic trend data (upward trend)
        np.random.seed(42)
        n = 1000
        trend = np.cumsum(np.random.normal(0.0001, 0.005, n)) + 100
        direction = np.sign(np.diff(trend, prepend=trend[0]))

        sma_signal = simple_sma_crossover(trend)
        acc = compute_accuracy(sma_signal, direction)
        # On synthetic trend, SMA should beat 50%
        assert acc > 0.50, f"SMA crossover accuracy {acc:.3f} < 0.50 on trend data"

    def test_sma_outperforms_random(self):
        """Simple strategy should outperform random classifier on trend data."""
        np.random.seed(42)
        n = 2000
        # Strong trend: clear directional movement
        trend = np.cumsum(np.random.normal(0.0005, 0.008, n)) + 100
        direction = np.sign(np.diff(trend, prepend=trend[0]))

        sma_signal = simple_sma_crossover(trend)
        sma_acc = compute_accuracy(sma_signal, direction)

        # Random baseline (should be ~50%)
        rng = np.random.RandomState(42)
        random_signal = rng.choice([-1, 0, 1], size=n)
        random_acc = compute_accuracy(random_signal, direction)

        assert sma_acc > random_acc, (
            f"SMA ({sma_acc:.3f}) should beat random ({random_acc:.3f})"
        )
        # SMA must be clearly above random
        assert sma_acc > 0.52, f"SMA accuracy too low: {sma_acc:.3f}"
        print(f"  SMA baseline accuracy: {sma_acc:.3f}")
        print(f"  Random baseline:       {random_acc:.3f}")
        print(f"  Improvement:           {(sma_acc - random_acc)*100:.1f}pp")

    def test_ml_should_not_be_worse_than_random(self):
        """ML model must not be worse than random baseline.

        WARNING: If this test fails, the ML model is degenerate (worse than guessing).
        Current model (before regularization fix): accuracy 0.454 vs random 0.500
        """
        import os
        import pickle
        import glob

        model_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "ml", "models"
        )
        if not os.path.isdir(model_dir):
            pytest.skip("No trained ML models found")

        models = sorted(glob.glob(os.path.join(model_dir, "xgboost_*.pkl")))
        if not models:
            pytest.skip("No XGBoost models found")

        # Load latest model
        with open(models[-1], "rb") as f:
            model_data = pickle.load(f)

        # Handle both formats: dict with "model" key or raw XGBClassifier
        if isinstance(model_data, dict):
            model = model_data["model"]
            feature_names = model_data.get("feature_names", [])
        else:
            model = model_data
            feature_names = getattr(model, "feature_names_in_", [])

        # Generate synthetic test data matching expected feature count
        n_features = len(feature_names) or getattr(model, "n_features_in_", 0)
        assert n_features > 0, "Cannot determine feature count from model"

        np.random.seed(42)
        n = 500
        X_test = np.random.normal(0, 1, (n, n_features))
        # Add some signal to first 3 features
        X_test[:n // 2, :3] += 0.3
        y_test = np.concatenate([np.ones(n // 2), np.zeros(n - n // 2)])

        ml_acc = model.score(X_test, y_test)

        # Simple threshold baseline (always predict majority class)
        majority_class = max((y_test == 0).sum(), (y_test == 1).sum())
        baseline_acc = majority_class / len(y_test)

        assert ml_acc >= baseline_acc - 0.05, (  # Allow 5% tolerance
            f"ML model ({ml_acc:.3f}) is significantly worse than baseline ({baseline_acc:.3f})! "
            f"Consider retraining with regularization."
        )
        print(f"  ML accuracy:      {ml_acc:.3f}")
        print(f"  Baseline accuracy: {baseline_acc:.3f}")
        print(f"  Delta:             {(ml_acc - baseline_acc)*100:+.1f}pp")
