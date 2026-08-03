"""
Deflated Sharpe Ratio calculator — Bailey & López de Prado (2014).

Reads walk-forward results from artifacts/walk_forward/ and computes the
Deflated Sharpe Ratio via the real implementation in
validation/deflated_sharpe.py (Euler-Mascheroni expected-max-SR correction),
the same module used by validation/overfitting_detector.py.

n_trials (the multiple-testing count) is NOT recoverable from disk artifacts
alone: validation/search_budget.py's SearchBudgetTracker is an in-process,
non-persisted object, so a fresh CLI process has no way to reconstruct the
trial history of whatever sweep produced the walk-forward file it's reading.
It must be supplied explicitly via --n-trials, sourced from the
SearchBudgetTracker/ParamSweep instance that actually ran the search.

Usage:
    python scripts/run_deflated_sharpe.py --symbol XAUUSD --freq H1 --n-trials 12
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent.parent
ARTIFACTS = BASE / "artifacts" / "walk_forward"

ROOT = BASE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant_os.validation.deflated_sharpe import deflated_sharpe_ratio as _real_dsr


def load_wf_returns(symbol: str, freq: str) -> tuple[np.ndarray, int]:
    """Load per-fold net PnL values from walk-forward JSON artifacts.

    Returns (returns_array, n_folds) where returns_array contains per-fold
    net_pnl values (used as proxy for per-period returns).
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

    returns = np.array([fold["net_pnl"] for fold in folds], dtype=np.float64)
    n_folds = len(folds)

    return returns, n_folds


def compute_dsr(returns: np.ndarray, n_trials: int, annualization: float) -> dict:
    """Compute observed-Sharpe moments from returns, then defer to the real
    Bailey & López de Prado DSR implementation for the correction itself."""
    returns = np.asarray(returns, dtype=np.float64)
    n_obs = len(returns)
    if n_obs < 20:
        return _insufficient("Need ≥20 observations", n_obs, n_trials)

    mean_ret = float(np.mean(returns))
    std_ret = float(np.std(returns, ddof=1))
    if std_ret < 1e-12:
        return _insufficient("Zero variance", n_obs, n_trials)

    std_rets = (returns - mean_ret) / std_ret
    skew = float(np.mean(std_rets ** 3))
    kurt = float(np.mean(std_rets ** 4))  # raw 4th moment, matches overfitting_detector's convention

    sr_hat = mean_ret / std_ret * (annualization ** 0.5)

    result = _real_dsr(
        observed_sharpe=sr_hat,
        n_trials=n_trials,
        n_observations=n_obs,
        sharpe_annualization_factor=annualization ** 0.5,  # SP1: sr_hat was scaled by annualization**0.5 above — de-annualize with the same factor
        skewness=skew,
        kurtosis=kurt,
    )

    if result.passes_threshold:
        recommendation = "PASS — strategy likely genuine after multiple-testing correction"
    elif result.probability_alpha < 0.50:
        recommendation = "WEAK — insufficient evidence of genuine edge"
    else:
        recommendation = "FAIL — strategy likely overfit"

    return {
        "observed_sharpe": round(result.observed_sharpe, 6),
        "deflated_sharpe": round(result.deflated_sharpe, 6),
        "probability_alpha": round(result.probability_alpha, 6),
        "expected_max_sharpe": round(result.multiple_testing_adjustment, 6),
        "passes_threshold": result.passes_threshold,
        "skew": round(skew, 6),
        "kurtosis": round(kurt, 6),
        "n_obs": n_obs,
        "n_trials": n_trials,
        "recommendation": recommendation,
    }


def _insufficient(reason: str, n_obs: int, n_trials: int) -> dict:
    return {
        "observed_sharpe": float("nan"),
        "deflated_sharpe": float("nan"),
        "probability_alpha": float("nan"),
        "expected_max_sharpe": float("nan"),
        "passes_threshold": False,
        "skew": float("nan"),
        "kurtosis": float("nan"),
        "n_obs": n_obs,
        "n_trials": n_trials,
        "recommendation": f"INSUFFICIENT — {reason}",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Deflated Sharpe Ratio calculator (Bailey & López de Prado 2014)"
    )
    parser.add_argument("--symbol", default="XAUUSD", help="Symbol (default: XAUUSD)")
    parser.add_argument("--freq", default="H1", help="Timeframe (default: H1)")
    parser.add_argument("--annualization", type=float, default=252.0,
                        help="Annualization factor (default: 252)")
    parser.add_argument("--n-trials", type=int, default=None,
                        help="Number of independent strategy trials this result came from "
                             "(from SearchBudgetTracker/ParamSweep for the sweep that produced "
                             "the walk-forward artifact). Required for a meaningful correction.")
    parser.add_argument("--output", default=None, help="Output JSON path (default: stdout)")
    args = parser.parse_args()

    try:
        returns, n_folds = load_wf_returns(args.symbol, args.freq)
    except (FileNotFoundError, ValueError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    if args.n_trials is None:
        print(
            "[WARN] --n-trials not supplied — defaulting to 1 (no multiple-testing "
            "correction applied). Pass the real trial count from the "
            "SearchBudgetTracker/ParamSweep that produced this result.",
            file=sys.stderr,
        )
        n_trials = 1
    else:
        n_trials = args.n_trials

    result = compute_dsr(returns=returns, n_trials=n_trials, annualization=args.annualization)
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
