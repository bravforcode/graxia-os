"""Closure item 1 (spec P0): re-run TSM portfolio jackknife from current data.

Reuses scripts/tsm_portfolio.py functions and the leave-one-out loop from
scripts/tsm_portfolio_jackknife.py (the 2026-07-28 generator, commit aff11f71).
Writes to a NEW dated path so the original evidence file is never overwritten.

Verdict semantics (closure, spec P0 item 1):
- REJECT_CONFIRMED: baseline Sharpe <= 0, OR single-asset dependence reproduces
  (same rule as the 07-28 generator: exclusion collapses Sharpe >50% or flips sign)
- INCONCLUSIVE: dependence does NOT reproduce -> escalate to user (flip risk)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tsm_portfolio import (  # noqa: E402
    COST_BPS,
    LOOKBACKS,
    TARGET_VOL,
    compute_metrics,
    get_close_matrix,
    load_data,
    portfolio_backtest,
)

BASE = Path(__file__).resolve().parent.parent
OUT_PATH = BASE / "reports" / "tsm_portfolio_jackknife_rerun_20260806.json"


def main() -> int:
    data = load_data()
    full_close = get_close_matrix(data)
    print(f"Full universe: {list(full_close.columns)}")

    base_ret, _, _ = portfolio_backtest(full_close, LOOKBACKS, TARGET_VOL, COST_BPS)
    base_m = compute_metrics(base_ret, "baseline_all")
    print(
        f"\nBASELINE (all {len(full_close.columns)} assets): "
        f"Sharpe={base_m['sharpe']:.4f}  AnnRet={base_m['ann_ret']:.2%}  MaxDD={base_m['max_dd']:.2%}"
    )

    results: dict = {"baseline": base_m, "jackknife": {}}

    for asset in full_close.columns:
        subset = full_close.drop(columns=[asset])
        ret, _, _ = portfolio_backtest(subset, LOOKBACKS, TARGET_VOL, COST_BPS)
        m = compute_metrics(ret, f"excl_{asset}")
        delta = m["sharpe"] - base_m["sharpe"]
        print(f"  Exclude {asset:<12} Sharpe={m['sharpe']:.4f}  (delta={delta:+.4f})")
        results["jackknife"][asset] = {**m, "sharpe_delta_from_baseline": round(delta, 4)}

    concerning = [
        a
        for a, r in results["jackknife"].items()
        if (base_m["sharpe"] > 0 and r["sharpe"] < base_m["sharpe"] * 0.5) or (r["sharpe"] <= 0 < base_m["sharpe"])
    ]
    results["concerning_single_asset_dependence"] = concerning

    if base_m["sharpe"] <= 0 or concerning:
        verdict = "REJECT_CONFIRMED"
    else:
        verdict = "INCONCLUSIVE"
    results["verdict"] = verdict
    results["data_sources"] = {
        "parquet": "artifacts/portfolio/d1_multi_asset.parquet (built by scripts/build_d1_portfolio.py; "
        "see mtime for freshness vs current data/)",
        "generator_reference": "scripts/tsm_portfolio_jackknife.py (commit aff11f71)",
        "note": "Closure rerun 2026-08-06 — original 07-28 evidence file untouched.",
    }

    OUT_PATH.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {verdict}")
    print(f"Saved: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
