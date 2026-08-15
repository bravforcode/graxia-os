"""Direction K 4006 — BTC/ETH volume-divergence spread (BEVS)."""
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

OUT = ROOT / "reports" / "edge_search_dirk_4006.json"
COST_RT = 14.0  # bps per pair round trip


def main() -> int:
    from graxia.packages.quant_os.strategies.btc_eth_vol_spread import BTCETHVolSpreadConfig, compute_bevs_signals

    b = pd.read_csv(ROOT / "data" / "BTCUSD_H1.csv")
    e = pd.read_csv(ROOT / "data" / "ETHUSD_H1.csv")
    for df in (b, e):
        ts = "time" if "time" in df.columns else "date"
        df[ts] = pd.to_datetime(df[ts], utc=True)
        df.set_index(pd.DatetimeIndex(df[ts]), inplace=True)
    j = pd.concat([b[["close", "volume"]], e[["close", "volume"]]], axis=1, join="inner").dropna()
    j.columns = ["BTC", "BTC_v", "ETH", "ETH_v"]

    res = compute_bevs_signals(
        btc_close=j["BTC"], btc_volume=j["BTC_v"],
        eth_close=j["ETH"], eth_volume=j["ETH_v"],
        config=BTCETHVolSpreadConfig(),
    )
    sig = res.signal.reindex(j.index).fillna(0.0)
    n_sig = int((sig != 0).sum())
    print(f"signal bars: {n_sig} ({n_sig/len(sig)*100:.2f}%)")

    # Backtest: sig>0 -> long spread (long BTC, short ETH), hold_days, cost per pair
    ratio = np.log(j["BTC"] / j["ETH"])
    n = len(j)
    cash = 10000.0
    pos = 0.0
    entry = 0.0
    hold_left = 0
    pnls = []
    for i in range(1, n):
        if hold_left > 0:
            hold_left -= 1
            if hold_left == 0 and pos != 0:
                gross = pos * (ratio.iloc[i] - entry) * 10000.0
                cost = COST_RT / 10000.0 * 10000.0
                pnls.append(gross - cost)
                cash += gross - cost
                pos = 0.0
            continue
        s = sig.iloc[i - 1]
        if s != 0 and pos == 0:
            pos = s
            entry = ratio.iloc[i - 1]
            hold_left = BTCETHVolSpreadConfig().hold_days
    if pos != 0:
        pnls.append(pos * (ratio.iloc[-1] - entry) * 10000.0)

    arr = np.array(pnls) if len(pnls) >= 20 else np.array([])
    print(f"trades: {len(pnls)}, final cash: {cash:.2f}")
    if len(arr) < 100:
        result = {"n_trades": len(pnls), "verdict": "INSUFFICIENT"}
        print("INSUFFICIENT (<100)")
    else:
        mu = arr.mean()
        n2 = len(arr)
        bnd = max(int(4 * (n2 / 100) ** (2 / 9)), 1)
        g0 = float(np.mean((arr - mu) ** 2))
        v = g0
        for k in range(1, bnd + 1):
            w = 1 - k / (bnd + 1)
            v += 2 * w * float(np.mean((arr[k:] - mu) * (arr[:-k] - mu)))
        t = mu / (math.sqrt(v / n2) + 1e-10)
        sharpe = float(arr.mean()) / (float(arr.std(ddof=1)) + 1e-10) * math.sqrt(252 * 24)
        verdict = "GO" if (t > 2.0 and mu > 0) else ("MARGINAL" if t > 1.5 else "REJECT")
        print(f"dk_t={t:.4f} sharpe={sharpe:.3f} mean_pnl={mu:.4f} -> {verdict}")
        result = {"n_trades": len(pnls), "dk_t": round(t, 4), "sharpe": round(sharpe, 4),
                  "mean_pnl": round(float(mu), 4), "final_cash": round(cash, 2), "verdict": verdict}

    OUT.write_text(json.dumps({**result, "executed_at": datetime.now(UTC).isoformat()}, indent=2), encoding="utf-8")
    print(f"merged -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
