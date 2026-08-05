"""Compute the Deflated Sharpe Ratio (DSR) test from Bailey & Lopez de Prado (2014).

Reads the reconciled trial count from a JSON file and evaluates whether a
candidate strategy's observed Sharpe ratio remains statistically significant
after correcting for multiple testing.

DSR = P(SR* > 0 | N, SR_0, skew, kurtosis, T)

Where:
  SR* = observed Sharpe ratio of the candidate strategy
  N   = total number of trials tested (from reconciliation)
  SR_0 = expected maximum Sharpe under null (no skill)
  skew = skewness of returns
  kurtosis = excess kurtosis of returns
  T = number of observations

Expected max SR under null (independent trials):
  SR_0 = sqrt(2) * erfinv(1 - 2/N) * (1 - euler_gamma/sqrt(T))
         + euler_gamma * sqrt(log(N)) / sqrt(T)

Where erfinv is the inverse error function and euler_gamma ≈ 0.5772.

DSR > 0 means the observed Sharpe is statistically significant after
correcting for multiple testing.

Usage:
  python scripts/compute_deflated_sharpe.py \\
      --trial-count-source trial_count_reconciliation_20260720.json \\
      --candidate-trial 2001 \\
      --observed-sharpe 1.85 \\
      --observed-skew -0.3 \\
      --observed-kurtosis 4.2 \\
      --T 1200 \\
      --output reports/deflated_sharpe_2001_20260720.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.special import erfinv
from scipy.stats import norm

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EULER_GAMMA = 0.5772156649015329


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_sr0(N: int, T: int) -> float:
    """Expected maximum Sharpe ratio under the null hypothesis (no skill).

    Accounts for N independent trials and T observations per trial.

    Parameters
    ----------
    N : int
        Total number of trials tested (must be >= 2).
    T : int
        Number of observations (returns) in the candidate trial.

    Returns
    -------
    float
        SR_0, the expected max Sharpe under the null.
    """
    if N < 2:
        raise ValueError(f"N must be >= 2, got {N}")
    if T < 1:
        raise ValueError(f"T must be >= 1, got {T}")

    # erfinv(1 - 2/N) is the (1 - 1/N)-quantile of the half-normal
    base = math.sqrt(2.0) * erfinv(1.0 - 2.0 / N)
    correction = 1.0 - EULER_GAMMA / math.sqrt(T)
    tail = EULER_GAMMA * math.sqrt(math.log(N)) / math.sqrt(T)
    return base * correction + tail


def compute_dsr(
    observed_sharpe: float,
    sr0: float,
    skew: float,
    kurtosis: float,
    T: int,
) -> tuple[float, float]:
    """Compute the Deflated Sharpe Ratio and its p-value.

    Parameters
    ----------
    observed_sharpe : float
        SR*, the observed annualized Sharpe ratio.
    sr0 : float
        Expected maximum Sharpe under the null.
    skew : float
        Skewness of the strategy returns.
    kurtosis : float
        Excess kurtosis of the strategy returns.
    T : int
        Number of observations.

    Returns
    -------
    tuple[float, float]
        (DSR, p_value) where DSR = Phi(DSR_z) and p_value = 1 - DSR.
    """
    # Variance of the Sharpe ratio estimator (adjusted for non-normality)
    # Var[SR_hat] ≈ (1/T) * (1 + 0.5*SR^2 - skew*SR + (kurtosis-3)/4 * SR^2)
    sr_var = (
        1.0
        + 0.5 * observed_sharpe**2
        - skew * observed_sharpe
        + (kurtosis - 3.0) / 4.0 * observed_sharpe**2
    ) / T

    if sr_var <= 0:
        # Degenerate case — treat as insignificant
        return 0.0, 1.0

    sr_std = math.sqrt(sr_var)

    # DSR z-score: how many standard deviations the observed SR exceeds SR_0
    dsr_z = (observed_sharpe - sr0) / sr_std

    # DSR = P(SR* > 0 | ...) = Phi(dsr_z)
    dsr = float(norm.cdf(dsr_z))
    p_value = 1.0 - dsr

    return dsr, p_value


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute the Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014).",
    )
    parser.add_argument(
        "--trial-count-source",
        type=Path,
        required=True,
        help="Path to trial_count_reconciliation JSON file.",
    )
    parser.add_argument(
        "--candidate-trial",
        type=int,
        required=True,
        help="Trial number of the candidate strategy (e.g. 2001).",
    )
    parser.add_argument(
        "--observed-sharpe",
        type=float,
        required=True,
        help="Observed (annualized) Sharpe ratio of the candidate.",
    )
    parser.add_argument(
        "--observed-skew",
        type=float,
        required=True,
        help="Skewness of the candidate's return distribution.",
    )
    parser.add_argument(
        "--observed-kurtosis",
        type=float,
        required=True,
        help="Excess kurtosis of the candidate's return distribution.",
    )
    parser.add_argument(
        "--T",
        type=int,
        required=True,
        help="Number of observations (returns) in the candidate trial.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/deflated_sharpe_output.json"),
        help="Output JSON path (default: reports/deflated_sharpe_output.json).",
    )
    return parser.parse_args(argv)


def load_trial_count(source: Path) -> int:
    """Load the reconciled trial count from JSON.

    Expected schema (as produced by scripts/reconcile_trial_ledger.py)::

        {
            "total_n_for_multiple_testing": <int>,
            ...
        }

    Also accepts ``"reconciled_trial_count"``, ``"total_trials"``, and
    ``"n_trials"`` as aliases for backward compatibility.
    """
    if not source.exists():
        raise FileNotFoundError(f"Trial count source not found: {source}")

    with open(source, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    # Try known keys in order of preference
    for key in (
        "total_n_for_multiple_testing",
        "reconciled_trial_count",
        "total_trials",
        "n_trials",
    ):
        if key in data:
            return int(data[key])

    raise KeyError(
        f"Could not find trial count key in {source}. "
        f"Expected one of: total_n_for_multiple_testing, reconciled_trial_count, "
        f"total_trials, n_trials"
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # --- 1. Load reconciled trial count ---
    try:
        N = load_trial_count(args.trial_count_source)
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if N < 2:
        print(
            f"ERROR: Reconciled trial count must be >= 2, got {N}",
            file=sys.stderr,
        )
        return 1

    T = args.T
    observed_sharpe = args.observed_sharpe
    skew = args.observed_skew
    kurtosis = args.observed_kurtosis

    # --- 2. Compute SR_0 ---
    sr0 = compute_sr0(N, T)

    # --- 3. Compute DSR ---
    dsr, p_value = compute_dsr(observed_sharpe, sr0, skew, kurtosis, T)

    # --- 4. Build output ---
    passes = dsr > 0.95
    output = {
        "test": "deflated_sharpe_ratio",
        "reference": "Bailey & Lopez de Prado (2014)",
        "candidate_trial": args.candidate_trial,
        "inputs": {
            "observed_sharpe": round(observed_sharpe, 6),
            "observed_skew": round(skew, 6),
            "observed_kurtosis": round(kurtosis, 6),
            "T": T,
            "N": N,
            "trial_count_source": str(args.trial_count_source),
        },
        "intermediate": {
            "euler_gamma": EULER_GAMMA,
            "sr0": round(sr0, 6),
        },
        "results": {
            "dsr": round(dsr, 6),
            "p_value": round(p_value, 6),
            "passes_threshold_0_95": passes,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # --- 5. Write output ---
    output_path: Path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    # --- 6. Console summary ---
    print(f"Deflated Sharpe Ratio — Candidate Trial {args.candidate_trial}")
    print(f"  N (reconciled trials): {N}")
    print(f"  T (observations):      {T}")
    print(f"  Observed Sharpe:       {observed_sharpe:.4f}")
    print(f"  Skew / Kurtosis:       {skew:.4f} / {kurtosis:.4f}")
    print(f"  SR_0 (null expected):  {sr0:.4f}")
    print(f"  DSR:                   {dsr:.4f}")
    print(f"  p-value:               {p_value:.4f}")
    print(f"  Passes (DSR > 0.95):   {'YES' if passes else 'NO'}")
    print(f"\nResults written to {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
