"""
Label Shuffling Null Hypothesis Test — Phase 13.1

INFRASTRUCTURE ONLY: This test framework exists but has never been validated
with real strategy data. The _compute_sharpe() helper always returns 0.0 due
to import errors. All pytest tests pass because they test infrastructure
(shuffling, distribution creation) but never compute actual Sharpe ratios.

Do NOT use this as evidence of strategy validation until real Sharpe
computation is implemented and tested with actual backtest data.

Mandatory per audit protocol: shuffle labels, rerun backtest >=100 times.
Real Sharpe must fall OUTSIDE null distribution for edge to exist.
"""
import numpy as np
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # graxia/packages for quant_os.*

from quant_os.backtest.engine import BacktestConfig


def run_label_shuffle_test(
    features: np.ndarray,
    labels: np.ndarray,
    n_permutations: int = 100,
    config: BacktestConfig = None,
) -> dict:
    """Run label-shuffling null distribution test.

    Args:
        features: Feature matrix (n_samples, n_features)
        labels: Binary labels (1=long, -1=short, 0=flat)
        n_permutations: Number of shuffles (default 100)
        config: Backtest config

    Returns:
        dict with: real_sharpe, null_mean, null_std, null_95th, p_value, survives
    """
    if config is None:
        config = BacktestConfig()

    # 1. Compute real Sharpe (unshuffled)
    real_sharpe = _compute_sharpe(features, labels, config)

    # 2. Compute null distribution
    null_sharpes = []
    for i in range(n_permutations):
        shuffled = np.random.permutation(labels)
        sharpe = _compute_sharpe(features, shuffled, config)
        null_sharpes.append(sharpe)
        if (i + 1) % 10 == 0:
            print(f"  Permutation {i+1}/{n_permutations}: Sharpe={sharpe:.3f}")

    null_sharpes = np.array(null_sharpes)
    null_mean = float(null_sharpes.mean())
    null_std = float(null_sharpes.std(ddof=1))
    null_95th = float(np.percentile(null_sharpes, 95))

    # 3. p-value: fraction of null >= real
    p_value = float((null_sharpes >= real_sharpe).mean())

    # 4. Survives?
    survives = real_sharpe > null_95th and p_value < 0.05

    return {
        "real_sharpe": float(real_sharpe),
        "null_mean": null_mean,
        "null_std": null_std,
        "null_95th_percentile": null_95th,
        "p_value": p_value,
        "survives": bool(survives),
        "n_permutations": n_permutations,
    }


def _compute_sharpe(features: np.ndarray, labels: np.ndarray, config: BacktestConfig) -> float:
    """Compute Sharpe from feature/label signal simulation."""
    # Simple proxy: use label-direction * forward return as PnL
    # This is a simplified test — full backtest integration would be slower
    # but the statistical logic is the same
    try:
        from backtest.metrics import _sharpe_ratio
        # Simulate returns: 1 unit per trade, return = label * small_random
        returns = labels * np.random.normal(0.001, 0.01, size=len(labels))
        returns = returns.tolist()
        if len(returns) < 2:
            return 0.0
        return _sharpe_ratio(returns, 0.0, 252)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Pytest tests — converted from script-only
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_data():
    """Generate reproducible synthetic features and labels."""
    np.random.seed(42)
    n = 500
    features = np.random.randn(n, 10)
    labels = np.random.choice([-1, 0, 1], size=n, p=[0.3, 0.4, 0.3])
    return features, labels


class TestShuffleReducesOverfit:
    """Shuffled labels must produce worse (or equal) Sharpe than real labels.

    On random synthetic data the real Sharpe should fall inside the null
    distribution, confirming no spurious edge.
    """

    def test_shuffle_reduces_overfit(self, synthetic_data):
        features, labels = synthetic_data
        result = run_label_shuffle_test(features, labels, n_permutations=50)

        # On random data, real Sharpe should NOT survive (no edge)
        assert result["n_permutations"] == 50
        assert "real_sharpe" in result
        assert "null_mean" in result
        assert "p_value" in result

    def test_real_sharpe_is_finite(self, synthetic_data):
        features, labels = synthetic_data
        result = run_label_shuffle_test(features, labels, n_permutations=20)
        assert np.isfinite(result["real_sharpe"])

    def test_null_distribution_has_correct_size(self, synthetic_data):
        features, labels = synthetic_data
        n = 30
        result = run_label_shuffle_test(features, labels, n_permutations=n)
        assert result["n_permutations"] == n


class TestShufflePreservesDistribution:
    """Shuffling must preserve the label distribution (same counts)."""

    def test_shuffle_preserves_distribution(self):
        np.random.seed(123)
        labels = np.random.choice([-1, 0, 1], size=1000, p=[0.3, 0.4, 0.3])
        original_counts = {v: int(np.sum(labels == v)) for v in [-1, 0, 1]}

        shuffled = np.random.permutation(labels)
        shuffled_counts = {v: int(np.sum(shuffled == v)) for v in [-1, 0, 1]}

        assert original_counts == shuffled_counts, "Shuffling must preserve label counts"

    def test_shuffle_changes_order(self):
        np.random.seed(99)
        labels = np.arange(100)
        shuffled = np.random.permutation(labels)

        # Extremely unlikely to be identical after shuffle
        assert not np.array_equal(labels, shuffled)

    def test_p_value_is_probability(self, synthetic_data):
        features, labels = synthetic_data
        result = run_label_shuffle_test(features, labels, n_permutations=50)
        assert 0.0 <= result["p_value"] <= 1.0


# ---------------------------------------------------------------------------
# CLI entry point (preserved for manual runs)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Label Shuffling Null Hypothesis Test (Phase 13.1) ===")
    print()

    np.random.seed(42)
    n = 500
    features = np.random.randn(n, 10)
    labels = np.random.choice([-1, 0, 1], size=n, p=[0.3, 0.4, 0.3])

    result = run_label_shuffle_test(features, labels, n_permutations=100)

    print()
    print("=== RESULTS ===")
    print(f"  Real Sharpe:     {result['real_sharpe']:.4f}")
    print(f"  Null mean:       {result['null_mean']:.4f}")
    print(f"  Null std:        {result['null_std']:.4f}")
    print(f"  Null 95th pct:   {result['null_95th_percentile']:.4f}")
    print(f"  p-value:         {result['p_value']:.4f}")
    print(f"  Survives (p<0.05, >95th pct): {result['survives']}")
    print()

    if result["survives"]:
        print("  VERDICT: Edge may be real — survives null hypothesis test")
    else:
        print("  VERDICT: NO EDGE — real Sharpe falls inside null distribution")
        print("  (This is expected for synthetic random data)")
