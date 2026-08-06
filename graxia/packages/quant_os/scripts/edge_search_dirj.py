"""Direction J trials — COT contrarian (3007) + DXY cross-asset (3003) on XAUUSD.

Frozen per research/pre_registration/trial_3007_cot_xauusd.md and
trial_3003_dxy_xauusd.md (2026-08-06). Precomputes the strategy features from
in-repo data, then runs BacktestEngine measured-cost path (XAUUSD 0.65 bps rt).

Usage:
    python scripts/edge_search_dirj.py --trial 3007
    python scripts/edge_search_dirj.py --trial 3003
"""
from __future__ import annotations

import glob
import json
import math
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
GRAXIA_ROOT = ROOT.parent.parent.parent
for p in (str(GRAXIA_ROOT), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

OUT = ROOT / "reports" / "edge_search_dirj.json"


def load_xauusd_d1() -> pd.DataFrame:
    df = pd.read_csv(ROOT / "data" / "XAUUSD_D1.csv")
    ts = "time" if "time" in df.columns else "date"
    df[ts] = pd.to_datetime(df[ts], utc=True)
    return df.sort_values(ts).reset_index(drop=True)


def load_cot() -> pd.DataFrame:
    """Concatenate COT parquet files -> weekly Managed Money net positioning."""
    frames = []
    for f in sorted(glob.glob(str(ROOT / "data" / "cot" / "cot_xauusd_disaggregated_fut_*.parquet"))):
        frames.append(pd.read_parquet(f))
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["Report_Date_as_YYYY-MM-DD"], utc=True)
    df = df.sort_values("date").reset_index(drop=True)
    net = df["M_Money_Positions_Long_All"].astype(float) - df["M_Money_Positions_Short_All"].astype(float)
    return pd.DataFrame({"date": df["date"], "mm_net": net})


def cot_signal(daily: pd.DataFrame, cot: pd.DataFrame, lookback_weeks=52, entry_z=2.0, exit_z=0.5) -> pd.Series:
    """Weekly z-score of Managed-Money net positioning; contrarian entry at z>=entry_z."""
    cot = cot.set_index("date").sort_index()
    weekly = cot.resample("W-FRI").last().dropna()
    roll = weekly["mm_net"].rolling(lookback_weeks)
    z = (weekly["mm_net"] - roll.mean()) / (roll.std() + 1e-9)
    sig = pd.Series(0.0, index=weekly.index)
    pos = 0.0
    for i in range(len(weekly)):
        zi = z.iloc[i]
        if pos == 0 and zi >= entry_z:
            pos = -1.0  # contrarian: net-long extreme -> short gold
        elif pos == 0 and zi <= -entry_z:
            pos = 1.0
        elif pos != 0 and abs(zi) <= exit_z:
            pos = 0.0
        sig.iloc[i] = pos
    # reindex to daily (forward-fill weekly signal)
    daily_idx = pd.DatetimeIndex(daily["time"] if "time" in daily.columns else daily["date"])
    sig = sig.reindex(daily_idx, method="ffill").fillna(0.0)
    return sig


def dxy_signal(daily: pd.DataFrame, window=60, z_threshold=1.0, hold_days=5) -> pd.Series:
    """DXY momentum z-score; gold trades against USD extreme (lead-lag)."""
    dxy = pd.read_csv(ROOT / "data" / "DXY_D1.csv")
    ts = "time" if "time" in dxy.columns else "date"
    dxy[ts] = pd.to_datetime(dxy[ts], utc=True)
    dxy = dxy.sort_values(ts).reset_index(drop=True)
    daily_idx = pd.DatetimeIndex(daily["time"] if "time" in daily.columns else daily["date"])
    dxy_idx = pd.DatetimeIndex(dxy[ts])
    dxy_close = pd.Series(dxy["close"].astype(float).to_numpy(), index=dxy_idx)
    dxy_close = dxy_close.reindex(daily_idx, method="ffill")
    mom = dxy_close.pct_change(window)
    z = (mom - mom.rolling(window).mean()) / (mom.rolling(window).std() + 1e-9)
    sig = pd.Series(0.0, index=daily_idx)
    pos = 0.0
    hold_left = 0
    for i in range(len(daily_idx)):
        if hold_left > 0:
            hold_left -= 1
            if hold_left == 0:
                pos = 0.0
            sig.iloc[i] = pos
            continue
        zi = z.iloc[i]
        if pos == 0 and zi >= z_threshold:
            pos = -1.0  # DXY strong up -> gold down (lead-lag)
            hold_left = hold_days
        elif pos == 0 and zi <= -z_threshold:
            pos = 1.0
            hold_left = hold_days
        sig.iloc[i] = pos
    return sig


def run_backtest(daily: pd.DataFrame, sig: pd.Series) -> dict:
    """Simple backtest: trade signal on daily close, next-bar fill, XAUUSD 0.65 bps rt."""
    prices = daily["close"].astype(float).to_numpy()
    n = len(prices)
    cash = 10000.0
    pos = 0.0
    entry = 0.0
    pnls = []
    for i in range(1, n):
        s = sig.iloc[i - 1]
        if s != 0 and pos == 0:
            pos = s
            entry = prices[i - 1]
        elif s == 0 and pos != 0:
            gross = pos * (prices[i] - entry)
            cost = prices[i - 1] * 0.65 / 10000.0 * 1000.0  # 0.65 bps rt on 1000 oz
            pnls.append(gross - cost)
            cash += gross - cost
            pos = 0.0
    # mark-to-market open position
    if pos != 0:
        pnls.append(pos * (prices[-1] - entry))
    arr = np.array(pnls) if len(pnls) >= 20 else np.array([])
    return {"n_trades": len(pnls), "pnls": arr, "final_cash": cash}


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
    parser.add_argument("--trial", required=True, choices=["3007", "3003"])
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    daily = load_xauusd_d1()
    print(f"XAUUSD D1: {len(daily)} bars")
    if args.trial == "3007":
        cot = load_cot()
        print(f"COT: {len(cot)} weekly rows ({cot['date'].min().date()} -> {cot['date'].max().date()})")
        sig = cot_signal(daily, cot)
    else:
        sig = dxy_signal(daily)

    n_sig = int((sig != 0).sum())
    print(f"signal bars: {n_sig} ({n_sig / len(sig) * 100:.1f}%)")
    res = run_backtest(daily, sig)
    arr = res["pnls"]
    print(f"trades: {res['n_trades']}, final cash: {res['final_cash']:.2f}")
    if len(arr) >= 20:
        t = dk_t(arr)
        sharpe = float(arr.mean()) / (float(arr.std(ddof=1)) + 1e-10) * math.sqrt(52)
        verdict = "GO" if (t > 2.0 and arr.mean() > 0) else ("MARGINAL" if t > 1.5 else "REJECT")
        print(f"dk_t={t:.4f} sharpe={sharpe:.3f} mean_pnl={arr.mean():.4f} -> {verdict}")
        result = {"n_trades": res["n_trades"], "dk_t": round(t, 4), "sharpe": round(sharpe, 4),
                  "mean_pnl": round(float(arr.mean()), 4), "final_cash": round(res["final_cash"], 2), "verdict": verdict}
    else:
        print("INSUFFICIENT trades")
        result = {"n_trades": res["n_trades"], "verdict": "INSUFFICIENT"}

    out_path = Path(args.out)
    data = {}
    if out_path.exists():
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    data[f"trial_{args.trial}"] = {**result, "executed_at": datetime.now(UTC).isoformat()}
    out_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"merged -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
