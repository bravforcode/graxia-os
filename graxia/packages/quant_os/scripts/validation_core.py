"""
Donchian BTCUSD H1 — VALIDATION SUITE v2 (HONEST)
===================================================
4 analyses, all using REAL data:
  1. Monte Carlo: 10K bootstrap resamples from actual trade returns
  2. Multi-asset: Only assets with MEASURED spread costs
  3. Parameter sensitivity: 18 Donchian configs on real BTCUSD
  4. Regime analysis: Rolling vol + trend (not broken ADX)
"""
from __future__ import annotations

import json
import time
from datetime import datetime as _dt
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "data"
REPORTS_DIR = BASE / "reports" / "validation_suite"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

N_BOOTSTRAP = 10_000
INITIAL_CAPITAL = 100_000.0

# MEASURED spreads — loaded from cost_calibration.json at runtime
MEASURED_SPREADS = {}

def _load_spreads():
    """Load spread costs from cost_calibration.json (Pepperstone Razor MEASURED)."""
    global MEASURED_SPREADS
    cal_path = BASE / "config" / "cost_calibration.json"
    if cal_path.exists():
        cal = json.loads(cal_path.read_text(encoding="utf-8"))
        for sym, data in cal.get("assets", {}).items():
            MEASURED_SPREADS[sym] = data.get("spread_bps_measured", 0.0)
    # Also map XAGUSD → SILVER if needed
    if "SILVER" in MEASURED_SPREADS and "XAGUSD" not in MEASURED_SPREADS:
        MEASURED_SPREADS["XAGUSD"] = MEASURED_SPREADS.pop("SILVER")

_load_spreads()

# ── LOAD ────────────────────────────────────────────────────────────
def load_h1(sym: str) -> pd.DataFrame | None:
    p = DATA_DIR / f"{sym}_H1.csv"
    if not p.exists():
        return None
    try:
        df = pd.read_csv(p)
        df.columns = [c.strip().lower() for c in df.columns]
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time").sort_index()
        return df if len(df) > 100 else None
    except Exception:
        return None

# ── DONCHIAN ────────────────────────────────────────────────────────
def donchian_signals(df, period=20, vol_filter=True, atr_period=14):
    closes = df["close"].values.astype(float)
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    n = len(closes)

    tr = np.maximum(highs[1:] - lows[1:],
        np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])))
    atr = np.full(n, np.nan)
    atr[1] = tr[0]
    for i in range(2, n):
        atr[i] = (atr[i-1] * (atr_period - 1) + tr[i-1]) / atr_period

    atr_ratio = np.where(closes > 0, atr / closes, 0)
    med_ratio = np.nanmedian(atr_ratio[-200:]) if n > 200 else np.nanmedian(atr_ratio)

    signals = []
    for i in range(period + 1, n):
        if np.isnan(atr[i]):
            continue
        hh = np.max(highs[i - period: i - 1])
        ll = np.min(lows[i - period: i - 1])
        vol_ok = not vol_filter or (i > 0 and atr_ratio[i] > med_ratio * 0.8)

        d, conf, reason = 0, 0.0, ""
        if closes[i] > hh and vol_ok:
            d = 1
            conf = min((closes[i] - hh) / (hh + 1e-10) * 100 * 5, 1.0)
            reason = f"LONG high={hh:.2f}"
        elif closes[i] < ll and vol_ok:
            d = -1
            conf = min((ll - closes[i]) / (ll + 1e-10) * 100 * 5, 1.0)
            reason = f"SHORT low={ll:.2f}"

        if d != 0 and conf > 0.1:
            signals.append({"bar_index": i, "direction": d, "confidence": round(conf, 3),
                "entry": closes[i],
                "sl": closes[i] - atr[i] * 2.0 if d == 1 else closes[i] + atr[i] * 2.0,
                "tp": closes[i] + atr[i] * 3.0 if d == 1 else closes[i] - atr[i] * 3.0,
                "reason": reason})
    return signals

# ── SIMULATE ────────────────────────────────────────────────────────
def simulate(df, signals, spread_bps, capital=INITIAL_CAPITAL):
    closes = df["close"].values.astype(float)
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    n = len(closes)
    trades, open_t = [], None

    for sig in signals:
        idx = sig["bar_index"]
        if idx + 1 >= n:
            continue
        if open_t is None:
            entry = closes[idx + 1]
            sd = abs(entry - sig["sl"])
            lots = max(0.01, round(capital * 1.0 / 100.0 / sd, 2)) if sd > 1e-10 else 0.01
            open_t = {"entry_time": str(df.index[idx+1]), "dir": sig["direction"],
                       "entry": entry, "sl": sig["sl"], "tp": sig["tp"],
                       "lots": lots, "holding": 0}
        else:
            hit, ep, reason = False, None, ""
            d = open_t["dir"]
            if d == 1:
                if lows[idx+1] <= open_t["sl"]: ep, reason, hit = open_t["sl"], "stop_loss", True
                elif highs[idx+1] >= open_t["tp"]: ep, reason, hit = open_t["tp"], "take_profit", True
            else:
                if highs[idx+1] >= open_t["sl"]: ep, reason, hit = open_t["sl"], "stop_loss", True
                elif lows[idx+1] <= open_t["tp"]: ep, reason, hit = open_t["tp"], "take_profit", True
            open_t["holding"] += 1

            if hit:
                se = open_t["entry"] * spread_bps / 20000
                sx = ep * spread_bps / 20000
                ee = open_t["entry"] + se if d == 1 else open_t["entry"] - se
                ex = ep - sx if d == 1 else ep + sx
                pnl = (ex - ee) * open_t["lots"] if d == 1 else (ee - ex) * open_t["lots"]
                trades.append({"pnl": round(pnl, 2), "reason": reason,
                    "holding": open_t["holding"], "direction": "LONG" if d == 1 else "SHORT"})
                open_t = None
                if sig["direction"] in (1, -1):
                    entry = closes[idx+1]
                    sd = abs(entry - sig["sl"])
                    lots = max(0.01, round(capital / 100.0 / sd, 2)) if sd > 1e-10 else 0.01
                    open_t = {"entry_time": str(df.index[idx+1]), "dir": sig["direction"],
                               "entry": entry, "sl": sig["sl"], "tp": sig["tp"],
                               "lots": lots, "holding": 0}
                continue

            if sig["direction"] == 0 or sig["direction"] != d:
                ep = closes[idx+1]
                se = open_t["entry"] * spread_bps / 20000
                sx = ep * spread_bps / 20000
                ee = open_t["entry"] + se if d == 1 else open_t["entry"] - se
                ex = ep - sx if d == 1 else ep + sx
                pnl = (ex - ee) * open_t["lots"] if d == 1 else (ee - ex) * open_t["lots"]
                trades.append({"pnl": round(pnl, 2), "reason": "signal_exit",
                    "holding": open_t["holding"], "direction": "LONG" if d == 1 else "SHORT"})
                open_t = None
                if sig["direction"] in (1, -1):
                    entry = closes[idx+1]
                    sd = abs(entry - sig["sl"])
                    lots = max(0.01, round(capital / 100.0 / sd, 2)) if sd > 1e-10 else 0.01
                    open_t = {"entry_time": str(df.index[idx+1]), "dir": sig["direction"],
                               "entry": entry, "sl": sig["sl"], "tp": sig["tp"],
                               "lots": lots, "holding": 0}

    if open_t:
        ep = closes[-1]
        d = open_t["dir"]
        se = open_t["entry"] * spread_bps / 20000
        sx = ep * spread_bps / 20000
        ee = open_t["entry"] + se if d == 1 else open_t["entry"] - se
        ex = ep - sx if d == 1 else ep + sx
        pnl = (ex - ee) * open_t["lots"] if d == 1 else (ee - ex) * open_t["lots"]
        trades.append({"pnl": round(pnl, 2), "reason": "end_of_data",
            "holding": open_t["holding"], "direction": "LONG" if d == 1 else "SHORT"})
    return trades

# ── METRICS ─────────────────────────────────────────────────────────
def metrics(trades):
    if not trades:
        return {"total_trades": 0}
    pnls = np.array([t["pnl"] for t in trades])
    n = len(pnls)
    wins = pnls > 0

    # Estimate trades per year from holding bars (assuming H1 = 24 bars/day, 365 days)
    avg_holding = np.mean([t.get("holding", 1) for t in trades])
    bars_per_trade = max(avg_holding, 1)
    bars_per_year = 24 * 365  # H1 bars per year
    trades_per_year = bars_per_year / bars_per_trade if bars_per_trade > 0 else 252

    returns = pnls / INITIAL_CAPITAL
    std = np.std(returns)
    sharpe = float(np.mean(returns) / std * np.sqrt(trades_per_year)) if std > 1e-10 else 0.0
    cum = np.cumsum(pnls)
    dd = float(np.max(np.maximum.accumulate(cum) - cum)) if n > 0 else 0.0
    gp = float(np.sum(pnls[wins])) if np.any(wins) else 0.0
    gl = float(np.sum(pnls[~wins])) if np.any(~wins) else 0.0
    return {
        "total_trades": n,
        "total_pnl": round(float(np.sum(pnls)), 2),
        "win_rate_pct": round(float(np.mean(wins)) * 100, 1),
        "avg_win": round(float(np.mean(pnls[wins])), 2) if np.any(wins) else 0,
        "avg_loss": round(float(np.mean(pnls[~wins])), 2) if np.any(~wins) else 0,
        "profit_factor": round(abs(gp / gl), 2) if gl != 0 else 999,
        "sharpe": round(sharpe, 3),
        "max_drawdown": round(dd, 2),
        "trades_per_year": round(trades_per_year, 1),
    }
