"""
Track A — DK-test + label-shuffle on the 6 existing Path B wrappers
====================================================================
Tests the already-imported published-edge strategies in
strategies/path_b_wrappers.py (TSMOM, CrossAssetMomentum, VolRiskPremium,
Carry, FOMCDrift, COTPositioning) through the SAME honest harness used for
Trial #2001:

  - run_engine_for_asset()  -> BacktestEngine per asset (same costs)
  - run_dk_test()           -> pooled Deflated-Sharpe (NW-HAC, sqrt(252))
  - label_shuffle_test()    -> stationary-bootstrap null (Politis & Romano)

GO criteria (pre-registered, identical to edge_search_cross_sectional.py):
  dk_t > 2.0 AND positive_sharpe_count >= 5 AND label_shuffle_p < 0.05 -> GO

Each wrapper is ONE hypothesis (N=1) -> no multiple-testing correction needed.
Params are frozen in the wrapper classes; nothing is fit to this data here.

Usage:
  python scripts/test_path_b_wrappers.py
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # scripts/
QUANT_OS = ROOT.parent                          # quant_os/
GRAXIA_ROOT = QUANT_OS.parent.parent.parent     # graxia os/graxia
for p in (str(GRAXIA_ROOT), str(QUANT_OS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np
import pandas as pd

from graxia.packages.quant_os.strategies.path_b_wrappers import (  # noqa: E402
    TSMOMStrategy,
    CrossAssetMomentumStrategy,
    VolRiskPremiumStrategy,
    CarryStrategy,
    FOMCDriftStrategy,
    COTPositioningStrategy,
)
from graxia.packages.quant_os.scripts.edge_search_all import (  # noqa: E402
    run_engine_for_asset,
    run_dk_test,
    extract_daily_returns,
)
from graxia.packages.quant_os.scripts.edge_search_cross_sectional import (  # noqa: E402
    label_shuffle_test,
)

# 7-asset universe (daily D1 data, matches DK/label-shuffle annualization)
UNIVERSE = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "US30", "NAS100", "BTCUSD"]

WRAPPERS = {
    "TSMOM": TSMOMStrategy,
    "CAM": CrossAssetMomentumStrategy,
    "VRP": VolRiskPremiumStrategy,
    "Carry": CarryStrategy,
    "FOMCDrift": FOMCDriftStrategy,
    "COTPositioning": COTPositioningStrategy,
}

N_SHUFFLES = 200
BLOCK_LENGTH = 10


def test_wrapper(name: str, cls) -> dict | None:
    print(f"\n=== {name} ===")
    try:
        strat = cls()
    except Exception as e:  # noqa: BLE001
        print(f"  [SKIP] instantiate failed: {e}")
        return None

    per_asset: list[pd.DataFrame] = []
    total_trades = 0
    for sym in UNIVERSE:
        try:
            res = run_engine_for_asset(sym, strat)
        except Exception as e:  # noqa: BLE001
            print(f"  [SKIP] {sym}: {type(e).__name__}: {e}")
            continue
        dr = extract_daily_returns(res)
        if dr is None or dr.empty:
            continue
        dr = dr.copy()
        dr.columns = [sym]
        per_asset.append(dr)
        total_trades += len(res.get("trades", []))

    if not per_asset:
        print("  [SKIP] no returns produced")
        return None

    all_ret = pd.concat(per_asset, axis=1).dropna(how="all")
    if all_ret.shape[1] < 2:
        print("  [SKIP] <2 assets with returns")
        return None

    dk = run_dk_test(all_ret, total_trades)
    shuffle = label_shuffle_test(
        all_ret, dk["dk_t_stat"], n_shuffles=N_SHUFFLES, block_length=BLOCK_LENGTH
    )
    p = shuffle.get("p_value")

    go = (
        dk["dk_t_stat"] > 2.0
        and dk["positive_sharpe_count"] >= 5
        and (p is not None and p < 0.05)
    )

    print(
        f"  dk_t={dk['dk_t_stat']:.3f} pos_sharpe={dk['positive_sharpe_count']}/"
        f"{all_ret.shape[1]} pooled_sharpe={dk['pooled_sharpe']:.3f} "
        f"trades={total_trades} label_shuffle_p={p} -> {dk['verdict']} GO={go}"
    )

    return {
        "dk_t": dk["dk_t_stat"],
        "pooled_sharpe": dk["pooled_sharpe"],
        "positive_sharpe_count": dk["positive_sharpe_count"],
        "total_assets": int(all_ret.shape[1]),
        "total_trades": total_trades,
        "label_shuffle_p": p,
        "label_shuffle_mean_t": shuffle.get("mean_shuffled_t"),
        "verdict": dk["verdict"],
        "go": bool(go),
    }


def main() -> int:
    report: dict[str, dict] = {}
    for name, cls in WRAPPERS.items():
        try:
            r = test_wrapper(name, cls)
        except Exception:  # noqa: BLE001
            print(f"  [ERROR] {name}: {traceback.format_exc()}")
            r = None
        if r is not None:
            report[name] = r

    out = QUANT_OS / "reports" / "path_b_wrappers_dk_label_shuffle_20260723.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {out}")

    go_list = [n for n, r in report.items() if r["go"]]
    print(f"GO strategies: {go_list if go_list else 'NONE'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
