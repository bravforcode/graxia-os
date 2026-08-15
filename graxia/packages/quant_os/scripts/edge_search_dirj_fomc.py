"""Direction J 3010 — FOMC drift on XAUUSD D1. Frozen per pre-registration."""
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

OUT = ROOT / "reports" / "edge_search_dirj_fomc.json"


def main() -> int:
    from graxia.packages.quant_os.strategies.fomc_drift import FOMCDriftConfig, compute_fomc_drift_signals

    df = pd.read_csv(ROOT / "data" / "XAUUSD_D1.csv")
    ts = "time" if "time" in df.columns else "date"
    df[ts] = pd.to_datetime(df[ts], utc=True)
    df = df.set_index(pd.DatetimeIndex(df[ts])).sort_index()

    res = compute_fomc_drift_signals(
        close=df["close"], high=df["high"], low=df["low"], config=FOMCDriftConfig()
    )
    sig = res.signal
    prices = df["close"].astype(float).to_numpy()
    n_sig = int((sig != 0).sum())
    print(f"signal bars: {n_sig} ({n_sig/len(sig)*100:.2f}%)")

    # Backtest: entry next bar open at signal, exit after drift_window_days
    cash = 10000.0
    pos = 0.0
    entry = 0.0
    hold_left = 0
    pnls = []
    for i in range(len(prices)):
        s = sig.iloc[i]
        if hold_left > 0:
            hold_left -= 1
            if hold_left == 0 and pos != 0:
                gross = pos * (prices[i] - entry)
                cost = prices[i] * 0.65 / 10000.0 * 1000.0
                pnls.append(gross - cost)
                cash += gross - cost
                pos = 0.0
            continue
        if s != 0 and pos == 0:
            pos = s
            entry = prices[i]
            hold_left = FOMCDriftConfig().drift_window_days
    if pos != 0:
        pnls.append(pos * (prices[-1] - entry))

    arr = np.array(pnls) if len(pnls) >= 20 else np.array([])
    print(f"trades: {len(pnls)}, final cash: {cash:.2f}")
    if len(arr) < 25:
        result = {"n_trades": len(pnls), "verdict": "INSUFFICIENT"}
        print("INSUFFICIENT (<25 trades)")
    else:
        mu = arr.mean()
        n = len(arr)
        b = max(int(4 * (n / 100) ** (2 / 9)), 1)
        g0 = float(np.mean((arr - mu) ** 2))
        v = g0
        for k in range(1, b + 1):
            w = 1 - k / (b + 1)
            v += 2 * w * float(np.mean((arr[k:] - mu) * (arr[:-k] - mu)))
        t = mu / (math.sqrt(v / n) + 1e-10)
        sharpe = float(arr.mean()) / (float(arr.std(ddof=1)) + 1e-10) * math.sqrt(52)
        verdict = "GO" if (t > 2.0 and mu > 0) else ("MARGINAL" if t > 1.5 else "REJECT")
        print(f"dk_t={t:.4f} sharpe={sharpe:.3f} mean_pnl={mu:.4f} -> {verdict}")
        result = {"n_trades": len(pnls), "dk_t": round(t, 4), "sharpe": round(sharpe, 4),
                  "mean_pnl": round(float(mu), 4), "final_cash": round(cash, 2), "verdict": verdict}

    OUT.write_text(json.dumps({**result, "executed_at": datetime.now(UTC).isoformat()}, indent=2), encoding="utf-8")
    print(f"merged -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
