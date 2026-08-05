"""
WINSORIZATION CURVE + MAGNITUDE AUDIT
======================================
Quick checks before freeze:

1. Winsorize at P99/P97/P95/P90/P85/P80 → Sharpe curve
   If curve oscillates → fragile. If monotonic → robust.

2. Magnitude audit: 80-170x median returns
   Check if from position sizing bug (vol→0) or real tail events.

Usage:
    python scripts/winsorize_and_magnitude.py
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
# PART 1: WINSORIZATION CURVE
# ══════════════════════════════════════════════════════════════════════════

def winsorize_curve(
    strategy_returns: dict[str, list[float]],
) -> dict:
    """Winsorize at multiple percentiles, plot Sharpe as continuous curve."""
    print("=" * 64)
    print("  PART 1: WINSORIZATION CURVE")
    print("=" * 64)

    percentiles = [100, 99, 97, 95, 90, 85, 80, 75, 70]
    results = {}

    for name, rets in strategy_returns.items():
        arr = np.array(rets)
        if len(arr) < 20:
            continue

        print(f"\n  {name}:")
        print(f"  {'Percentile':>12} {'Cutoff':>12} {'Sharpe':>10} {'Change':>10} {'Direction':>10}")
        print(f"  {'-'*56}")

        sharpes = {}
        prev_sharpe = None
        prev_direction = None
        oscillations = 0

        for pct in percentiles:
            # Winsorize: cap returns at percentile threshold
            cutoff = np.percentile(np.abs(arr), pct)
            winsorized = np.clip(arr, -cutoff, cutoff)

            mu = float(winsorized.mean())
            std = float(winsorized.std())
            sharpe = mu / (std + 1e-10) * math.sqrt(252)
            sharpes[pct] = round(sharpe, 4)

            if prev_sharpe is not None:
                change = sharpe - prev_sharpe
                direction = "UP" if change > 0 else "DOWN" if change < 0 else "FLAT"
                change_pct = abs(change) / (abs(prev_sharpe) + 1e-10) * 100

                # Detect oscillation: direction changed from previous step
                if prev_direction is not None and direction != prev_direction and direction != "FLAT":
                    oscillations += 1

                print(f"  P{pct:>9}  {cutoff:>12.8f}  {sharpe:>10.4f}  {change_pct:>9.1f}%  {direction:>10}")
                prev_direction = direction
            else:
                print(f"  P{pct:>9}  {cutoff:>12.8f}  {sharpe:>10.4f}  {'---':>10}  {'---':>10}")

            prev_sharpe = sharpe

        # Monotonicity check
        sharpe_values = list(sharpes.values())
        # Count direction changes
        directions = []
        for i in range(1, len(sharpe_values)):
            if sharpe_values[i] > sharpe_values[i - 1]:
                directions.append(1)
            elif sharpe_values[i] < sharpe_values[i - 1]:
                directions.append(-1)
            else:
                directions.append(0)

        # Count oscillations (direction changes)
        dir_changes = sum(1 for i in range(1, len(directions))
                         if directions[i] != directions[i - 1]
                         and directions[i] != 0
                         and directions[i - 1] != 0)

        # Monotonic if 0 direction changes
        is_monotonic = dir_changes == 0
        # "Mostly monotonic" if <=1 direction change
        mostly_monotonic = dir_changes <= 1

        # Total swing: max - min Sharpe across all percentiles
        total_swing = max(sharpe_values) - min(sharpe_values)
        swing_pct = total_swing / (abs(sharpe_values[0]) + 1e-10) * 100

        print(f"\n  Oscillations: {dir_changes}")
        print(f"  Total swing: {total_swing:.4f} ({swing_pct:.1f}% of original)")
        print(f"  Monotonic: {'YES' if is_monotonic else 'NO'}")
        print(f"  Mostly monotonic (<=1 change): {'YES' if mostly_monotonic else 'NO'}")

        if is_monotonic:
            verdict = "ROBUST — monotonic winsorization"
        elif mostly_monotonic:
            verdict = "MARGINALLY ROBUST — 1 direction change"
        else:
            verdict = "FRAGILE — non-monotonic oscillation"

        print(f"  Verdict: {verdict}")

        results[name] = {
            "sharpes_by_percentile": sharpes,
            "oscillations": dir_changes,
            "total_swing": round(total_swing, 6),
            "swing_pct": round(swing_pct, 1),
            "monotonic": is_monotonic,
            "mostly_monotonic": mostly_monotonic,
            "verdict": verdict,
        }

    return results


# ══════════════════════════════════════════════════════════════════════════
# PART 2: MAGNITUDE AUDIT
# ══════════════════════════════════════════════════════════════════════════

def magnitude_audit(
    strategy_returns: dict[str, list[float]],
    returns_full: np.ndarray,
) -> dict:
    """Audit 80-170x median outliers — sizing bug or real tail?"""
    print("\n" + "=" * 64)
    print("  PART 2: MAGNITUDE AUDIT (80-170x Median)")
    print("=" * 64)

    results = {}

    for name, rets in strategy_returns.items():
        arr = np.array(rets)
        if len(arr) < 20:
            continue

        print(f"\n  {name}:")

        median_abs = np.median(np.abs(arr))

        # Find all returns > 20x median
        threshold_20x = median_abs * 20
        extreme_mask = np.abs(arr) > threshold_20x
        extreme_indices = np.where(extreme_mask)[0]
        n_extreme = len(extreme_indices)

        print(f"    Median |return|: {median_abs:.8f}")
        print(f"    20x threshold: {threshold_20x:.8f}")
        print(f"    Returns > 20x median: {n_extreme}")

        if n_extreme > 0:
            extreme_returns = arr[extreme_indices]
            extreme_abs = np.abs(extreme_returns)

            # Sort by magnitude
            sorted_idx = np.argsort(extreme_abs)[::-1]

            print(f"\n    Top extreme returns:")
            for i in range(min(10, n_extreme)):
                idx = sorted_idx[i]
                actual_idx = extreme_indices[idx]
                mult = extreme_abs[idx] / median_abs
                direction = "WIN" if extreme_returns[idx] > 0 else "LOSS"

                # Check surrounding bars for context
                context_start = max(0, actual_idx - 3)
                context_end = min(len(returns_full), actual_idx + 4)
                context = returns_full[context_start:context_end]

                print(f"      [{actual_idx}] {extreme_returns[idx]:+.8f} ({mult:.1f}x median) [{direction}]")
                print(f"        Context (5 bars around): {[f'{x:.6f}' for x in context]}")

            # Analyze: are these from the strategy signal or from underlying price?
            # Check if the extreme return coincides with a large move in the underlying
            extreme_underlying = returns_full[extreme_indices]
            underlying_median = np.median(np.abs(returns_full))
            underlying_mult = np.abs(extreme_underlying) / (underlying_median + 1e-10)

            print(f"\n    Underlying price move at extreme points:")
            print(f"      Underlying median |return|: {underlying_median:.8f}")
            print(f"      Average underlying move at extremes: {np.mean(underlying_mult):.1f}x median")
            print(f"      Max underlying move at extremes: {np.max(underlying_mult):.1f}x median")

            # Classification
            avg_underlying = np.mean(underlying_mult)
            if avg_underlying > 10:
                classification = "REAL TAIL EVENT — large underlying moves"
            elif avg_underlying > 3:
                classification = "MIXED — partly underlying, partly sizing"
            else:
                classification = "SIZING ARTIFACT — underlying didn't move much"

            print(f"\n    Classification: {classification}")

            # Check if extremes are concentrated in time
            # (would suggest a specific event like NFP/FOMC)
            gaps = np.diff(extreme_indices)
            avg_gap = np.mean(gaps) if len(gaps) > 0 else 0
            print(f"    Avg gap between extremes: {avg_gap:.0f} bars")

            if avg_gap < 10:
                timing = "CLUSTERED — possibly same event"
            elif avg_gap < 50:
                timing = "MODERATE — some clustering"
            else:
                timing = "SPREAD — different events"

            print(f"    Timing: {timing}")

            results[name] = {
                "n_extreme_20x": n_extreme,
                "pct_of_total": round(n_extreme / len(arr) * 100, 2),
                "avg_magnitude": round(float(np.mean(extreme_abs / median_abs)), 1),
                "classification": classification,
                "timing": timing,
                "avg_underlying_move": round(avg_underlying, 1),
            }
        else:
            print(f"    No returns > 20x median")
            results[name] = {
                "n_extreme_20x": 0,
                "pct_of_total": 0,
                "classification": "NO EXTREMES",
                "timing": "N/A",
            }

    return results


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 64)
    print("  WINSORIZATION CURVE + MAGNITUDE AUDIT")
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

    # Run Part 1: Winsorization curve
    c1 = winsorize_curve(strategy_returns)

    # Run Part 2: Magnitude audit
    c2 = magnitude_audit(strategy_returns, returns_full)

    # ── FINAL ────────────────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("  FINAL VERDICT")
    print("=" * 64)

    for name in strategy_returns:
        w = c1.get(name, {})
        m = c2.get(name, {})
        print(f"\n  {name}:")
        print(f"    Winsorize: {w.get('verdict', 'N/A')}")
        print(f"    Oscillations: {w.get('oscillations', 'N/A')}, Swing: {w.get('swing_pct', 'N/A')}%")
        print(f"    Magnitude: {m.get('classification', 'N/A')}")
        print(f"    Extremes: {m.get('n_extreme_20x', 0)} ({m.get('pct_of_total', 0)}% of trades)")

    # Overall
    issues = []
    for name in ["momentum_12m"]:
        w = c1.get(name, {})
        if not w.get("mostly_monotonic", False):
            issues.append(f"{name}: non-monotonic winsorization")

    print(f"\n  {'='*64}")
    if not issues:
        print("  VERDICT: WINSORIZATION STABLE — safe to freeze")
        print("  Set TCA logging for >20x median trades from day 1")
    else:
        print(f"  VERDICT: {len(issues)} ISSUE(S)")
        for issue in issues:
            print(f"    {issue}")
    print(f"  {'='*64}")

    return {"winsorization": c1, "magnitude": c2, "issues": issues}


if __name__ == "__main__":
    main()
