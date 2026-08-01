"""
Track B — honest out-of-sample edge test for KhubievPortfolio
==============================================================
KhubievPortfolio trains a return-forecaster on finance-grounded loss
functions (Khubiev et al. 2509.04541). To avoid look-ahead bias, the model
is trained on the FIRST train_fraction (default 0.70) of universe data only;
the DK-test + label-shuffle are then computed on the HELD-OUT last 30%.

Reuses run_engine_for_asset (real costs/SL/TP) + run_dk_test + label_shuffle_test.

GO criteria (pre-registered):
  dk_t > 2.0 AND positive_sharpe_count >= 5 AND label_shuffle_p < 0.05 -> GO

Usage:
  python scripts/test_khubiev_edge.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QUANT_OS = ROOT.parent
GRAXIA_ROOT = QUANT_OS.parent.parent.parent
for p in (str(GRAXIA_ROOT), str(QUANT_OS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np
import pandas as pd

from graxia.packages.quant_os.strategies.khubiev_portfolio import KhubievPortfolio
from graxia.packages.quant_os.scripts.edge_search_all import (
    run_engine_for_asset,
    run_dk_test,
    extract_daily_returns,
)
from graxia.packages.quant_os.scripts.edge_search_cross_sectional import (
    label_shuffle_test,
)

UNIVERSE = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "US30", "NAS100", "BTCUSD"]
LOSSES = ["mod_sharpe_abs", "risk_adj"]
TRAIN_FRACTION = 0.70
TEST_FRACTION = 0.30
N_SHUFFLES = 200
BLOCK_LENGTH = 10


def test_loss(loss: str) -> dict | None:
    print(f"\n=== KhubievPortfolio loss={loss} (train={TRAIN_FRACTION}) ===")
    try:
        strat = KhubievPortfolio(loss=loss, train_fraction=TRAIN_FRACTION)
    except Exception as e:  # noqa: BLE001
        print(f"  [SKIP] init/fit failed: {e}")
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
        # Hold out the last TEST_FRACTION of dates (no look-ahead: model trained on first 70%)
        n_test = max(30, int(len(dr) * TEST_FRACTION))
        dr_test = dr.iloc[-n_test:]
        if len(dr_test) < 30:
            continue
        per_asset.append(dr_test)
        total_trades += len(res.get("trades", []))

    if not per_asset:
        print("  [SKIP] no test-window returns")
        return None

    all_ret = pd.concat(per_asset, axis=1).dropna(how="any")
    if all_ret.shape[1] < 2:
        print("  [SKIP] <2 assets with test returns")
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
        f"test_days={all_ret.shape[0]} trades={total_trades} label_shuffle_p={p} "
        f"-> {dk['verdict']} GO={go}"
    )

    return {
        "loss": loss,
        "train_fraction": TRAIN_FRACTION,
        "dk_t": dk["dk_t_stat"],
        "pooled_sharpe": dk["pooled_sharpe"],
        "positive_sharpe_count": dk["positive_sharpe_count"],
        "total_assets": int(all_ret.shape[1]),
        "test_days": int(all_ret.shape[0]),
        "total_trades": total_trades,
        "label_shuffle_p": p,
        "label_shuffle_mean_t": shuffle.get("mean_shuffled_t"),
        "verdict": dk["verdict"],
        "go": bool(go),
    }


def main() -> int:
    report: dict[str, dict] = {}
    for loss in LOSSES:
        try:
            r = test_loss(loss)
        except Exception as e:  # noqa: BLE001
            print(f"  [ERROR] {loss}: {e}")
            r = None
        if r is not None:
            report[loss] = r

    out = QUANT_OS / "reports" / "khubiev_edge_oos_20260723.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {out}")

    go_list = [n for n, r in report.items() if r["go"]]
    print(f"GO losses: {go_list if go_list else 'NONE'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
