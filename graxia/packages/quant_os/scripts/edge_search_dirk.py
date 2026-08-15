"""Direction K Trial 4005 — BTC/ETH pairs trading (log-ratio z + Engle-Granger).

Frozen per research/pre_registration/trial_4005_btceth_pairs.md (2026-08-06).
Costs: Binance taker 10 bps rt + slippage 2 bps/leg = 14 bps rt per pair trade.

Usage:
    python scripts/edge_search_dirk.py --arm pairs_mr
    python scripts/edge_search_dirk.py --arm pgm
"""
from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
GRAXIA_ROOT = ROOT.parent.parent.parent
for p in (str(GRAXIA_ROOT), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

OUT = ROOT / "reports" / "edge_search_dirk_4005.json"
COST_RT = 14.0  # bps per pair round trip (10 taker + 4 slippage)


def load_joint() -> pd.DataFrame:
    b = pd.read_csv(ROOT / "data" / "BTCUSD_H1.csv")
    e = pd.read_csv(ROOT / "data" / "ETHUSD_H1.csv")
    for df in (b, e):
        ts = "time" if "time" in df.columns else "date"
        df[ts] = pd.to_datetime(df[ts], utc=True)
        df.set_index(pd.DatetimeIndex(df[ts]), inplace=True)
    j = pd.concat([b["close"].astype(float), e["close"].astype(float)], axis=1, join="inner").dropna()
    j.columns = ["BTC", "ETH"]
    return j


def backtest_pair(j: pd.DataFrame, sig: pd.Series, cost_bps: float) -> dict:
    """Trade the ratio: sig>0 -> long ratio (long BTC, short ETH)."""
    ratio = np.log(j["BTC"] / j["ETH"])
    n = len(j)
    cash = 10000.0
    pos = 0.0
    entry = 0.0
    pnls = []
    for i in range(1, n):
        s = sig.iloc[i - 1]
        if s != 0 and pos == 0:
            pos = s
            entry = ratio.iloc[i - 1]
        elif s == 0 and pos != 0:
            gross = pos * (ratio.iloc[i] - entry) * 10000.0
            cost = cost_bps / 10000.0 * 10000.0
            pnls.append(gross - cost)
            cash += gross - cost
            pos = 0.0
    if pos != 0:
        pnls.append(pos * (ratio.iloc[-1] - entry) * 10000.0)
    return {"n_trades": len(pnls), "pnls": np.array(pnls), "final_cash": cash}


def dk_t(arr: np.ndarray) -> float:
    if len(arr) < 20:
        return 0.0
    mu = arr.mean()
    n = len(arr)
    b = max(int(4 * (n / 100) ** (2 / 9)), 1)
    g0 = float(np.mean((arr - mu) ** 2))
    v = g0
    for k in range(1, b + 1):
        w = 1 - k / (b + 1)
        v += 2 * w * float(np.mean((arr[k:] - mu) * (arr[:-k] - mu)))
    return mu / (math.sqrt(v / n) + 1e-10)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True, choices=["pairs_mr", "pgm"])
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    j = load_joint()
    print(f"joint bars: {len(j)} ({j.index.min()} -> {j.index.max()})")

    if args.arm == "pairs_mr":
        from graxia.packages.quant_os.strategies.pairs_mr import compute_pairs_mr_signal

        sig_obj = compute_pairs_mr_signal(j["BTC"], j["ETH"], lookback=60, entry_z=2.0, exit_z=0.5)
        sig = sig_obj.signal if hasattr(sig_obj, "signal") else sig_obj
    else:
        from graxia.packages.quant_os.strategies.pgm_pairs import compute_pgm_pairs_signals

        res = compute_pgm_pairs_signals(
            xpt_close=j["BTC"], xpt_high=j["BTC"], xpt_low=j["BTC"],
            xpd_close=j["ETH"], xpd_high=j["ETH"], xpd_low=j["ETH"],
        )
        sig = res.signal

    n_sig = int((sig != 0).sum())
    print(f"signal bars: {n_sig} ({n_sig/len(sig)*100:.2f}%)")
    bt = backtest_pair(j, sig, COST_RT)
    arr = bt["pnls"]
    print(f"trades: {bt['n_trades']}, final cash: {bt['final_cash']:.2f}")
    if len(arr) < 100:
        result = {"n_trades": bt["n_trades"], "verdict": "INSUFFICIENT"}
        print("INSUFFICIENT (<100 trades)")
    else:
        t = dk_t(arr)
        sharpe = float(arr.mean()) / (float(arr.std(ddof=1)) + 1e-10) * math.sqrt(252 * 24)
        verdict = "GO" if (t > 2.0 and arr.mean() > 0) else ("MARGINAL" if t > 1.5 else "REJECT")
        print(f"dk_t={t:.4f} sharpe={sharpe:.3f} mean_pnl={arr.mean():.4f} -> {verdict}")
        result = {"n_trades": bt["n_trades"], "dk_t": round(t, 4), "sharpe": round(sharpe, 4),
                  "mean_pnl": round(float(arr.mean()), 4), "final_cash": round(bt["final_cash"], 2), "verdict": verdict}

    out_path = Path(args.out)
    data = {}
    if out_path.exists():
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    data[f"arm_{args.arm}"] = {**result, "executed_at": datetime.now(UTC).isoformat()}
    out_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"merged -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
