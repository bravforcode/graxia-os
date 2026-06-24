"""
FEATURE SIGNAL DIAGNOSTIC — Check if features have predictive power.

Before training ML models, run this to check:
1. Raw correlation of each feature with forward returns
2. Mutual information (catches non-linear relationships)
3. Which features pass noise floor threshold
4. Whether the feature set is worth training at all

If NO feature has |corr| > noise_floor → XGBoost will fail regardless of data volume.
Fix: better features needed, not more data.

Usage:
    python scripts/diagnose_features.py [--symbol XAUUSD] [--freq 1min] [--horizon 1]
"""
import argparse
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

from scipy.stats import pearsonr, spearmanr
from sklearn.feature_selection import mutual_info_regression

FEATURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "features")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "diagnostics")


def load_data(symbol: str, freq: str) -> pd.DataFrame:
    path = os.path.join(FEATURES_DIR, f"features_{symbol}_{freq}.parquet")
    if not os.path.exists(path):
        print(f"ERROR: {path} not found. Run build_features.py first.")
        sys.exit(1)
    df = pd.read_parquet(path)
    print(f"  Loaded: {len(df)} rows, {len(df.columns)} columns")
    return df


def diagnose(df: pd.DataFrame, horizon: int = 1, noise_floor: float = 0.02) -> dict:
    """
    Check every feature for predictive power against forward return.
    
    Tests:
    1. Pearson correlation (linear)
    2. Spearman correlation (monotonic)
    3. Mutual information (non-linear)
    
    Returns diagnostic report.
    """
    exclude = {'target', 'target_return', 'symbol', 'freq', 'timestamp',
               'open', 'high', 'low', 'close', 'volume', 'tick_count',
               'tr', 'bb_upper', 'bb_lower', 'bb_mid', 'macd_signal'}

    feature_cols = [c for c in df.columns if c not in exclude
                    and df[c].dtype in (np.float64, np.int64, np.float32, np.int32)]

    if 'target_return' not in df.columns and 'return_1' in df.columns:
        forward = df['return_1'].shift(-horizon)
    elif 'target_return' in df.columns:
        forward = df['target_return']
    else:
        forward = df['close'].pct_change(horizon).shift(-horizon)

    forward = forward.dropna()
    
    results = []
    for col in feature_cols:
        valid = pd.DataFrame({'x': df[col], 'y': forward}).dropna()
        if len(valid) < 30:
            continue

        x, y = valid['x'].values, valid['y'].values

        # Pearson
        r_p, p_p = pearsonr(x, y)
        # Spearman
        r_s, p_s = spearmanr(x, y)
        # Mutual Information (normalized)
        mi = mutual_info_regression(x.reshape(-1, 1), y)
        mi_norm = mi[0] / abs(y.std()) if y.std() > 0 else 0

        # Signal quality
        has_signal = abs(r_p) > noise_floor
        has_nonlinear = mi_norm > noise_floor * 2

        results.append({
            "feature": col,
            "pearson_r": round(r_p, 6),
            "pearson_p": round(p_p, 6),
            "spearman_r": round(r_s, 6),
            "mutual_info_norm": round(mi_norm, 6),
            "has_linear_signal": has_signal,
            "has_nonlinear_signal": has_nonlinear,
            "n_samples": len(valid),
        })

    results_df = pd.DataFrame(results).sort_values('pearson_r', key=abs, ascending=False)
    return results_df


def main():
    parser = argparse.ArgumentParser(description="Feature signal diagnostic")
    parser.add_argument("--symbol", type=str, default="XAUUSD")
    parser.add_argument("--freq", type=str, default="1min")
    parser.add_argument("--horizon", type=int, default=1,
                        help="Forward return horizon (bars)")
    parser.add_argument("--noise-floor", type=float, default=0.02,
                        help="Minimum |corr| for linear signal")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"{'='*60}")
    print("FEATURE SIGNAL DIAGNOSTIC")
    print(f"  Symbol: {args.symbol} @ {args.freq}")
    print(f"  Horizon: {args.horizon} bars")
    print(f"  Noise floor: |corr| > {args.noise_floor}")
    print(f"{'='*60}")

    df = load_data(args.symbol, args.freq)
    results = diagnose(df, args.horizon, args.noise_floor)

    # Summary
    n_linear = results['has_linear_signal'].sum()
    n_nonlinear = results['has_nonlinear_signal'].sum()
    n_total = len(results)

    print(f"\n--- Results ---")
    print(f"  Features tested: {n_total}")
    print(f"  Linear signal (|r|>{args.noise_floor}): {n_linear}/{n_total}")
    print(f"  Non-linear signal (MI>{args.noise_floor*2}): {n_nonlinear}/{n_total}")

    print(f"\n  Top correlations:")
    for _, row in results.head(10).iterrows():
        flag = "!" if row['has_linear_signal'] else " "
        print(f"    {flag} {row['feature']:<20s} r={row['pearson_r']:+7.4f}  "
              f"MI={row['mutual_info_norm']:6.4f}  n={row['n_samples']}")

    verdict = "PASS" if n_linear > 0 else "FAIL"
    reason = (f"{n_linear} features found with |corr| > {args.noise_floor}"
              if n_linear > 0 else
              f"No feature passes noise floor |r| > {args.noise_floor}. "
              f"XGBoost will fail regardless of data volume. "
              f"Need better features (add order book, sentiment, or change target framing).")

    print(f"\n--- Verdict: {verdict} ---")
    print(f"  {reason}")

    # Save
    save_path = os.path.join(OUTPUT_DIR, f"diagnostic_{args.symbol}_{args.freq}.csv")
    results.to_csv(save_path, index=False)

    report = {
        "symbol": args.symbol,
        "freq": args.freq,
        "horizon": args.horizon,
        "noise_floor": args.noise_floor,
        "n_features": n_total,
        "n_linear_signal": int(n_linear),
        "n_nonlinear_signal": int(n_nonlinear),
        "verdict": verdict,
        "reason": reason,
        "top_features": results.head(10)['feature'].tolist(),
        "top_correlations": results.head(10)['pearson_r'].tolist(),
        "csv_path": save_path,
    }
    with open(os.path.join(OUTPUT_DIR, f"diagnostic_{args.symbol}.json"), 'w') as f:
        json.dump(report, f, indent=2)

    print(f"\n  Report: {save_path}")


if __name__ == "__main__":
    main()
