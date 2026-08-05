"""
Direct jackknife for tsm_dxy_divergence — leave-one-out DK t-stat.

Usage: python scripts/jackknife_tsm_dxy.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # C:\Users\menum\graxia os
sys.path.insert(0, str(ROOT))

from graxia.packages.quant_os.scripts.pooled_strategy_test import (
    UNIVERSE,
    driscoll_kraay_t_stat,
    extract_daily_returns,
    run_engine_for_asset,
)
from graxia.packages.quant_os.strategies.tsm_dxy_divergence import TSMDXYDivergence


def main():
    strategy_factory = lambda: TSMDXYDivergence()
    params = {"lookbacks": [20, 40, 60, 120], "atr_sl_mult": 4.0}

    print("=" * 70)
    print("Jackknife: tsm_dxy_divergence (TSMDXYDivergence)")
    print(f"Params: {params}")
    print(f"Universe: {UNIVERSE}")
    print("=" * 70)

    # Step 1: Run all assets
    asset_results = {}
    daily_returns = {}
    for symbol in UNIVERSE:
        print(f"\n  Running {symbol}...", end=" ", flush=True)
        results = run_engine_for_asset(symbol, strategy_factory)
        asset_results[symbol] = results
        dr = extract_daily_returns(results)
        daily_returns[symbol] = dr
        trades = len(results.get("trades", []))
        print(f"trades={trades}")

    # Step 2: Compute pooled panel (date x asset)
    panel = None
    for symbol, dr in daily_returns.items():
        if dr.empty:
            continue
        if panel is None:
            panel = dr.copy()
        else:
            panel = panel.join(dr, how="outer")

    if panel is None or panel.empty:
        print("\nERROR: No daily returns computed for any asset.")
        return

    panel = panel.fillna(0.0)
    total_days = len(panel)

    # Step 3: Compute pooled DK t-stat (all assets)
    cross_means = panel.mean(axis=1).values
    pooled_dk_t, pooled_mu, pooled_se = driscoll_kraay_t_stat(cross_means)

    print(f"\n{'=' * 70}")
    print(f"Pooled DK t-stat (all {len(panel.columns)} assets): {pooled_dk_t:.4f}")
    print(f"  mean={pooled_mu:.6e}  se={pooled_se:.6e}  n_days={total_days}")
    print(f"{'=' * 70}")

    # Step 4: Leave-one-out jackknife
    assets_with_trades = [
        s for s in panel.columns
        if len(asset_results.get(s, {}).get("trades", [])) > 0
    ]

    print(f"\nJackknife (leave-one-out) — {len(assets_with_trades)} assets with trades:")
    print(f"{'Asset':<12} {'dk_t':>8} {'delta':>8} {'verdict':>12}")
    print("-" * 44)

    jackknife_results = {}
    for excl_symbol in assets_with_trades:
        subset = panel.drop(columns=[excl_symbol])
        if subset.empty or subset.shape[1] == 0:
            continue
        sub_means = subset.mean(axis=1).values
        sub_dk_t, _, _ = driscoll_kraay_t_stat(sub_means)
        delta = sub_dk_t - pooled_dk_t
        verdict = "REJECT" if sub_dk_t < 2.0 else ("GO" if sub_dk_t > 2.0 and subset.shape[1] >= 5 else "MARGINAL")
        jackknife_results[excl_symbol] = {
            "dk_t_excluded": round(sub_dk_t, 4),
            "delta": round(delta, 4),
            "verdict": verdict,
        }
        marker = " <-- FLIPS" if delta < -1.0 else ""
        print(f"  -{excl_symbol:<10} {sub_dk_t:>8.4f} {delta:>+8.4f} {verdict:>12}{marker}")

    # Step 5: Summary
    print(f"\n{'=' * 70}")
    flips = [s for s, r in jackknife_results.items() if r["verdict"] != "REJECT"]
    if pooled_dk_t < 2.0:
        print(f"BASELINE: dk_t={pooled_dk_t:.4f} < 2.0 → REJECTED (no jackknife needed)")
    elif flips:
        print(f"BASELINE: dk_t={pooled_dk_t:.4f} ≥ 2.0")
        print(f"  Jackknife FLIPS: excluding {flips} keeps dk_t ≥ 2.0")
        print(f"  → Signal is NOT robust to single-asset removal → REJECTED")
    else:
        print(f"BASELINE: dk_t={pooled_dk_t:.4f} ≥ 2.0")
        print(f"  Jackknife: ALL leave-one-out dk_t < 2.0")
        print(f"  → Signal is robust → retains MARGINAL or GO status")

    # Step 6: Save report
    report = {
        "strategy": "TSMDXYDivergence",
        "variant": "tsm_dxy_divergence",
        "params": params,
        "universe": UNIVERSE,
        "pooled_dk_t": round(pooled_dk_t, 4),
        "pooled_mean": pooled_mu,
        "pooled_se": pooled_se,
        "n_days": total_days,
        "jackknife": jackknife_results,
        "verdict": "REJECT" if pooled_dk_t < 2.0 else ("REJECT" if flips else "MARGINAL"),
    }

    out_path = ROOT / "reports" / "jackknife_tsm_dxy_divergence.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to {out_path}")


if __name__ == "__main__":
    main()
