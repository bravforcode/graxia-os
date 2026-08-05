#!/usr/bin/env python3
"""
Probability of Backtest Overfitting (PBO) — Bailey, Borwein, López de Prado 2015.

Implements Combinatorally-Symmetric Cross-Validation (CSCV):
  1. Split S walk-forward folds into two equal halves (train/test)
  2. For each combination, find the best-performing strategy in-sample
  3. Check if that same strategy is also best out-of-sample
  4. PBO = fraction of combinations where the IS-best is NOT the OOS-best

PBO ∈ [0, 1].  PBO < 0.5 = good (less overfitting than chance).
PBO close to 1.0 = severe overfitting.

Usage:
    python scripts/run_pbo.py --symbol XAUUSD
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent.parent
ARTIFACTS = BASE / "artifacts" / "walk_forward"


# ---------------------------------------------------------------------------
# Normal CDF fallback
# ---------------------------------------------------------------------------

try:
    from scipy.stats import norm as _norm

    def _phi(x: float) -> float:
        return float(_norm.cdf(x))

except ImportError:
    def _phi(x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# CSCV — Combinatorially-Symmetric Cross-Validation
# ---------------------------------------------------------------------------


def cscv_pbo(
    fold_metrics: np.ndarray,
    n_partitions: int = 16,
) -> dict:
    """Compute Probability of Backtest Overfitting via CSCV.

    Parameters
    ----------
    fold_metrics:
        (S, N) array where S = number of strategy configurations (folds)
        and N = number of performance metrics per fold.
        For a single-metric use case, reshape to (S, 1).
        Each row is a strategy, each column is a fold's performance.
    n_partitions:
        Number of partitions to split folds into. Must be even.

    Returns
    -------
    dict with: pbo, p_value, n_combos, n_overfit, recommendation
    """
    fold_metrics = np.asarray(fold_metrics, dtype=np.float64)
    if fold_metrics.ndim == 1:
        fold_metrics = fold_metrics.reshape(-1, 1)

    n_strategies, n_folds = fold_metrics.shape

    if n_folds < 4:
        return _pbo_insufficient("Need ≥4 folds for CSCV", n_folds)

    # Ensure even number of partitions
    n_partitions = min(n_partitions, n_folds)
    if n_partitions % 2 != 0:
        n_partitions -= 1
    if n_partitions < 4:
        return _pbo_insufficient("Too few partitions after adjustment", n_folds)

    half = n_partitions // 2

    # Generate all C(S, S/2) combinations — pick S/2 indices for in-sample
    all_indices = list(range(n_partitions))
    combos = list(itertools.combinations(all_indices, half))
    n_combos = len(combos)

    # Limit combos for performance (C(16,8) = 12870 is manageable)
    if n_combos > 50000:
        # Subsample for very large cases
        rng = np.random.default_rng(42)
        combo_indices = rng.choice(n_combos, size=50000, replace=False)
        combos = [combos[i] for i in combo_indices]
        n_combos = len(combos)

    # Partition fold indices into n_partitions groups
    fold_indices = np.array_split(np.arange(n_folds), n_partitions)

    n_overfit = 0

    for is_indices in combos:
        oos_indices = tuple(i for i in all_indices if i not in is_indices)

        # Aggregate performance in-sample and out-of-sample
        is_folds = np.concatenate([fold_indices[i] for i in is_indices])
        oos_folds = np.concatenate([fold_indices[i] for i in oos_indices])

        # Sum performance across folds for each strategy
        is_perf = fold_metrics[:, is_folds].sum(axis=1)
        oos_perf = fold_metrics[:, oos_folds].sum(axis=1)

        # Find best strategy in-sample
        best_is = int(np.argmax(is_perf))

        # Is the IS-best also in the top half out-of-sample?
        oos_rank = int(np.sum(oos_perf >= oos_perf[best_is]))

        # Overfit if IS-best performs below median OOS
        if oos_rank > n_strategies / 2:
            n_overfit += 1

    pbo = n_overfit / n_combos if n_combos > 0 else float("nan")

    # P-value: probability of seeing this PBO under null (uniform)
    # Use normal approximation for binomial test
    if n_combos > 0:
        z = (pbo - 0.5) / math.sqrt(0.25 / n_combos)
        p_value = 1.0 - _phi(z)  # one-sided: P(PBO > 0.5)
    else:
        p_value = float("nan")

    if pbo < 0.25:
        recommendation = "PASS — low overfitting risk (PBO < 0.25)"
    elif pbo < 0.50:
        recommendation = "WEAK — moderate overfitting risk (PBO < 0.50)"
    elif pbo < 0.75:
        recommendation = "WARN — high overfitting risk (PBO ≥ 0.50)"
    else:
        recommendation = "FAIL — severe overfitting (PBO ≥ 0.75)"

    return {
        "pbo": round(pbo, 6),
        "p_value": round(p_value, 6),
        "n_combos": n_combos,
        "n_overfit": n_overfit,
        "n_strategies": n_strategies,
        "n_folds": n_folds,
        "n_partitions": n_partitions,
        "recommendation": recommendation,
    }


def _pbo_insufficient(reason: str, n_folds: int) -> dict:
    return {
        "pbo": float("nan"),
        "p_value": float("nan"),
        "n_combos": 0,
        "n_overfit": 0,
        "n_strategies": 0,
        "n_folds": n_folds,
        "n_partitions": 0,
        "recommendation": f"INSUFFICIENT — {reason}",
    }


# ---------------------------------------------------------------------------
# Walk-forward result loading
# ---------------------------------------------------------------------------


def load_fold_matrix(symbol: str, freq: str = "H1") -> tuple[np.ndarray, list[dict]]:
    """Load walk-forward fold results as a strategy × fold performance matrix.

    Each fold's net_pnl is used as the performance metric.
    Returns (matrix, fold_details) where matrix is (n_folds, 1).
    """
    pattern = f"wf_{symbol}_{freq}_*.json"
    files = sorted(ARTIFACTS.glob(pattern))
    if not files:
        raise FileNotFoundError(
            f"No walk-forward results for {symbol}/{freq} in {ARTIFACTS}\n"
            f"  Expected pattern: {pattern}\n"
            f"  Run: python scripts/wf_patched.py --symbol {symbol} --freq {freq}"
        )

    latest = files[-1]
    with open(latest) as f:
        data = json.load(f)

    folds = data.get("folds", [])
    if not folds:
        raise ValueError(f"No folds in {latest}")

    # Build matrix: each fold is a "strategy" configuration
    # Use net_pnl as the single performance metric
    matrix = np.array([[fold["net_pnl"]] for fold in folds], dtype=np.float64)

    return matrix, folds


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Probability of Backtest Overfitting (Bailey et al. 2015 CSCV)"
    )
    parser.add_argument("--symbol", default="XAUUSD", help="Symbol (default: XAUUSD)")
    parser.add_argument("--freq", default="H1", help="Timeframe (default: H1)")
    parser.add_argument("--partitions", type=int, default=16,
                        help="Number of CSCV partitions (default: 16, must be even)")
    parser.add_argument("--output", default=None, help="Output JSON path (default: stdout)")
    args = parser.parse_args()

    try:
        matrix, folds = load_fold_matrix(args.symbol, args.freq)
    except (FileNotFoundError, ValueError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    result = cscv_pbo(matrix, n_partitions=args.partitions)
    result["symbol"] = args.symbol
    result["freq"] = args.freq
    result["source_file"] = str(
        sorted(ARTIFACTS.glob(f"wf_{args.symbol}_{args.freq}_*.json"))[-1]
    )

    output_json = json.dumps(result, indent=2)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            f.write(output_json + "\n")
        print(f"Saved: {args.output}")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
