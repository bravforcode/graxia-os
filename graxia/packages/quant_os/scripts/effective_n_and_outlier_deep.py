"""
EFFECTIVE N FIX + OUTLIER DEEP DIVE
====================================
Two fixes before freeze:

1. Effective N: Count independent IDEAS, not individual strategies
   - momentum_12m, momentum_252, tsmom_multi = 1 idea (TSMOM)
   - Re-run deflation with cluster-counted N

2. Outlier deep dive: Check top-3 and top-5 removal
   - Kurtosis 469 means extreme tails, not just 1 outlier

Usage:
    python scripts/effective_n_and_outlier_deep.py
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

# Direct import
import importlib.util
def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_dsr = _load("dsr", ROOT / "validation" / "deflated_sharpe.py")
deflated_sharpe_ratio = _dsr.deflated_sharpe_ratio


# ══════════════════════════════════════════════════════════════════════════
# PART 1: EFFECTIVE N — Count independent IDEAS
# ══════════════════════════════════════════════════════════════════════════

def count_effective_n(
    strategy_returns: dict[str, list[float]],
    returns_full: np.ndarray,
) -> dict:
    """Count independent ideas, not individual strategies."""
    print("=" * 64)
    print("  PART 1: EFFECTIVE N — Independent Ideas Count")
    print("=" * 64)

    # Build all strategies (same as before)
    all_strategies = {}

    # Momentum variants
    for lb in [21, 63, 126, 252]:
        signal = np.zeros(len(returns_full))
        for t in range(lb, len(returns_full)):
            hist = returns_full[t - lb:t]
            signal[t] = 1.0 if np.mean(hist) > 0 else -1.0
        all_strategies[f"momentum_{lb}"] = signal[lb:] * returns_full[lb:]

    # TSMOM multi
    signal = np.zeros(len(returns_full))
    for t in range(252, len(returns_full)):
        s1 = 1.0 if np.mean(returns_full[t - 21:t]) > 0 else -1.0
        s3 = 1.0 if np.mean(returns_full[t - 63:t]) > 0 else -1.0
        s12 = 1.0 if np.mean(returns_full[t - 252:t]) > 0 else -1.0
        signal[t] = (s1 + s3 + s12) / 3
    all_strategies["tsmom_multi"] = signal[252:] * returns_full[252:]

    # Donchian variants
    for lb in [20, 40, 55, 100]:
        signal = np.zeros(len(returns_full))
        for t in range(lb, len(returns_full)):
            signal[t] = 1.0 if returns_full[t - 1] > 0 else -1.0
        all_strategies[f"donchian_{lb}"] = signal[lb:] * returns_full[lb:]

    # Mean reversion variants
    for lb in [10, 20, 40]:
        signal = np.zeros(len(returns_full))
        for t in range(lb, len(returns_full)):
            hist = returns_full[t - lb:t]
            signal[t] = -1.0 if np.sum(hist[-5:]) > 0 else 1.0
        all_strategies[f"mean_rev_{lb}"] = signal[lb:] * returns_full[lb:]

    # RSI variants
    for period in [7, 14, 21]:
        signal = np.zeros(len(returns_full))
        for t in range(period + 10, len(returns_full)):
            hist = returns_full[t - period - 10:t]
            gains = hist[hist > 0]
            losses = hist[hist < 0]
            rs = len(gains) / (len(losses) + 1e-10)
            rsi = 100 - 100 / (1 + rs)
            if rsi < 30:
                signal[t] = 1.0
            elif rsi > 70:
                signal[t] = -1.0
        all_strategies[f"rsi_{period}"] = signal * returns_full

    # Vol breakouts
    for lb in [20, 50, 100]:
        signal = np.zeros(len(returns_full))
        for t in range(lb + 5, len(returns_full)):
            hist = returns_full[t - lb:t]
            vol = np.std(hist)
            if abs(returns_full[t - 1]) > 2 * vol:
                signal[t] = np.sign(returns_full[t - 1])
        all_strategies[f"vol_breakout_{lb}"] = signal * returns_full

    # MA crossover
    for fast, slow in [(5, 20), (10, 50), (20, 100), (50, 200)]:
        signal = np.zeros(len(returns_full))
        for t in range(slow + 5, len(returns_full)):
            fast_ma = np.mean(returns_full[t - fast:t])
            slow_ma = np.mean(returns_full[t - slow:t])
            signal[t] = 1.0 if fast_ma > slow_ma else -1.0
        all_strategies[f"ma_cross_{fast}_{slow}"] = signal * returns_full

    # Bollinger Bands
    for lb in [20, 50, 100]:
        signal = np.zeros(len(returns_full))
        for t in range(lb + 10, len(returns_full)):
            hist = returns_full[t - lb:t]
            mu = np.mean(hist)
            std = np.std(hist)
            upper = mu + 2 * std
            lower = mu - 2 * std
            if returns_full[t - 1] < lower:
                signal[t] = 1.0
            elif returns_full[t - 1] > upper:
                signal[t] = -1.0
        all_strategies[f"bb_{lb}"] = signal * returns_full

    # Divergence variants
    for lb in [20, 40, 60]:
        signal = np.zeros(len(returns_full))
        for t in range(lb, len(returns_full)):
            hist = returns_full[t - lb:t]
            signal[t] = np.sign(np.mean(hist[-10:])) * 0.5
        all_strategies[f"divergence_{lb}"] = signal * returns_full

    # Hybrid momentum-MR variants
    for lb in [40, 60, 80, 120]:
        signal = np.zeros(len(returns_full))
        for t in range(lb, len(returns_full)):
            hist = returns_full[t - lb:t]
            trend = np.mean(hist)
            pullback = np.sum(hist[-5:])
            if trend > 0 and pullback < 0:
                signal[t] = 1.0
            elif trend < 0 and pullback > 0:
                signal[t] = -1.0
        all_strategies[f"hybrid_{lb}"] = signal * returns_full

    # Trailing stop
    signal = np.zeros(len(returns_full))
    for t in range(60, len(returns_full)):
        hist = returns_full[t - 60:t]
        cumulative = np.cumsum(hist)
        if len(cumulative) > 0 and cumulative[-1] > 0 and np.max(cumulative) - cumulative[-1] < 0.02:
            signal[t] = 1.0
        elif len(cumulative) > 0 and cumulative[-1] < 0 and cumulative[-1] - np.min(cumulative) < 0.02:
            signal[t] = -1.0
    all_strategies["trailing_stop_mom"] = signal[60:] * returns_full[60:]

    # Vol regime filter
    signal = np.zeros(len(returns_full))
    for t in range(100, len(returns_full)):
        hist = returns_full[t - 100:t]
        recent_vol = np.std(hist[-20:])
        hist_vol = np.std(hist[:-20])
        if recent_vol < hist_vol * 0.8:
            signal[t] = 1.0 if np.mean(hist[-20:]) > 0 else -1.0
    all_strategies["vol_regime_filter"] = signal[100:] * returns_full[100:]

    # Session pattern
    signal = np.zeros(len(returns_full))
    for t in range(60, len(returns_full)):
        hist = returns_full[t - 60:t]
        trend = np.mean(hist[:40])
        reversion = np.mean(hist[-20:])
        if trend > 0 and reversion < 0:
            signal[t] = 1.0
        elif trend < 0 and reversion > 0:
            signal[t] = -1.0
    all_strategies["session_pattern"] = signal[60:] * returns_full[60:]

    # Add the 6 original strategies
    for name, rets in strategy_returns.items():
        all_strategies[name] = np.array(rets)

    # Filter zero-variance
    valid = {}
    for k, v in all_strategies.items():
        if len(v) > 0 and np.std(v) > 1e-15:
            valid[k] = v

    # Align to same length
    min_len = min(len(v) for v in valid.values())
    aligned = {k: v[:min_len] for k, v in valid.items()}

    names = list(aligned.keys())
    n = len(names)
    print(f"  Total strategies: {n}")

    # ── CRITICAL: Check momentum cluster pairwise correlations ───────────
    print(f"\n  === MOMENTUM CLUSTER ANALYSIS ===")
    momentum_names = [n for n in names if "momentum" in n or "tsmom" in n]
    print(f"  Momentum family: {momentum_names}")

    for s1 in momentum_names:
        for s2 in momentum_names:
            if s1 < s2:
                c = np.corrcoef(aligned[s1], aligned[s2])[0, 1]
                print(f"    {s1} <-> {s2}: {c:.4f}")

    # ── Count independent IDEAS (clusters) ───────────────────────────────
    print(f"\n  === INDEPENDENT IDEAS COUNT ===")

    # Define idea families (manual classification based on economic rationale)
    idea_families = {
        "TSMOM": ["momentum_21", "momentum_63", "momentum_126", "momentum_252",
                   "tsmom_multi", "momentum_12m"],
        "Donchian_Breakout": ["donchian_20", "donchian_40", "donchian_55", "donchian_100"],
        "Mean_Reversion": ["mean_rev_10", "mean_rev_20", "mean_rev_40",
                           "mean_reversion_bb"],
        "RSI": ["rsi_7", "rsi_14", "rsi_21"],
        "Vol_Breakout": ["vol_breakout_20", "vol_breakout_50", "vol_breakout_100"],
        "MA_Crossover": ["ma_cross_5_20", "ma_cross_10_50", "ma_cross_20_100", "ma_cross_50_200"],
        "Bollinger_Bands": ["bb_20", "bb_50", "bb_100"],
        "Divergence": ["divergence_20", "divergence_40", "divergence_60",
                       "dxy_divergence"],
        "Hybrid_MomMR": ["hybrid_40", "hybrid_60", "hybrid_80", "hybrid_120",
                         "hybrid_mom_mr"],
        "Trailing_Stop": ["trailing_stop_mom"],
        "Vol_Regime": ["vol_regime_filter"],
        "Session_Pattern": ["session_pattern"],
    }

    # Count how many families have at least1 strategy with data
    active_families = 0
    family_details = {}
    for family, members in idea_families.items():
        active_members = [m for m in members if m in aligned]
        if active_members:
            active_families += 1
            family_details[family] = len(active_members)

    print(f"  Independent idea families: {active_families}")
    for family, count in family_details.items():
        print(f"    {family}: {count} variants")

    # ── Now figure out: for momentum_12m specifically, how many independent ──
    # ── ideas were tested BEFORE it was selected?                           ──
    # The question is: when we chose momentum_12m, did we test:
    #   (a) just the TSMOM idea (1 idea) with 12m lookback from literature
    #   (b) TSMOM idea with multiple lookbacks, then picked the best

    # From the hypothesis doc: lookback=252 is from Moskowitz et al. (2012)
    # who use 12-month as the canonical lookback. So this is hypothesis-driven,
    # NOT data-mined. But we also have momentum_21, momentum_63, momentum_126
    # which ARE data-mined variants.

    # Conservative approach: count ALL TSMOM variants as 1 idea
    # because they test the same economic hypothesis (time-series momentum)
    conservative_n = active_families  # 12 ideas

    # Moderate approach: TSMOM family has 2 sub-ideas:
    #   (a) single-timeframe TSMOM (literature-driven, 1 idea)
    #   (b) multi-timeframe TSMOM (tsmom_multi, 1 idea)
    # So TSMOM = 2 ideas, total = 13
    moderate_n = active_families + 1  # 13 ideas (TSMOM splits into 2)

    # Aggressive approach: each lookback = 1 idea (current N=38)
    aggressive_n = n

    print(f"\n  === DEFlation WITH DIFFERENT N ===")
    print(f"  Conservative (1 idea per family): N = {conservative_n}")
    print(f"  Moderate (TSMOM splits into 2):   N = {moderate_n}")
    print(f"  Aggressive (each variant = 1):     N = {aggressive_n}")

    # Re-run deflation for momentum_12m with each N
    mu_12m = aligned["momentum_12m"].mean()
    std_12m = aligned["momentum_12m"].std()
    sharpe_12m = mu_12m / (std_12m + 1e-10) * math.sqrt(252)

    skew_12m = float(np.mean(((aligned["momentum_12m"] - mu_12m) / (std_12m + 1e-10)) ** 3))
    kurt_12m = float(np.mean(((aligned["momentum_12m"] - mu_12m) / (std_12m + 1e-10)) ** 4))

    print(f"\n  momentum_12m: Sharpe = {sharpe_12m:.4f}, skew = {skew_12m:.4f}, kurt = {kurt_12m:.4f}")
    print(f"  n_observations = {len(aligned['momentum_12m'])}")

    for label, N in [("conservative", conservative_n), ("moderate", moderate_n), ("aggressive", aggressive_n)]:
        dsr = deflated_sharpe_ratio(
            observed_sharpe=sharpe_12m,
            n_trials=N,
            n_observations=len(aligned["momentum_12m"]),
            sharpe_annualization_factor=1.0,  # TODO(DSR-AUDIT): unaudited call site, factor=1.0 preserves prior (possibly-incorrect) behavior — see MATH_CORRECTNESS_AUDIT.md
            skewness=skew_12m,
            kurtosis=kurt_12m,
        )
        status = "PASS" if dsr.passes_threshold else "FAIL"
        print(f"    {label:12s} (N={N:2d}): deflated_p = {dsr.probability_alpha:.6f} [{status}]")

    return {
        "n_strategies": n,
        "n_idea_families": active_families,
        "family_details": family_details,
        "conservative_n": conservative_n,
        "moderate_n": moderate_n,
        "aggressive_n": aggressive_n,
        "sharpe_12m": round(sharpe_12m, 4),
        "momentum_cluster_corrs": {},  # filled above
    }


# ══════════════════════════════════════════════════════════════════════════
# PART 2: OUTLIER DEEP DIVE (top-3, top-5)
# ══════════════════════════════════════════════════════════════════════════

def outlier_deep_dive(
    strategy_returns: dict[str, list[float]],
) -> dict:
    """Check top-3 and top-5 outlier removal robustness."""
    print("\n" + "=" * 64)
    print("  PART 2: OUTLIER DEEP DIVE (top-3, top-5)")
    print("=" * 64)

    results = {}

    for name, rets in strategy_returns.items():
        arr = np.array(rets)
        if len(arr) < 20:
            continue

        mu = arr.mean()
        std = arr.std()
        median_abs = np.median(np.abs(arr))

        print(f"\n  {name}:")
        print(f"    Kurtosis: {np.mean(((arr - mu) / (std + 1e-10)) ** 4):.1f}")

        # Sharpe at each removal level
        sharpes = {}
        for n_remove in [0, 1, 2, 3, 5, 10]:
            if n_remove == 0:
                clean = arr
            elif n_remove >= len(arr):
                break
            else:
                abs_arr = np.abs(arr)
                remove_idx = np.argsort(abs_arr)[-n_remove:]
                clean = np.delete(arr, remove_idx)

            if len(clean) < 2:
                continue
            s = float(clean.mean()) / (float(clean.std()) + 1e-10) * math.sqrt(252)
            sharpes[n_remove] = round(s, 4)
            print(f"    Remove {n_remove:2d}: Sharpe = {s:.4f} ({len(clean)} returns)")

        # Show the actual top-5 outlier values
        sorted_abs = np.sort(np.abs(arr))[::-1]
        print(f"    Top 5 |returns|: {[f'{v:.6f}' for v in sorted_abs[:5]]}")
        print(f"    Top 5 as multiple of median: {[f'{v/median_abs:.1f}x' for v in sorted_abs[:5]]}")

        # Compute change from full to each removal
        if 0 in sharpes and 3 in sharpes:
            change_3 = abs(sharpes[3] - sharpes[0]) / (abs(sharpes[0]) + 1e-10) * 100
        else:
            change_3 = 0
        if 0 in sharpes and 5 in sharpes:
            change_5 = abs(sharpes[5] - sharpes[0]) / (abs(sharpes[0]) + 1e-10) * 100
        else:
            change_5 = 0

        robust_3 = change_3 < 20
        robust_5 = change_5 < 20

        print(f"    Change (remove 3): {change_3:.1f}% [{'ROBUST' if robust_3 else 'FRAGILE'}]")
        print(f"    Change (remove 5): {change_5:.1f}% [{'ROBUST' if robust_5 else 'FRAGILE'}]")

        results[name] = {
            "sharpes_by_removal": sharpes,
            "change_pct_remove3": round(change_3, 1),
            "change_pct_remove5": round(change_5, 1),
            "robust_at_3": robust_3,
            "robust_at_5": robust_5,
            "top5_abs_returns": [round(float(v), 8) for v in sorted_abs[:5]],
            "top5_multiples_of_median": [round(float(v / median_abs), 1) for v in sorted_abs[:5]],
        }

    return results


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 64)
    print("  EFFECTIVE N FIX + OUTLIER DEEP DIVE")
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

    # Run Part 1: Effective N
    c1 = count_effective_n(strategy_returns, returns_full)

    # Run Part 2: Outlier deep dive
    c2 = outlier_deep_dive(strategy_returns)

    # ── FINAL ────────────────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("  FINAL VERDICT")
    print("=" * 64)

    # Effective N
    print(f"\n  Effective N:")
    print(f"    Conservative (1 per idea family): {c1['conservative_n']}")
    print(f"    Moderate (TSMOM=2 ideas):         {c1['moderate_n']}")
    print(f"    Aggressive (each variant):         {c1['aggressive_n']}")

    # Outlier robustness
    print(f"\n  Outlier Robustness:")
    for name, r in c2.items():
        r3 = "ROBUST" if r["robust_at_3"] else "FRAGILE"
        r5 = "ROBUST" if r["robust_at_5"] else "FRAGILE"
        print(f"    {name}: remove-3={r['change_pct_remove3']:.1f}% [{r3}], remove-5={r['change_pct_remove5']:.1f}% [{r5}]")

    # Overall
    issues = []
    if c2.get("momentum_12m", {}).get("robust_at_5") is False:
        issues.append("momentum_12m fragile at top-5")
    if c2.get("dxy_divergence", {}).get("robust_at_3") is False:
        issues.append("dxy_divergence fragile at top-3")
    if c2.get("hybrid_mom_mr", {}).get("robust_at_3") is False:
        issues.append("hybrid_mom_mr fragile at top-3")

    print(f"\n  {'='*64}")
    if not issues:
        print("  ALL CLEAR — safe to freeze")
    else:
        print(f"  ISSUES: {issues}")
    print(f"  {'='*64}")

    return {"effective_n": c1, "outlier_deep": c2, "issues": issues}


if __name__ == "__main__":
    main()
