"""Jackknife (leave-one-out) robustness test for scripts/tsm_portfolio.py's
Sharpe=1.1749 / DSR-significant result -- per user's explicit demand: do not
trust this number until it survives the same leave-one-out test that caught
donchian_vol_filter's single-asset artifact (XAGUSD alone flipped that pooled
dk_t from +3.318 to -0.136).

Reuses the real portfolio_backtest()/compute_metrics() functions from
tsm_portfolio.py unmodified -- does not reimplement the backtest logic.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tsm_portfolio import (
    ASSETS,
    LOOKBACKS,
    TARGET_VOL,
    COST_BPS,
    load_data,
    get_close_matrix,
    portfolio_backtest,
    compute_metrics,
)

BASE = Path(__file__).resolve().parent.parent


def main() -> int:
    data = load_data()
    full_close = get_close_matrix(data)
    print(f"Full universe: {list(full_close.columns)}")

    # Baseline (all assets)
    base_ret, _, _ = portfolio_backtest(full_close, LOOKBACKS, TARGET_VOL, COST_BPS)
    base_m = compute_metrics(base_ret, "baseline_all")
    print(f"\nBASELINE (all {len(full_close.columns)} assets): "
          f"Sharpe={base_m['sharpe']:.4f}  AnnRet={base_m['ann_ret']:.2%}  MaxDD={base_m['max_dd']:.2%}")

    results = {"baseline": base_m, "jackknife": {}}

    for asset in full_close.columns:
        subset = full_close.drop(columns=[asset])
        ret, _, _ = portfolio_backtest(subset, LOOKBACKS, TARGET_VOL, COST_BPS)
        m = compute_metrics(ret, f"excl_{asset}")
        delta = m["sharpe"] - base_m["sharpe"]
        print(f"  Exclude {asset:<12} Sharpe={m['sharpe']:.4f}  "
              f"(delta={delta:+.4f})  AnnRet={m['ann_ret']:.2%}  MaxDD={m['max_dd']:.2%}")
        results["jackknife"][asset] = {**m, "sharpe_delta_from_baseline": round(delta, 4)}

    # Flag any single-asset exclusion that flips the sign or collapses Sharpe by >50%
    concerning = [
        a for a, r in results["jackknife"].items()
        if (base_m["sharpe"] > 0 and r["sharpe"] < base_m["sharpe"] * 0.5)
        or (r["sharpe"] <= 0 < base_m["sharpe"])
    ]
    results["concerning_single_asset_dependence"] = concerning

    print(f"\n{'='*70}")
    if concerning:
        print(f"CONCERNING: excluding any of {concerning} collapses/flips the Sharpe.")
        print("This result may be a single-asset (or small-subset) artifact, not a")
        print("genuine diversified multi-asset edge -- same pattern as F27's XAGUSD flip.")
    else:
        print("No single-asset exclusion collapses or flips the Sharpe sign.")
        print("Result is NOT a single-asset artifact by this test (does not by itself")
        print("prove the edge is real -- see separate n_trials/DSR-scope caveat).")

    out_path = BASE / "reports" / "tsm_portfolio_jackknife_20260728.json"
    out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
