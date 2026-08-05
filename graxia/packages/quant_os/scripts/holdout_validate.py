"""Sacred Holdout Validation — Run FROZEN momentum_factor_rotation on holdout data.

Evaluates whether the strategy's edge survives out-of-sample by checking:
  1. Direction consistency (positive Sharpe = same sign as in-sample)
  2. Sharpe ratio within 50% of in-sample value
  3. Deflated Sharpe t-stat (dk_t > 0)

Usage:
    python scripts/holdout_validate.py \
        --trial 2001 \
        --holdout data/sacred_holdout/holdout.csv \
        --in-sample-sharpe 1.85 \
        --output reports/holdout_validation_2001.json

    # Minimal (defaults to known holdout path):
    python scripts/holdout_validate.py --trial 2001

Exit codes:
    0 = HOLDOUT PASS
    1 = HOLDOUT FAIL
    2 = Script error (bad input, missing file, etc.)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path setup — allow `from graxia.packages.quant_os.strategies.*` imports
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
GRAXIA_ROOT = ROOT.parent.parent.parent
for p in (str(GRAXIA_ROOT), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from graxia.packages.quant_os.strategies.momentum_factor_rotation import (
    MomentumFactorRotationConfig,
    compute_momentum_factor_rotation,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_HOLDOUT = ROOT / "data" / "sacred_holdout" / "holdout.csv"
HOLDOUT_PASS_THRESHOLD_SHARPE_RATIO = 0.50  # Sharpe must be within 50% of in-sample
DK_T_THRESHOLD = 0.0  # dk_t must be positive


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_holdout(path: Path) -> pd.DataFrame:
    """Load holdout CSV and return a price DataFrame (columns = assets).

    Expected CSV format:
        date, XAUUSD, XAGUSD, EURUSD, GBPUSD, USDJPY, NAS100, US30
    Or pivot-style with 'date' + 'symbol' + 'close' columns.

    Returns DataFrame with DatetimeIndex and one column per asset.
    """
    if not path.exists():
        raise FileNotFoundError(f"Holdout file not found: {path}")

    df = pd.read_csv(path, encoding="utf-8")

    # Detect date column
    date_col = None
    for candidate in ("date", "Date", "timestamp", "Timestamp", "time", "Time"):
        if candidate in df.columns:
            date_col = candidate
            break
    if date_col is None:
        raise ValueError(f"No date column found in {path}. Columns: {list(df.columns)}")

    df[date_col] = pd.to_datetime(df[date_col], utc=True)
    df = df.set_index(date_col).sort_index()

    # If pivot-style (symbol + close columns), pivot to wide
    if "symbol" in df.columns and "close" in df.columns:
        df = df.pivot_table(index=df.index, columns="symbol", values="close")
        df.columns.name = None
    # Otherwise assume wide format: each column is an asset price series
    else:
        # Drop non-numeric columns (keep only price columns)
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        df = df[numeric_cols]

    if df.empty:
        raise ValueError(f"Holdout file is empty or has no numeric columns: {path}")

    return df


def _compute_sharpe(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Annualized Sharpe ratio (zero-risk rate = 0)."""
    if len(returns) < 2 or returns.std() == 0:
        return 0.0
    return float(returns.mean() / returns.std() * np.sqrt(periods_per_year))


def _compute_dk_t(returns: pd.Series) -> float:
    """Compute dk_t (deflated t-statistic proxy).

    dk_t = t_stat * sqrt(1 - (skew/6)*t_stat + (kurtosis-3)/24 * t_stat^2)
    Simplified: just the t-stat of mean return (positive = edge present).
    """
    n = len(returns)
    if n < 3 or returns.std() == 0:
        return 0.0
    t_stat = returns.mean() / (returns.std() / np.sqrt(n))
    skew = float(returns.skew())
    kurt = float(returns.kurtosis())
    # Bailey & Lopez de Prado adjustment
    dk_t = t_stat * np.sqrt(
        1 - (skew / 6) * t_stat + (kurt / 24) * t_stat**2
    )
    return float(dk_t)


def _direction_consistency(holdout_sharpe: float) -> bool:
    """Direction is consistent if Sharpe is positive (same direction as in-sample gain)."""
    return holdout_sharpe > 0.0


def _sharpe_within_tolerance(holdout_sharpe: float, in_sample_sharpe: float) -> bool:
    """Sharpe is within 50% of in-sample value."""
    if in_sample_sharpe <= 0:
        return holdout_sharpe > 0  # Any positive Sharpe passes if in-sample was negative
    return holdout_sharpe >= in_sample_sharpe * HOLDOUT_PASS_THRESHOLD_SHARPE_RATIO


# ---------------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------------


def run_holdout_validation(
    trial: int,
    holdout_path: Path,
    in_sample_sharpe: float,
) -> dict:
    """Run the full holdout validation and return result dict.

    Parameters
    ----------
    trial : int
        Trial number from the edge-search ledger.
    holdout_path : Path
        Path to the holdout CSV.
    in_sample_sharpe : float
        Observed Sharpe ratio from the in-sample run.

    Returns
    -------
    dict with keys:
        trial, timestamp, holdout_path, in_sample_sharpe,
        holdout_sharpe, holdout_dk_t, direction_consistent,
        sharpe_within_tolerance, verdict, details
    """
    prices = _load_holdout(holdout_path)

    # Run FROZEN momentum_factor_rotation
    config = MomentumFactorRotationConfig()  # defaults = FROZEN params
    result = compute_momentum_factor_rotation(prices, config)

    # Compute portfolio returns: equal-weight across signaled assets
    # signal DataFrame: {asset: {-1, 0, +1}}
    daily_returns = prices.pct_change().fillna(0)
    # Weighted returns: signal * return for each asset, then mean across assets
    weighted = result.signal.shift(1).fillna(0) * daily_returns
    portfolio_returns = weighted.mean(axis=1)

    # Drop initial warmup period (lookback = 252)
    warmup = 252
    if len(portfolio_returns) > warmup:
        portfolio_returns = portfolio_returns.iloc[warmup:]

    # Compute metrics
    holdout_sharpe = _compute_sharpe(portfolio_returns)
    holdout_dk_t = _compute_dk_t(portfolio_returns)
    dir_ok = _direction_consistency(holdout_sharpe)
    tol_ok = _sharpe_within_tolerance(holdout_sharpe, in_sample_sharpe)
    dk_ok = holdout_dk_t > DK_T_THRESHOLD

    # Verdict
    if not dir_ok:
        verdict = "FAIL"
        reason = "Direction reversal: negative Sharpe on holdout"
    elif not tol_ok:
        verdict = "FAIL"
        reason = f"Sharpe {holdout_sharpe:.4f} < 50% of in-sample {in_sample_sharpe:.4f}"
    elif not dk_ok:
        verdict = "FAIL"
        reason = f"dk_t {holdout_dk_t:.4f} <= 0 (no statistical edge)"
    else:
        verdict = "PASS"
        reason = "All checks passed"

    # Per-asset signal summary
    asset_signals = {}
    for col in result.signal.columns:
        pos_days = int((result.signal[col] > 0).sum())
        neg_days = int((result.signal[col] < 0).sum())
        flat_days = int((result.signal[col] == 0).sum())
        asset_signals[col] = {
            "long_days": pos_days,
            "short_days": neg_days,
            "flat_days": flat_days,
        }

    # Annualized return
    ann_return = float(portfolio_returns.mean() * 252)

    return {
        "trial": trial,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "holdout_path": str(holdout_path),
        "holdout_period": {
            "start": str(prices.index[0].date()) if len(prices) > 0 else None,
            "end": str(prices.index[-1].date()) if len(prices) > 0 else None,
            "bars": len(prices),
            "assets": list(prices.columns),
        },
        "in_sample_sharpe": round(in_sample_sharpe, 6),
        "holdout_sharpe": round(holdout_sharpe, 6),
        "holdout_annualized_return": round(ann_return, 6),
        "holdout_dk_t": round(holdout_dk_t, 6),
        "direction_consistent": dir_ok,
        "sharpe_within_tolerance": tol_ok,
        "dk_t_positive": dk_ok,
        "verdict": verdict,
        "reason": reason,
        "config": {
            "lookbacks": list(config.lookbacks),
            "vol_target": config.vol_target,
            "top_n": config.top_n,
            "bottom_n": config.bottom_n,
            "rebalance_freq": config.rebalance_freq,
            "min_signal_strength": config.min_signal_strength,
        },
        "asset_signals": asset_signals,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sacred holdout validation for momentum_factor_rotation (FROZEN params).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/holdout_validate.py --trial 2001 --holdout data/sacred_holdout/holdout.csv
  python scripts/holdout_validate.py --trial 2001 --in-sample-sharpe 1.85
        """,
    )
    parser.add_argument(
        "--trial",
        type=int,
        required=True,
        help="Trial number from the edge-search ledger.",
    )
    parser.add_argument(
        "--holdout",
        type=str,
        default=str(DEFAULT_HOLDOUT),
        help=f"Path to holdout CSV (default: {DEFAULT_HOLDOUT}).",
    )
    parser.add_argument(
        "--in-sample-sharpe",
        type=float,
        default=1.0,
        help="Observed Sharpe ratio from the in-sample run (default: 1.0).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON path (default: reports/holdout_validation_<trial>.json).",
    )

    args = parser.parse_args()

    holdout_path = Path(args.holdout)
    output_path = (
        Path(args.output)
        if args.output
        else ROOT / "reports" / f"holdout_validation_{args.trial}.json"
    )

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = run_holdout_validation(
            trial=args.trial,
            holdout_path=holdout_path,
            in_sample_sharpe=args.in_sample_sharpe,
        )
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}", file=sys.stderr)
        sys.exit(2)

    # Write JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)

    # Print summary
    print("=" * 60)
    print(f"  HOLDOUT VALIDATION — Trial #{args.trial}")
    print("=" * 60)
    print(f"  Holdout:      {holdout_path}")
    print(f"  Period:       {result['holdout_period']['start']} → {result['holdout_period']['end']}")
    print(f"  Assets:       {', '.join(result['holdout_period']['assets'])}")
    print(f"  In-sample SR: {result['in_sample_sharpe']:.4f}")
    print(f"  Holdout SR:   {result['holdout_sharpe']:.4f}")
    print(f"  Holdout dk_t: {result['holdout_dk_t']:.4f}")
    print(f"  Direction OK: {result['direction_consistent']}")
    print(f"  Tolerance OK: {result['sharpe_within_tolerance']}")
    print(f"  dk_t OK:      {result['dk_t_positive']}")
    print("-" * 60)
    print(f"  VERDICT:      {result['verdict']}")
    print(f"  Reason:       {result['reason']}")
    print("=" * 60)
    print(f"\n  Output: {output_path}")

    sys.exit(0 if result["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
