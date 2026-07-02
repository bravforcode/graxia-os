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
from glob import glob

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from scipy.stats import pearsonr, spearmanr
from sklearn.feature_selection import mutual_info_regression

FEATURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "features")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "diagnostics")


def load_data(symbol: str, freq: str, feat_dir: str = None) -> pd.DataFrame:
    if feat_dir is None:
        feat_dir = FEATURES_DIR
    # Try v2 naming first, then v1
    candidates = [
        os.path.join(feat_dir, f"features_v2_{symbol}_{freq}.parquet"),
        os.path.join(feat_dir, f"features_{symbol}_{freq}.parquet"),
    ]
    path = None
    for c in candidates:
        if os.path.exists(c):
            path = c
            break
    if path is None:
        # Wildcard search
        paths = glob(os.path.join(feat_dir, f"*{symbol}*{freq}*.parquet"))
        if paths:
            path = paths[0]
    if path is None:
        print(f"ERROR: no features for {symbol} @ {freq} in {feat_dir}")
        sys.exit(1)
    df = pd.read_parquet(path)
    print(f"  Loaded: {os.path.basename(path)} — {len(df)} rows, {len(df.columns)} columns")
    return df


def diagnose(df: pd.DataFrame, horizon: int = 1, noise_floor: float = 0.02, walk_forward: bool = True) -> pd.DataFrame:
    """
    Check every feature for predictive power against forward return.

    Tests:
    1. Pearson correlation (linear) with Bonferroni correction
    2. Spearman correlation (monotonic)
    3. Mutual information (non-linear)
    4. Walk-forward stability: compute corr on train half, verify it holds on test half

    Returns diagnostic report.
    """
    exclude = {
        "target",
        "target_return",
        "symbol",
        "freq",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "tick_count",
        "tr",
        "bb_upper",
        "bb_lower",
        "bb_mid",
        "macd_signal",
        "tb_label",
        "tb_bar_hit",
        "tb_side",
        "tb_ret",
        "tb_k_upper",
        "tb_k_lower",
    }

    feature_cols = [
        c for c in df.columns if c not in exclude and df[c].dtype in (np.float64, np.int64, np.float32, np.int32)
    ]

    if "target_return" not in df.columns and "return_1" in df.columns:
        forward = df["return_1"].shift(-horizon)
    elif "target_return" in df.columns:
        forward = df["target_return"]
    else:
        forward = df["close"].pct_change(horizon).shift(-horizon)

    forward = forward.dropna()

    results = []
    n_features_tested = 0

    for col in feature_cols:
        valid = pd.DataFrame({"x": df[col], "y": forward}).dropna()
        if len(valid) < 30:
            continue
        n_features_tested += 1

        x, y = valid["x"].values, valid["y"].values

        # Pearson
        r_p, p_p = pearsonr(x, y)
        # Spearman
        r_s, p_s = spearmanr(x, y)
        # Mutual Information (normalized)
        mi = mutual_info_regression(x.reshape(-1, 1), y)
        mi_norm = mi[0] / abs(y.std()) if y.std() > 0 else 0

        # ── Bonferroni correction ──
        # Threshold: α / n_features_tested (apply after we know n)
        bonf_alpha = 0.05 / max(n_features_tested, 1)
        bonf_pass = p_p < bonf_alpha

        # ── Walk-forward stability ──
        wf_stable = None
        if walk_forward and len(valid) > 60:
            split = len(valid) // 2
            # Train half correlation
            r_train, _ = pearsonr(x[:split], y[:split])
            # Test half correlation
            r_test, _ = pearsonr(x[split:], y[split:])
            # Stable if same sign and both above noise_floor/2
            wf_stable = (r_train * r_test > 0) and (abs(r_test) > noise_floor / 2)

        # Signal quality (after Bonferroni)
        has_signal = abs(r_p) > noise_floor and bonf_pass and (wf_stable if walk_forward else True)
        has_nonlinear = mi_norm > noise_floor * 2

        results.append(
            {
                "feature": col,
                "pearson_r": round(r_p, 6),
                "pearson_p": round(p_p, 6),
                "bonferroni_pass": bonf_pass,
                "walk_forward_stable": wf_stable,
                "spearman_r": round(r_s, 6),
                "mutual_info_norm": round(mi_norm, 6),
                "has_verified_signal": has_signal,
                "has_nonlinear_signal": has_nonlinear,
                "n_samples": len(valid),
            }
        )

    results_df = pd.DataFrame(results).sort_values("pearson_r", key=abs, ascending=False)
    results_df.attrs["bonferroni_alpha"] = 0.05 / max(n_features_tested, 1)
    results_df.attrs["n_features_tested"] = n_features_tested
    return results_df


def main():
    parser = argparse.ArgumentParser(description="Feature signal diagnostic")
    parser.add_argument("--symbol", type=str, default="XAUUSD")
    parser.add_argument("--freq", type=str, default="1min")
    parser.add_argument("--horizon", type=int, default=1, help="Forward return horizon (bars)")
    parser.add_argument("--noise-floor", type=float, default=0.02, help="Minimum |corr| for linear signal")
    parser.add_argument("--feat-dir", type=str, default=None, help="Feature directory (default: artifacts/features)")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"{'='*60}")
    print("FEATURE SIGNAL DIAGNOSTIC")
    print(f"  Symbol: {args.symbol} @ {args.freq}")
    print(f"  Horizon: {args.horizon} bars")
    print(f"  Noise floor: |corr| > {args.noise_floor}")
    if args.feat_dir:
        print(f"  Feature dir: {args.feat_dir}")
    print(f"{'='*60}")

    df = load_data(args.symbol, args.freq, args.feat_dir)
    results = diagnose(df, args.horizon, args.noise_floor)

    # Summary
    n_linear = results["has_verified_signal"].sum()
    n_nonlinear = results["has_nonlinear_signal"].sum()
    n_total = len(results)
    bonf_alpha = results.attrs.get("bonferroni_alpha", args.noise_floor)

    print("\n--- Results ---")
    print(f"  Features tested: {n_total}")
    print(f"  Bonferroni threshold: p < {bonf_alpha:.6f}")
    print(f"  Verified signal (|r|>{args.noise_floor} + Bonferroni + walk-forward): {n_linear}/{n_total}")
    print(f"  Non-linear signal (MI>{args.noise_floor*2:.4f}): {n_nonlinear}/{n_total}")

    print("\n  Top correlations:")
    for _, row in results.head(10).iterrows():
        flag = "!" if row["has_verified_signal"] else " "
        wf = "WF-OK" if row["walk_forward_stable"] else "WF-?" if row["walk_forward_stable"] is None else "WF-FAIL"
        print(
            f"    {flag} {row['feature']:<20s} r={row['pearson_r']:+7.4f}  "
            f"p={row['pearson_p']:.4e}  bonf={row['bonferroni_pass']}  {wf}  n={row['n_samples']}"
        )

    if n_linear == 0:
        verdict = "FAIL — HIGH BIAS"
        reason = (
            "No feature survives Bonferroni + walk-forward validation. "
            "Feature set has no information. Need NEW features "
            "(order-flow proxy, multi-TF confluence, volume profile), "
            "NOT more data at same sample size. Adding samples won't turn r=0.06 into r=0.3."
        )
    elif n_linear <= 2:
        verdict = "MARGINAL — WEAK SIGNAL"
        reason = (
            f"Only {n_linear} features survive rigorous tests. "
            "Signal exists but very weak. Proceed with regime filter + "
            "threshold approach. Don't trade every bar."
        )
    else:
        verdict = "PASS"
        reason = f"{n_linear} verified features found. Proceed with strategy modeling."

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
        "bonferroni_alpha": round(bonf_alpha, 8),
        "n_features": n_total,
        "n_verified_signal": int(n_linear),
        "n_nonlinear_signal": int(n_nonlinear),
        "verdict": verdict,
        "reason": reason,
        "top_features": results.head(10)["feature"].tolist(),
        "top_correlations": results.head(10)["pearson_r"].tolist(),
        "csv_path": save_path,
    }
    with open(os.path.join(OUTPUT_DIR, f"diagnostic_{args.symbol}.json"), "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n  Report: {save_path}")


if __name__ == "__main__":
    main()
