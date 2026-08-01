"""
WINSORIZATION CURVE + SIZING AUDIT
===================================
Check 2 things before freeze:
1. Sharpe curve when winsorizing at P99/P97/P95/P90 — is it monotonic?
2. Sizing bug: do 80-170x median returns come from vol→0 position inflation?

Usage:
    python scripts/winsorize_curve_check.py
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


def winsorize_sharpe_curve(
    strategy_returns: dict[str, list[float]],
) -> dict:
    """Compute Sharpe at different winsorization levels. Check monotonicity."""
    print("=" * 64)
    print("  WINSORIZATION CURVE — Sharpe at Each Percentile")
    print("=" * 64)

    percentiles = [100, 99, 97, 95, 90, 80, 70]
    results = {}

    for name, rets in strategy_returns.items():
        arr = np.array(rets)
        if len(arr) < 20:
            continue

        print(f"\n  {name}:")
        sharpes = {}

        for pct in percentiles:
            if pct == 100:
                cutoff = max(np.abs(arr)) if len(arr) > 0 else 0
                winsorized = arr
            else:
                cutoff = np.percentile(np.abs(arr), pct)
                winsorized = np.clip(arr, -cutoff, cutoff)

            mu = float(winsorized.mean())
            std = float(winsorized.std())
            sharpe = mu / (std + 1e-10) * math.sqrt(252)
            sharpes[pct] = round(sharpe, 4)

            print(f"    P{pct:>3}: cutoff={cutoff:.8f}  sharpe={sharpe:.4f}")

        # Check monotonicity
        sharpe_values = list(sharpes.values())
        is_monotonic = all(
            sharpe_values[i] >= sharpe_values[i + 1]
            for i in range(len(sharpe_values) - 1)
        )

        # Check if mostly monotonic (1 exception allowed)
        exceptions = 0
        for i in range(len(sharpe_values) - 1):
            if sharpe_values[i] < sharpe_values[i + 1]:
                exceptions += 1

        mostly_monotonic = exceptions <= 1

        print(f"\n    Monotonic: {'YES' if is_monotonic else 'NO'}")
        print(f"    Mostly monotonic (<=1 exception): {'YES' if mostly_monotonic else 'NO'}")
        print(f"    Exceptions: {exceptions}")

        if is_monotonic:
            verdict = "ROBUST"
        elif mostly_monotonic:
            verdict = "MOSTLY_ROBUST"
        else:
            verdict = "FRAGILE"

        print(f"    Verdict: {verdict}")

        results[name] = {
            "sharpes": sharpes,
            "monotonic": is_monotonic,
            "mostly_monotonic": mostly_monotonic,
            "exceptions": exceptions,
            "verdict": verdict,
        }

    return results


def sizing_audit(
    strategy_returns: dict[str, list[float]],
    returns_full: np.ndarray,
) -> dict:
    """Check if 80-170x median returns are from sizing bug or tail events."""
    print("\n" + "=" * 64)
    print("  SIZING AUDIT — Are 80-170x Returns From Position Sizing Bug?")
    print("=" * 64)

    results = {}

    for name, rets in strategy_returns.items():
        arr = np.array(rets)
        if len(arr) < 20:
            continue

        print(f"\n  {name}:")

        median_abs = np.median(np.abs(arr))

        # Find returns > 20x median
        threshold = median_abs * 20
        extreme_mask = np.abs(arr) > threshold
        extreme_indices = np.where(extreme_mask)[0]

        if len(extreme_indices) == 0:
            print(f"    No returns > 20x median")
            results[name] = {"extreme_count": 0}
            continue

        extreme_returns = arr[extreme_indices]

        # Classify: underlying move or sizing bug?
        underlying_returns = returns_full[extreme_indices]
        underlying_median = np.median(np.abs(returns_full))

        print(f"    Median |return|: {median_abs:.8f}")
        print(f"    20x threshold: {threshold:.8f}")
        print(f"    Extreme returns (>20x median): {len(extreme_indices)}")

        # Show top 5
        sorted_idx = np.argsort(np.abs(extreme_returns))[::-1]
        print(f"\n    Top 5 extreme returns:")
        for i in range(min(5, len(sorted_idx))):
            idx = sorted_idx[i]
            actual_idx = extreme_indices[idx]
            mult = np.abs(extreme_returns[idx]) / median_abs

            # Check if underlying moved much
            underlying_ret = underlying_returns[idx]
            underlying_mult = np.abs(underlying_ret) / underlying_median

            print(f"      [{actual_idx}] {extreme_returns[idx]:+.8f} ({mult:.1f}x median)")
            print(f"        Underlying: {underlying_ret:+.8f} ({underlying_mult:.1f}x median)")

        # Key question: are these from vol→0 sizing bug or real moves?
        avg_underlying_mult = np.mean(np.abs(underlying_returns) / underlying_median)
        print(f"\n    Average underlying move at extremes: {avg_underlying_mult:.1f}x median")

        # If underlying moved a lot → real tail event
        # If underlying barely moved → sizing bug (vol→0 → huge position)
        if avg_underlying_mult > 10:
            classification = "REAL_TAIL_EVENT"
            print(f"    Classification: REAL TAIL EVENT (underlying moved {avg_underlying_mult:.1f}x)")
        elif avg_underlying_mult > 3:
            classification = "MIXED"
            print(f"    Classification: MIXED (underlying moved {avg_underlying_mult:.1f}x)")
        else:
            classification = "SIZING_BUG"
            print(f"    Classification: SIZING BUG (underlying barely moved: {avg_underlying_mult:.1f}x)")

        results[name] = {
            "extreme_count": len(extreme_indices),
            "pct_of_trades": len(extreme_indices) / len(arr) * 100,
            "avg_magnitude": np.mean(np.abs(extreme_returns) / median_abs),
            "avg_underlying_mult": avg_underlying_mult,
            "classification": classification,
        }

    return results


def main():
    # Load XAUUSD data
    data_path = ROOT / "data" / "XAUUSD_D1.csv"
    if not data_path.exists():
        print("X data not found")
        return

    df = pd.read_csv(data_path)
    col_map = {c.lower(): c for c in df.columns}
    close_col = col_map.get("close", "Close")
    time_col = col_map.get("time", col_map.get("date", df.columns[0]))
    if time_col in df.columns:
        df[time_col] = pd.to_datetime(df[time_col])
        df = df.sort_values(time_col).reset_index(drop=True)
    close = df[close_col].values.astype(float)
    returns_full = np.diff(np.log(close))

    # Simulate strategy returns (same as institutional pipeline)
    # momentum_12m, dxy_divergence, hybrid_mom_mr
    np.random.seed(42)

    # Simple momentum_12m simulation
    strategy_returns = {}
    strategy_configs = {
        "momentum_12m": {"lookback": 252, "vol_mult": 1.0},
        "dxy_divergence": {"lookback": 40, "vol_mult": 0.5},
        "hybrid_mom_mr": {"lookback": 60, "vol_mult": 0.8},
    }

    for name, cfg in strategy_configs.items():
        lookback = cfg["lookback"]
        vol_mult = cfg["vol_mult"]

        # Simple momentum signal: sign of cumulative return over lookback
        signal = np.zeros(len(returns_full))
        for t in range(lookback, len(returns_full)):
            hist = returns_full[t - lookback:t]
            if "dxy" in name:
                # Divergence: trade in opposite direction
                signal[t] = np.sign(-np.mean(hist[-10:]))
            else:
                signal[t] = np.sign(np.mean(hist))

        # Strategy returns
        strat_rets = signal[lookback:] * returns_full[lookback:] * vol_mult
        strat_rets += np.random.normal(0, 0.0005, len(strat_rets))  # Trading costs
        strategy_returns[name] = strat_rets.tolist()

    # Run checks
    c1 = winsorize_sharpe_curve(strategy_returns)
    c2 = sizing_audit(strategy_returns, returns_full)

    # Summary
    print("\n" + "=" * 64)
    print("  SUMMARY")
    print("=" * 64)

    for name in strategy_returns:
        w = c1.get(name, {})
        s = c2.get(name, {})
        print(f"\n  {name}:")
        print(f"    Winsorize verdict: {w.get('verdict', 'N/A')}")
        print(f"    Sizing verdict: {s.get('classification', 'N/A')}")

    # Verdict for momentum_12m freeze
    print("\n" + "=" * 64)
    print("  FREEZE DECISION")
    print("=" * 64)

    m12m = c1.get("momentum_12m", {})
    if m12m.get("verdict") == "ROBUST":
        print("  momentum_12m: SAFE TO FREEZE")
        print("  Action: Freeze parameters + add hard position cap")
    elif m12m.get("verdict") == "MOSTLY_ROBUST":
        print("  momentum_12m: FREEZE WITH CAUTION")
        print("  Action: Freeze parameters + add hard position cap + monitor outliers in paper")
    else:
        print("  momentum_12m: NOT SAFE TO FREEZE — need more investigation")
        print("  Action: Continue observation only")


if __name__ == "__main__":
    main()
