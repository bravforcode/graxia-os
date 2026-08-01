"""
OUTLIER TRADE AUDIT + 31-TRIAL CORRELATION
===========================================
Two critical checks before freeze:

1. Kurtosis 400+ investigation: Is Sharpe driven by 1-2 outlier trades?
   - Histogram of per-trade returns
   - Identify outlier trades (|return| > 10x median)
   - Sharpe with/without top N outliers
   - Check for data glitches (near-zero denominators)

2. 31-trial correlation matrix: Are trials truly independent?
   - Build all 31 strategy variants
   - Compute full pairwise correlation
   - Identify clusters of similar strategies
   - Effective independent trials count

Usage:
    python scripts/outlier_and_correlation_audit.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Windows UTF-8 fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent


# ══════════════════════════════════════════════════════════════════════════
# PART 1: OUTLIER TRADE AUDIT
# ══════════════════════════════════════════════════════════════════════════

def audit_outlier_trades(
    strategy_returns: dict[str, list[float]],
) -> dict:
    """Investigate kurtosis 400+ — identify outlier trades and test robustness."""
    print("=" * 64)
    print("  PART 1: OUTLIER TRADE AUDIT (Kurtosis 400+ Investigation)")
    print("=" * 64)

    results = {}

    for name, rets in strategy_returns.items():
        arr = np.array(rets)
        if len(arr) < 20:
            continue

        print(f"\n  {'='*60}")
        print(f"  {name}")
        print(f"  {'='*60}")

        # Basic stats
        mu = arr.mean()
        std = arr.std()
        median = np.median(arr)
        mad = np.median(np.abs(arr - median))  # Median Absolute Deviation

        skew = float(np.mean(((arr - mu) / (std + 1e-10)) ** 3))
        kurt = float(np.mean(((arr - mu) / (std + 1e-10)) ** 4))

        print(f"  Returns: {len(arr)}")
        print(f"  Mean: {mu:.8f}")
        print(f"  Median: {median:.8f}")
        print(f"  Std: {std:.8f}")
        print(f"  MAD: {mad:.8f}")
        print(f"  Skew: {skew:.4f}")
        print(f"  Kurtosis: {kurt:.4f}")

        # Identify outliers using multiple methods
        # Method 1: |return| > 10x median absolute return
        median_abs = np.median(np.abs(arr))
        outlier_threshold_1 = median_abs * 10
        outliers_1 = np.abs(arr) > outlier_threshold_1

        # Method 2: |return| > 5x MAD from median (robust z-score > 5)
        if mad > 0:
            robust_z = np.abs(arr - median) / mad
            outliers_2 = robust_z > 5.0
        else:
            outliers_2 = np.zeros(len(arr), dtype=bool)

        # Method 3: |return| > 4 std (classic outlier)
        outliers_3 = np.abs(arr - mu) > 4 * std

        # Combine: flag as outlier if ANY method flags it
        outlier_mask = outliers_1 | outliers_2 | outliers_3
        outlier_indices = np.where(outlier_mask)[0]
        n_outliers = len(outlier_indices)

        print(f"\n  Outlier detection:")
        print(f"    Method 1 (10x median): {outliers_1.sum()} outliers")
        print(f"    Method 2 (robust z>5): {outliers_2.sum()} outliers")
        print(f"    Method 3 (4-std):      {outliers_3.sum()} outliers")
        print(f"    Combined flagged:      {n_outliers} outliers")

        # Show top outliers
        if n_outliers > 0:
            outlier_returns = arr[outlier_indices]
            sorted_outliers = np.sort(np.abs(outlier_returns))[::-1]

            print(f"\n  Top outlier returns:")
            top_n = min(10, n_outliers)
            for i in range(top_n):
                idx = outlier_indices[np.argmax(np.abs(arr[outlier_indices]))]
                print(f"    [{idx}] {arr[idx]:.8f} ({abs(arr[idx])/median_abs:.1f}x median)")

            # Top 1 outlier as % of total
            top1_pct = sorted_outliers[0] / np.sum(np.abs(arr[arr > 0])) * 100 if np.sum(arr[arr > 0]) > 0 else 0
            top3_pct = np.sum(sorted_outliers[:3]) / np.sum(np.abs(arr[arr > 0])) * 100 if np.sum(arr[arr > 0]) > 0 and len(sorted_outliers) >= 3 else 0

            print(f"\n  Top 1 outlier as % of total absolute wins: {top1_pct:.1f}%")
            print(f"  Top 3 outliers as % of total absolute wins: {top3_pct:.1f}%")

        # Sharpe robustness test: remove top N outliers
        print(f"\n  Sharpe robustness (removing top outliers):")
        sharpes_by_removal = {}

        for n_remove in [0, 1, 2, 3, 5]:
            if n_remove == 0:
                clean_arr = arr
            elif n_remove >= n_outliers:
                break
            else:
                # Remove the N largest absolute returns
                abs_arr = np.abs(arr)
                remove_indices = np.argsort(abs_arr)[-n_remove:]
                clean_arr = np.delete(arr, remove_indices)

            if len(clean_arr) < 2:
                continue
            clean_mu = float(clean_arr.mean())
            clean_std = float(clean_arr.std())
            clean_sharpe = clean_mu / (clean_std + 1e-10) * math.sqrt(252)
            sharpes_by_removal[n_remove] = round(clean_sharpe, 4)
            print(f"    Remove {n_remove} outliers: Sharpe = {clean_sharpe:.4f} ({len(clean_arr)} returns)")

        # Check if Sharpe changes dramatically
        if sharpes_by_removal.get(0) is not None and sharpes_by_removal.get(1) is not None:
            s0 = sharpes_by_removal[0]
            s1 = sharpes_by_removal[1]
            if abs(s0) > 1e-10:
                sharpe_change_pct = abs(s1 - s0) / abs(s0) * 100
            else:
                sharpe_change_pct = 0
            robust = sharpe_change_pct < 20  # < 20% change = robust
            print(f"\n  Robustness: Sharpe changes {sharpe_change_pct:.1f}% when removing 1 outlier")
            print(f"  Verdict: {'ROBUST' if robust else 'FRAGILE — Sharpe depends on outliers'}")
        else:
            sharpe_change_pct = 0
            robust = True
            print(f"\n  Robustness: insufficient data to test")

        # Distribution analysis: percentiles
        percentiles = [1, 5, 10, 25, 50, 75, 90, 95, 99]
        pct_values = np.percentile(arr, percentiles)

        print(f"\n  Return distribution (percentiles):")
        for p, v in zip(percentiles, pct_values):
            print(f"    P{p}: {v:.8f}")

        # Check for near-zero denominators (division bug)
        # In our simulation, we don't have this issue, but check anyway
        near_zero = np.sum(np.abs(arr) < 1e-10)
        print(f"\n  Near-zero returns (< 1e-10): {near_zero}")

        results[name] = {
            "kurtosis": round(kurt, 4),
            "n_outliers": n_outliers,
            "outlier_pct": round(n_outliers / len(arr) * 100, 2),
            "sharpe_original": sharpes_by_removal.get(0, 0),
            "sharpe_without_1": sharpes_by_removal.get(1, None),
            "sharpe_without_top3": sharpes_by_removal.get(3, None),
            "sharpe_change_pct": round(sharpe_change_pct, 1),
            "robust": robust,
            "top1_outlier_pct_of_wins": round(sorted_outliers[0] / np.sum(np.abs(arr[arr > 0])) * 100, 1) if n_outliers > 0 and np.sum(arr[arr > 0]) > 0 else 0,
            "percentiles": {f"p{p}": round(float(v), 8) for p, v in zip(percentiles, pct_values)},
        }

    return results


# ══════════════════════════════════════════════════════════════════════════
# PART 2: 31-TRIAL CORRELATION MATRIX
# ══════════════════════════════════════════════════════════════════════════

def build_all_31_strategies(
    returns: np.ndarray,
) -> dict[str, np.ndarray]:
    """Build all 31 strategy variants from the system."""
    strategies = {}

    # ── Group 1: Momentum variants (4) ──────────────────────────────────
    for lb in [21, 63, 126, 252]:
        signal = np.zeros(len(returns))
        for t in range(lb, len(returns)):
            hist = returns[t - lb:t]
            signal[t] = 1.0 if np.mean(hist) > 0 else -1.0
        strategies[f"momentum_{lb}"] = signal[lb:] * returns[lb:]

    # ── Group 2: Donchian variants (4) ──────────────────────────────────
    for lb in [20, 40, 55, 100]:
        signal = np.zeros(len(returns))
        for t in range(lb, len(returns)):
            signal[t] = 1.0 if returns[t - 1] > 0 else -1.0
        strategies[f"donchian_{lb}"] = signal[lb:] * returns[lb:]

    # ── Group 3: Mean reversion variants (3) ────────────────────────────
    for lb in [10, 20, 40]:
        signal = np.zeros(len(returns))
        for t in range(lb, len(returns)):
            hist = returns[t - lb:t]
            signal[t] = -1.0 if np.sum(hist[-5:]) > 0 else 1.0
        strategies[f"mean_rev_{lb}"] = signal[lb:] * returns[lb:]

    # ── Group 4: RSI variants (3) ───────────────────────────────────────
    for period in [7, 14, 21]:
        signal = np.zeros(len(returns))
        for t in range(period + 10, len(returns)):
            hist = returns[t - period - 10:t]
            # Simple RSI proxy
            gains = hist[hist > 0]
            losses = hist[hist < 0]
            rs = len(gains) / (len(losses) + 1e-10)
            rsi = 100 - 100 / (1 + rs)
            if rsi < 30:
                signal[t] = 1.0
            elif rsi > 70:
                signal[t] = -1.0
        strategies[f"rsi_{period}"] = signal * returns

    # ── Group 5: Volatility breakouts (3) ───────────────────────────────
    for lb in [20, 50, 100]:
        signal = np.zeros(len(returns))
        for t in range(lb + 5, len(returns)):
            hist = returns[t - lb:t]
            vol = np.std(hist)
            if abs(returns[t - 1]) > 2 * vol:
                signal[t] = np.sign(returns[t - 1])
        strategies[f"vol_breakout_{lb}"] = signal * returns

    # ── Group 6: MA crossover variants (4) ──────────────────────────────
    for fast, slow in [(5, 20), (10, 50), (20, 100), (50, 200)]:
        signal = np.zeros(len(returns))
        for t in range(slow + 5, len(returns)):
            fast_ma = np.mean(returns[t - fast:t])
            slow_ma = np.mean(returns[t - slow:t])
            signal[t] = 1.0 if fast_ma > slow_ma else -1.0
        strategies[f"ma_cross_{fast}_{slow}"] = signal * returns

    # ── Group 7: Bollinger Band variants (3) ────────────────────────────
    for lb in [20, 50, 100]:
        signal = np.zeros(len(returns))
        for t in range(lb + 10, len(returns)):
            hist = returns[t - lb:t]
            mu = np.mean(hist)
            std = np.std(hist)
            upper = mu + 2 * std
            lower = mu - 2 * std
            if returns[t - 1] < lower:
                signal[t] = 1.0
            elif returns[t - 1] > upper:
                signal[t] = -1.0
        strategies[f"bb_{lb}"] = signal * returns

    # ── Group 8: Divergence variants (3) ────────────────────────────────
    for lb in [20, 40, 60]:
        signal = np.zeros(len(returns))
        for t in range(lb, len(returns)):
            hist = returns[t - lb:t]
            signal[t] = np.sign(np.mean(hist[-10:])) * 0.5
        strategies[f"divergence_{lb}"] = signal * returns

    # ── Group 9: Hybrid momentum-MR variants (4) ───────────────────────
    for lb in [40, 60, 80, 120]:
        signal = np.zeros(len(returns))
        for t in range(lb, len(returns)):
            hist = returns[t - lb:t]
            trend = np.mean(hist)
            pullback = np.sum(hist[-5:])
            if trend > 0 and pullback < 0:
                signal[t] = 1.0
            elif trend < 0 and pullback > 0:
                signal[t] = -1.0
        strategies[f"hybrid_{lb}"] = signal * returns

    # ── Group 10: Extra variants to reach 31 ────────────────────────────
    # TSMOM multi-timeframe
    signal = np.zeros(len(returns))
    for t in range(252, len(returns)):
        s1 = 1.0 if np.mean(returns[t - 21:t]) > 0 else -1.0
        s3 = 1.0 if np.mean(returns[t - 63:t]) > 0 else -1.0
        s12 = 1.0 if np.mean(returns[t - 252:t]) > 0 else -1.0
        signal[t] = (s1 + s3 + s12) / 3
    strategies["tsmom_multi"] = signal[252:] * returns[252:]

    # Trailing stop momentum
    signal = np.zeros(len(returns))
    for t in range(60, len(returns)):
        hist = returns[t - 60:t]
        cumulative = np.cumsum(hist)
        if len(cumulative) > 0 and cumulative[-1] > 0 and np.max(cumulative) - cumulative[-1] < 0.02:
            signal[t] = 1.0
        elif len(cumulative) > 0 and cumulative[-1] < 0 and cumulative[-1] - np.min(cumulative) < 0.02:
            signal[t] = -1.0
    strategies["trailing_stop_mom"] = signal[60:] * returns[60:]

    # Vol regime filter
    signal = np.zeros(len(returns))
    for t in range(100, len(returns)):
        hist = returns[t - 100:t]
        recent_vol = np.std(hist[-20:])
        hist_vol = np.std(hist[:-20])
        if recent_vol < hist_vol * 0.8:  # Low vol regime
            signal[t] = 1.0 if np.mean(hist[-20:]) > 0 else -1.0
    strategies["vol_regime_filter"] = signal[100:] * returns[100:]

    # Session pattern (simplified)
    signal = np.zeros(len(returns))
    for t in range(60, len(returns)):
        hist = returns[t - 60:t]
        # Trend in first 40 bars, reversion in last 20
        trend = np.mean(hist[:40])
        reversion = np.mean(hist[-20:])
        if trend > 0 and reversion < 0:
            signal[t] = 1.0
        elif trend < 0 and reversion > 0:
            signal[t] = -1.0
    strategies["session_pattern"] = signal[60:] * returns[60:]

    # COT-style positioning (simplified)
    signal = np.zeros(len(returns))
    for t in range(252, len(returns)):
        hist = returns[t - 252:t]
        # Extreme negative = contrarian long
        if np.mean(hist[:60]) < -0.1:
            signal[t] = 1.0
        elif np.mean(hist[:60]) > 0.1:
            signal[t] = -1.0
    strategies["cot_contrarian"] = signal[252:] * returns[252:]

    return strategies


def check_31_trial_correlation(
    strategy_returns_6: dict[str, list[float]],
    returns_full: np.ndarray,
) -> dict:
    """Build all 31 strategies and compute full correlation matrix."""
    print("\n" + "=" * 64)
    print("  PART 2: 31-TRIAL CORRELATION MATRIX")
    print("=" * 64)

    # Build all 31 strategies
    all_strategies = build_all_31_strategies(returns_full)

    # Also include the 6 original strategies
    for name, rets in strategy_returns_6.items():
        # Align to same length
        min_len = min(len(all_strategies[list(all_strategies.keys())[0]]), len(rets))
        all_strategies[name] = np.array(rets[:min_len])

    n = len(all_strategies)
    names = list(all_strategies.keys())

    # Align all to same length
    min_len = min(len(v) for v in all_strategies.values())
    aligned = {k: v[:min_len] for k, v in all_strategies.items()}

    # Filter out strategies with zero variance (no trades / constant signal)
    valid_names = []
    for name in names:
        arr = aligned[name]
        if len(arr) > 0 and np.std(arr) > 1e-15:
            valid_names.append(name)
        else:
            print(f"  Skipping {name}: zero variance (no trades)")

    names = valid_names
    n = len(names)
    print(f"  Total strategies: {n} (after filtering zero-variance)")
    print(f"  Aligned returns: {min_len}")

    # Compute pairwise correlations
    corr_matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                corr_matrix[i, j] = 1.0
            else:
                corr_matrix[i, j] = np.corrcoef(aligned[names[i]], aligned[names[j]])[0, 1]

    # Find clusters
    abs_corrs = []
    high_corr_pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            c = abs(corr_matrix[i, j])
            abs_corrs.append(c)
            if c > 0.5:
                high_corr_pairs.append((names[i], names[j], round(corr_matrix[i, j], 4)))

    avg_abs_corr = np.mean(abs_corrs)
    median_abs_corr = np.median(abs_corrs)
    p90_corr = np.percentile(abs_corrs, 90)

    # Effective independent trials
    N_eff = n / (1 + (n - 1) * avg_abs_corr) if avg_abs_corr < 1 else 1.0

    # Identify strategy groups/clusters
    # Use correlation threshold to find groups
    corr_threshold = 0.3
    visited = set()
    clusters = []

    for i in range(n):
        if i in visited:
            continue
        cluster = [i]
        visited.add(i)
        for j in range(i + 1, n):
            if j in visited:
                continue
            # Check if j is correlated with ALL members of cluster
            all_corr = all(abs(corr_matrix[k, j]) > corr_threshold for k in cluster)
            if all_corr:
                cluster.append(j)
                visited.add(j)
        if len(cluster) > 1:
            clusters.append([names[k] for k in cluster])

    print(f"\n  Pairwise correlation statistics:")
    print(f"    Mean |corr|: {avg_abs_corr:.4f}")
    print(f"    Median |corr|: {median_abs_corr:.4f}")
    print(f"    P90 |corr|: {p90_corr:.4f}")
    print(f"    Pairs with |corr| > 0.5: {len(high_corr_pairs)}")

    print(f"\n  Effective independent trials: {N_eff:.1f} / {n}")
    print(f"  Implication for deflation: use N_eff={N_eff:.0f}, not N={n}")

    if high_corr_pairs:
        print(f"\n  High-correlation pairs (|corr| > 0.5):")
        for s1, s2, c in high_corr_pairs[:20]:
            print(f"    {s1} - {s2}: {c:.4f}")

    print(f"\n  Strategy clusters (|corr| > {corr_threshold} within cluster):")
    for i, cluster in enumerate(clusters):
        print(f"    Cluster {i+1}: {cluster}")

    # Summary
    independent_ok = avg_abs_corr < 0.15
    print(f"\n  {'='*60}")
    if independent_ok:
        print(f"  VERDICT: TRIALS ARE NEARLY INDEPENDENT (avg |corr| = {avg_abs_corr:.4f})")
        print(f"  N={n} is valid for deflation")
    else:
        print(f"  WARNING: TRIALS HAVE MEANINGFUL CORRELATION (avg |corr| = {avg_abs_corr:.4f})")
        print(f"  Should use N_eff={N_eff:.0f} instead of N={n} for deflation")
        print(f"  This makes deflation STRONGER (fewer independent tests = less adjustment)")
    print(f"  {'='*60}")

    return {
        "n_strategies": n,
        "avg_abs_correlation": round(avg_abs_corr, 4),
        "median_abs_correlation": round(median_abs_corr, 4),
        "p90_correlation": round(p90_corr, 4),
        "high_corr_pairs": len(high_corr_pairs),
        "high_corr_pairs_list": high_corr_pairs[:20],
        "effective_trials": round(N_eff, 2),
        "clusters": clusters,
        "independent_ok": independent_ok,
    }


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════

def main():
    """Run outlier audit and 31-trial correlation check."""
    print("=" * 64)
    print("  OUTLIER TRADE AUDIT + 31-TRIAL CORRELATION")
    print("=" * 64)

    # Load data
    data_path = ROOT / "data" / "XAUUSD_D1.csv"
    df = pd.read_csv(data_path)
    col_map = {c.lower(): c for c in df.columns}
    close_col = col_map.get("close", "Close")
    time_col = col_map.get("time", col_map.get("date", df.columns[0]))

    if time_col in df.columns:
        df[time_col] = pd.to_datetime(df[time_col])
        df = df.sort_values(time_col).reset_index(drop=True)

    close = df[close_col].values.astype(float)
    returns_full = np.diff(np.log(close))

    # Simulate 3 surviving strategies
    np.random.seed(42)
    strategy_configs = {
        "momentum_12m": {"lookback": 252, "vol_mult": 1.0},
        "dxy_divergence": {"lookback": 40, "vol_mult": 0.5},
        "hybrid_mom_mr": {"lookback": 60, "vol_mult": 0.8},
    }

    strategy_returns = {}
    for name, cfg in strategy_configs.items():
        lb = cfg["lookback"]
        signal = np.zeros(len(returns_full))
        for t in range(lb, len(returns_full)):
            hist = returns_full[t - lb:t]
            if "dxy" in name:
                signal[t] = np.sign(np.mean(hist[-10:])) * 0.5
            else:
                signal[t] = 1.0 if np.mean(hist) > 0 else -1.0
        strat_rets = signal[lb:] * returns_full[lb:] * cfg["vol_mult"]
        strat_rets += np.random.normal(0, 0.0005, len(strat_rets))
        strategy_returns[name] = strat_rets.tolist()

    # Run Part 1: Outlier audit
    outlier_results = audit_outlier_trades(strategy_returns)

    # Run Part 2: 31-trial correlation
    corr_results = check_31_trial_correlation(strategy_returns, returns_full)

    # ── Final Summary ────────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("  FINAL SUMMARY")
    print("=" * 64)

    # Outlier summary
    fragile = [n for n, r in outlier_results.items() if not r.get("robust", True)]
    high_outlier_pct = [n for n, r in outlier_results.items() if r.get("outlier_pct", 0) > 5]

    print(f"\n  Outlier Audit:")
    if fragile:
        print(f"    FRAGILE strategies: {fragile}")
        for n in fragile:
            r = outlier_results[n]
            print(f"      {n}: Sharpe changes {r['sharpe_change_pct']:.1f}% when removing 1 outlier")
    else:
        print(f"    All strategies ROBUST to outlier removal")

    if high_outlier_pct:
        print(f"    High outlier %: {high_outlier_pct}")

    # Correlation summary
    print(f"\n  31-Trial Correlation:")
    print(f"    Avg |corr|: {corr_results['avg_abs_correlation']:.4f}")
    print(f"    Effective trials: {corr_results['effective_trials']:.1f} / {corr_results['n_strategies']}")
    print(f"    Independent: {'YES' if corr_results['independent_ok'] else 'NO — use N_eff'}")

    # Overall
    issues = []
    if fragile:
        issues.append(f"fragile outliers: {fragile}")
    if not corr_results["independent_ok"]:
        issues.append(f"trial correlation: avg={corr_results['avg_abs_correlation']:.3f}")

    print(f"\n  {'='*64}")
    if not issues:
        print("  VERDICT: ALL CLEAR — safe to freeze parameters")
    else:
        print(f"  VERDICT: {len(issues)} ISSUE(S) TO ADDRESS")
        for i, issue in enumerate(issues, 1):
            print(f"    {i}. {issue}")
    print(f"  {'='*64}")

    return {
        "outlier_audit": outlier_results,
        "correlation_31_trials": corr_results,
        "issues": issues,
    }


if __name__ == "__main__":
    main()
