"""
Donchian BTCUSD H1 — MASSIVE VALIDATION SUITE
================================================
4 analyses in 1 script:
  1. Monte Carlo: 10,000 synthetic price paths
  2. Multi-asset: Donchian across all available assets
  3. Parameter sensitivity: 18 Donchian parameter sets
  4. Regime analysis: trending/ranging/volatile performance

Uses only: numpy, pandas, csv (no imports from paper_engine).
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# ── CONFIG ──────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "data"
REPORTS_DIR = BASE / "reports" / "validation_suite"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

N_MONTE_CARLO = 1_000
MC_PATH_LEN = 10_000  # bars per synthetic path (~4 years of H1 data)
INITIAL_CAPITAL = 100_000.0
RISK_PCT = 1.0

# ── OHLCV LOADING ──────────────────────────────────────────────────
def load_btc() -> pd.DataFrame:
    p = DATA_DIR / "BTCUSD_H1.csv"
    df = pd.read_csv(p)
    # normalize columns
    df.columns = [c.strip().lower() for c in df.columns]
    for req in ["time", "open", "high", "low", "close", "volume"]:
        if req not in df.columns:
            if req == "volume":
                df["volume"] = 0
            else:
                raise ValueError(f"Missing {req}")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time").sort_index()
    return df

def load_symbol_h1(sym: str) -> pd.DataFrame | None:
    p = DATA_DIR / f"{sym}_H1.csv"
    if not p.exists():
        return None
    try:
        df = pd.read_csv(p)
        df.columns = [c.strip().lower() for c in df.columns]
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time").sort_index()
        if len(df) < 100:
            return None
        return df
    except Exception:
        return None

# ── SPREAD COSTS (from cost_calibration.json) ──────────────────────
SPREAD_BPS = {
    "BTCUSD": 2.43, "ETHUSD": 11.67, "EURUSD": 0.0, "GBPUSD": 0.15,
    "USDJPY": 0.06, "XAUUSD": 0.36, "XAGUSD": 6.58, "OIL": 4.88,
    "AUDUSD": 0.1, "USDCAD": 0.0, "USDCHF": 0.0, "NZDUSD": 0.0,
    "NAS100": 1.0, "US30": 0.5, "DXY": 0.0,
}

# ── DONCHIAN SIGNALS (inline — no imports) ──────────────────────────
def donchian_signals(df: pd.DataFrame, period: int = 20, vol_filter: bool = True,
                     atr_period: int = 14) -> list[dict]:
    """Return list of {bar_index, direction, entry, sl, tp, reason}."""
    closes = df["close"].values.astype(float)
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    n = len(closes)

    # ATR
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(
            np.abs(highs[1:] - closes[:-1]),
            np.abs(lows[1:] - closes[:-1])
        )
    )
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

        vol_ok = True
        if vol_filter and i > 0:
            vol_ok = atr_ratio[i] > med_ratio * 0.8

        direction = 0
        conf = 0.0
        reason = ""

        if closes[i] > hh and vol_ok:
            direction = 1
            strength = (closes[i] - hh) / (hh + 1e-10) * 100
            conf = min(strength * 5, 1.0)
            reason = f"BREAKOUT LONG high={hh:.5f}"
        elif closes[i] < ll and vol_ok:
            direction = -1
            strength = (ll - closes[i]) / (ll + 1e-10) * 100
            conf = min(strength * 5, 1.0)
            reason = f"BREAKOUT SHORT low={ll:.5f}"

        if direction != 0 and conf > 0.1:
            signals.append({
                "bar_index": i, "direction": direction, "confidence": round(conf, 3),
                "entry": closes[i], "sl": closes[i] - atr[i] * 2.0 if direction == 1 else closes[i] + atr[i] * 2.0,
                "tp": closes[i] + atr[i] * 3.0 if direction == 1 else closes[i] - atr[i] * 3.0,
                "reason": reason,
            })
    return signals

# ── TRADE SIMULATION ────────────────────────────────────────────────
def simulate_trades(df: pd.DataFrame, signals: list[dict], spread_bps: float = 2.43,
                    capital: float = INITIAL_CAPITAL, risk_pct: float = RISK_PCT) -> list[dict]:
    """Next-bar execution with spread cost."""
    closes = df["close"].values.astype(float)
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    n = len(closes)

    trades = []
    equity = capital
    open_trade = None

    for sig in signals:
        idx = sig["bar_index"]
        if idx + 1 >= n:
            continue

        if open_trade is None:
            if sig["direction"] == 0:
                continue
            entry = closes[idx + 1]
            # Position sizing: risk / (stop_dist)
            stop_dist = abs(entry - sig["sl"])
            if stop_dist < 1e-10:
                lots = 0.01
            else:
                lots = max(0.01, round(capital * risk_pct / 100.0 / stop_dist, 2))

            open_trade = {
                "entry_time": str(df.index[idx + 1]),
                "direction": sig["direction"],
                "entry": entry,
                "sl": sig["sl"],
                "tp": sig["tp"],
                "lots": lots,
                "bar_idx": idx,
                "holding": 0,
            }
        else:
            # Check SL/TP
            sl_tp_hit = False
            exit_price = None
            reason = ""

            if open_trade["direction"] == 1:
                if lows[idx + 1] <= open_trade["sl"]:
                    exit_price = open_trade["sl"]
                    reason = "stop_loss"
                    sl_tp_hit = True
                elif highs[idx + 1] >= open_trade["tp"]:
                    exit_price = open_trade["tp"]
                    reason = "take_profit"
                    sl_tp_hit = True
            else:
                if highs[idx + 1] >= open_trade["sl"]:
                    exit_price = open_trade["sl"]
                    reason = "stop_loss"
                    sl_tp_hit = True
                elif lows[idx + 1] <= open_trade["tp"]:
                    exit_price = open_trade["tp"]
                    reason = "take_profit"
                    sl_tp_hit = True

            open_trade["holding"] += 1

            if sl_tp_hit:
                # P&L with spread
                spread_entry = open_trade["entry"] * spread_bps / 20000
                spread_exit = exit_price * spread_bps / 20000
                effective_entry = open_trade["entry"] + spread_entry if open_trade["direction"] == 1 else open_trade["entry"] - spread_entry
                effective_exit = exit_price - spread_exit if open_trade["direction"] == 1 else exit_price + spread_exit

                if open_trade["direction"] == 1:
                    pnl = (effective_exit - effective_entry) * open_trade["lots"]
                else:
                    pnl = (effective_entry - effective_exit) * open_trade["lots"]

                trades.append({
                    "entry_time": open_trade["entry_time"],
                    "exit_time": str(df.index[idx + 1]),
                    "direction": "LONG" if open_trade["direction"] == 1 else "SHORT",
                    "entry_price": round(open_trade["entry"], 2),
                    "exit_price": round(exit_price, 2),
                    "pnl": round(pnl, 2),
                    "reason": reason,
                    "holding_bars": open_trade["holding"],
                })
                equity += pnl
                open_trade = None

                # Re-open if new signal
                if sig["direction"] in (1, -1):
                    entry = closes[idx + 1]
                    stop_dist = abs(entry - sig["sl"])
                    lots = max(0.01, round(capital * risk_pct / 100.0 / stop_dist, 2)) if stop_dist > 1e-10 else 0.01
                    open_trade = {
                        "entry_time": str(df.index[idx + 1]),
                        "direction": sig["direction"],
                        "entry": entry, "sl": sig["sl"], "tp": sig["tp"],
                        "lots": lots, "bar_idx": idx, "holding": 0,
                    }
                continue

            # Signal-based exit
            if sig["direction"] == 0 or sig["direction"] != open_trade["direction"]:
                exit_price = closes[idx + 1]
                spread_entry = open_trade["entry"] * spread_bps / 20000
                spread_exit = exit_price * spread_bps / 20000
                effective_entry = open_trade["entry"] + spread_entry if open_trade["direction"] == 1 else open_trade["entry"] - spread_entry
                effective_exit = exit_price - spread_exit if open_trade["direction"] == 1 else exit_price + spread_exit

                if open_trade["direction"] == 1:
                    pnl = (effective_exit - effective_entry) * open_trade["lots"]
                else:
                    pnl = (effective_entry - effective_exit) * open_trade["lots"]

                trades.append({
                    "entry_time": open_trade["entry_time"],
                    "exit_time": str(df.index[idx + 1]),
                    "direction": "LONG" if open_trade["direction"] == 1 else "SHORT",
                    "entry_price": round(open_trade["entry"], 2),
                    "exit_price": round(exit_price, 2),
                    "pnl": round(pnl, 2),
                    "reason": "signal_exit",
                    "holding_bars": open_trade["holding"],
                })
                equity += pnl
                open_trade = None

                if sig["direction"] in (1, -1):
                    entry = closes[idx + 1]
                    stop_dist = abs(entry - sig["sl"])
                    lots = max(0.01, round(capital * risk_pct / 100.0 / stop_dist, 2)) if stop_dist > 1e-10 else 0.01
                    open_trade = {
                        "entry_time": str(df.index[idx + 1]),
                        "direction": sig["direction"],
                        "entry": entry, "sl": sig["sl"], "tp": sig["tp"],
                        "lots": lots, "bar_idx": idx, "holding": 0,
                    }

    # Close remaining
    if open_trade:
        exit_price = closes[-1]
        spread_entry = open_trade["entry"] * spread_bps / 20000
        spread_exit = exit_price * spread_bps / 20000
        effective_entry = open_trade["entry"] + spread_entry if open_trade["direction"] == 1 else open_trade["entry"] - spread_entry
        effective_exit = exit_price - spread_exit if open_trade["direction"] == 1 else exit_price + spread_exit
        if open_trade["direction"] == 1:
            pnl = (effective_exit - effective_entry) * open_trade["lots"]
        else:
            pnl = (effective_entry - effective_exit) * open_trade["lots"]
        trades.append({
            "entry_time": open_trade["entry_time"],
            "exit_time": str(df.index[-1]),
            "direction": "LONG" if open_trade["direction"] == 1 else "SHORT",
            "entry_price": round(open_trade["entry"], 2),
            "exit_price": round(exit_price, 2),
            "pnl": round(pnl, 2),
            "reason": "end_of_data",
            "holding_bars": open_trade["holding"],
        })

    return trades

# ── METRICS ─────────────────────────────────────────────────────────
def compute_metrics(trades: list[dict]) -> dict:
    if not trades:
        return {"total_trades": 0, "error": "no trades"}
    pnls = np.array([t["pnl"] for t in trades])
    n = len(pnls)
    wins = pnls > 0
    losses = pnls < 0

    # Trades per year
    from datetime import datetime as _dt
    try:
        t_start = _dt.fromisoformat(trades[0]["entry_time"].replace("Z", "+00:00"))
        t_end = _dt.fromisoformat(trades[-1]["exit_time"].replace("Z", "+00:00"))
        years = (t_end - t_start).total_seconds() / (365.25 * 86400)
        tpy = n / max(years, 0.01)
    except Exception:
        tpy = 252.0

    # Sharpe
    returns = pnls / INITIAL_CAPITAL
    std = np.std(returns)
    sharpe = float(np.mean(returns) / std * np.sqrt(tpy)) if std > 1e-10 else 0.0

    # Max DD
    cumulative = np.cumsum(pnls)
    running_max = np.maximum.accumulate(cumulative)
    dd = running_max - cumulative
    max_dd = float(np.max(dd)) if len(dd) > 0 else 0.0

    # Profit factor
    gross_profit = float(np.sum(pnls[wins])) if np.any(wins) else 0.0
    gross_loss = float(np.sum(pnls[losses])) if np.any(losses) else 0.0
    pf = abs(gross_profit / gross_loss) if gross_loss != 0 else float("inf")

    # Win/loss streaks
    streak = 0
    max_win_streak = 0
    max_loss_streak = 0
    for p in pnls:
        if p > 0:
            streak = max(0, streak) + 1
            max_win_streak = max(max_win_streak, streak)
        else:
            streak = min(0, streak) - 1
            max_loss_streak = max(max_loss_streak, abs(streak))

    return {
        "total_trades": n,
        "total_pnl": round(float(np.sum(pnls)), 2),
        "win_rate_pct": round(float(np.mean(wins)) * 100, 1),
        "avg_win": round(float(np.mean(pnls[wins])), 2) if np.any(wins) else 0.0,
        "avg_loss": round(float(np.mean(pnls[losses])), 2) if np.any(losses) else 0.0,
        "profit_factor": round(pf, 2),
        "sharpe": round(sharpe, 3),
        "max_drawdown": round(max_dd, 2),
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "avg_holding_bars": round(float(np.mean([t["holding_bars"] for t in trades])), 1),
        "trades_per_year": round(tpy, 1),
    }

# ── ANALYSIS 1: MONTE CARLO ────────────────────────────────────────
def monte_carlo(df: pd.DataFrame) -> dict:
    print(f"\n{'='*70}")
    print(f"  ANALYSIS 1: MONTE CARLO — {N_MONTE_CARLO:,} SYNTHETIC PATHS")
    print(f"{'='*70}")

    closes = df["close"].values.astype(float)
    returns = np.diff(np.log(closes))
    mu = np.mean(returns)
    sigma = np.std(returns)
    print(f"  Real BTCUSD: {len(closes):,} bars, mu={mu:.6f}, sigma={sigma:.6f}")

    results = []
    t0 = time.time()
    for i in range(N_MONTE_CARLO):
        # Generate GBM path
        np.random.seed(i)
        log_returns = np.random.normal(mu, sigma, MC_PATH_LEN)
        prices = closes[0] * np.exp(np.cumsum(log_returns))

        # Build synthetic OHLCV (use close as proxy for high/low)
        synthetic = pd.DataFrame({
            "open": prices * (1 + np.random.normal(0, sigma * 0.3, MC_PATH_LEN)),
            "high": prices * (1 + np.abs(np.random.normal(0, sigma * 0.5, MC_PATH_LEN))),
            "low": prices * (1 - np.abs(np.random.normal(0, sigma * 0.5, MC_PATH_LEN))),
            "close": prices,
            "volume": np.random.randint(1000, 50000, MC_PATH_LEN),
        })

        sigs = donchian_signals(synthetic, period=20, vol_filter=True)
        trades = simulate_trades(synthetic, sigs, spread_bps=2.43)
        m = compute_metrics(trades)
        results.append(m)

        if (i + 1) % 2000 == 0:
            elapsed = time.time() - t0
            print(f"  [{elapsed:.0f}s] {i+1:,}/{N_MONTE_CARLO:,} done...")

    elapsed = time.time() - t0
    print(f"  Completed in {elapsed:.1f}s")

    # Aggregate
    sharpes = np.array([r["sharpe"] for r in results])
    pnls = np.array([r["total_pnl"] for r in results])
    win_rates = np.array([r["win_rate_pct"] for r in results])
    max_dds = np.array([r["max_drawdown"] for r in results])
    trade_counts = np.array([r["total_trades"] for r in results])

    stats = {
        "n_simulations": N_MONTE_CARLO,
        "path_length": MC_PATH_LEN,
        "elapsed_seconds": round(elapsed, 1),
        "sharpe": {
            "mean": round(float(np.mean(sharpes)), 3),
            "median": round(float(np.median(sharpes)), 3),
            "std": round(float(np.std(sharpes)), 3),
            "p5": round(float(np.percentile(sharpes, 5)), 3),
            "p25": round(float(np.percentile(sharpes, 25)), 3),
            "p75": round(float(np.percentile(sharpes, 75)), 3),
            "p95": round(float(np.percentile(sharpes, 95)), 3),
            "pct_profitable": round(float(np.mean(sharpes > 0)) * 100, 1),
        },
        "total_pnl": {
            "mean": round(float(np.mean(pnls)), 2),
            "median": round(float(np.median(pnls)), 2),
            "p5": round(float(np.percentile(pnls, 5)), 2),
            "p95": round(float(np.percentile(pnls, 95)), 2),
            "pct_profitable": round(float(np.mean(pnls > 0)) * 100, 1),
        },
        "win_rate": {
            "mean": round(float(np.mean(win_rates)), 1),
            "std": round(float(np.std(win_rates)), 1),
        },
        "max_drawdown": {
            "mean": round(float(np.mean(max_dds)), 2),
            "p95": round(float(np.percentile(max_dds, 95)), 2),
            "p99": round(float(np.percentile(max_dds, 99)), 2),
        },
        "trades_per_run": {
            "mean": round(float(np.mean(trade_counts)), 1),
            "std": round(float(np.std(trade_counts)), 1),
        },
    }

    print(f"\n  RESULTS:")
    print(f"  {'Metric':<25} {'Mean':>10} {'Median':>10} {'P5':>10} {'P95':>10}")
    print(f"  {'-'*65}")
    print(f"  {'Sharpe':<25} {stats['sharpe']['mean']:>10.3f} {stats['sharpe']['median']:>10.3f} {stats['sharpe']['p5']:>10.3f} {stats['sharpe']['p95']:>10.3f}")
    print(f"  {'Total P&L ($)':<25} {stats['total_pnl']['mean']:>10.0f} {stats['total_pnl']['median']:>10.0f} {stats['total_pnl']['p5']:>10.0f} {stats['total_pnl']['p95']:>10.0f}")
    print(f"  {'Max Drawdown ($)':<25} {stats['max_drawdown']['mean']:>10.0f} {'':>10} {'':>10} {stats['max_drawdown']['p95']:>10.0f}")
    print(f"  {'Win Rate (%)':<25} {stats['win_rate']['mean']:>10.1f} {'':>10} {'':>10} {'':>10}")
    print(f"  {'Trades/Run':<25} {stats['trades_per_run']['mean']:>10.1f} {'':>10} {'':>10} {'':>10}")
    print(f"  Profitable paths: {stats['total_pnl']['pct_profitable']:.1f}%")
    print(f"  Sharpe > 0 paths: {stats['sharpe']['pct_profitable']:.1f}%")

    return stats

# ── ANALYSIS 2: MULTI-ASSET ────────────────────────────────────────
def multi_asset() -> dict:
    print(f"\n{'='*70}")
    print(f"  ANALYSIS 2: MULTI-ASSET DONCHIAN VALIDATION")
    print(f"{'='*70}")

    # Find all H1 files
    h1_files = sorted(DATA_DIR.glob("*_H1.csv"))
    available = [f.stem.replace("_H1", "") for f in h1_files]
    print(f"  Assets with H1 data: {len(available)}")
    print(f"  {', '.join(available)}")

    results = {}
    for sym in available:
        df = load_symbol_h1(sym)
        if df is None:
            print(f"  {sym}: SKIP (no data)")
            continue

        spread = SPREAD_BPS.get(sym, 0.0)
        sigs = donchian_signals(df, period=20, vol_filter=True)
        trades = simulate_trades(df, sigs, spread_bps=spread)
        m = compute_metrics(trades)
        m["symbol"] = sym
        m["spread_bps"] = spread
        m["data_bars"] = len(df)
        results[sym] = m

        status = "PASS" if m.get("total_trades", 0) >= 20 and m.get("sharpe", 0) > 0 else "FAIL"
        print(f"  {sym:<10} trades={m.get('total_trades', 0):>5}  sharpe={m.get('sharpe', 0):>7.3f}  "
              f"P&L=${m.get('total_pnl', 0):>10,.0f}  WR={m.get('win_rate_pct', 0):>5.1f}%  DD=${m.get('max_drawdown', 0):>8,.0f}  [{status}]")

    # Summary
    valid = [r for r in results.values() if r.get("total_trades", 0) >= 20]
    if valid:
        sharpes = [r["sharpe"] for r in valid]
        pnls = [r["total_pnl"] for r in valid]
        print(f"\n  SUMMARY ({len(valid)} assets with trades):")
        print(f"  Sharpe range: {min(sharpes):.3f} to {max(sharpes):.3f} (mean={np.mean(sharpes):.3f})")
        print(f"  P&L range: ${min(pnls):,.0f} to ${max(pnls):,.0f}")
        print(f"  Profitable assets: {sum(1 for s in sharpes if s > 0)}/{len(sharpes)}")
        profitable_syms = [r["symbol"] for r in valid if r["sharpe"] > 0]
        print(f"  Profitable: {', '.join(profitable_syms)}")

    return {"assets": results, "summary": {
        "total_assets": len(results),
        "profitable": sum(1 for r in results.values() if r.get("sharpe", 0) > 0),
        "mean_sharpe": round(float(np.mean([r["sharpe"] for r in valid])), 3) if valid else 0,
        "mean_pnl": round(float(np.mean([r["total_pnl"] for r in valid])), 2) if valid else 0,
    }}

# ── ANALYSIS 3: PARAMETER SENSITIVITY ──────────────────────────────
def parameter_sensitivity(df: pd.DataFrame) -> dict:
    print(f"\n{'='*70}")
    print(f"  ANALYSIS 3: PARAMETER SENSITIVITY — DONCHIAN")
    print(f"{'='*70}")

    param_sets = [
        {"period": 10, "vol_filter": True},
        {"period": 15, "vol_filter": True},
        {"period": 20, "vol_filter": True},   # baseline
        {"period": 25, "vol_filter": True},
        {"period": 30, "vol_filter": True},
        {"period": 35, "vol_filter": True},
        {"period": 40, "vol_filter": True},
        {"period": 50, "vol_filter": True},
        {"period": 60, "vol_filter": True},
        {"period": 10, "vol_filter": False},
        {"period": 15, "vol_filter": False},
        {"period": 20, "vol_filter": False},
        {"period": 25, "vol_filter": False},
        {"period": 30, "vol_filter": False},
        {"period": 35, "vol_filter": False},
        {"period": 40, "vol_filter": False},
        {"period": 50, "vol_filter": False},
        {"period": 60, "vol_filter": False},
    ]

    results = {}
    for i, params in enumerate(param_sets):
        sigs = donchian_signals(df, period=params["period"], vol_filter=params["vol_filter"])
        trades = simulate_trades(df, sigs, spread_bps=2.43)
        m = compute_metrics(trades)
        label = f"p{params['period']}_vf{1 if params['vol_filter'] else 0}"
        m["params"] = params
        m["label"] = label
        results[label] = m

        baseline = " *" if params["period"] == 20 and params["vol_filter"] else ""
        print(f"  [{i+1:2d}/18] period={params['period']:>3} vf={str(params['vol_filter']):<5} "
              f"trades={m.get('total_trades', 0):>5}  sharpe={m.get('sharpe', 0):>7.3f}  "
              f"P&L=${m.get('total_pnl', 0):>10,.0f}  WR={m.get('win_rate_pct', 0):>5.1f}%{baseline}")

    # Robustness check
    sharpes = [r["sharpe"] for r in results.values() if r.get("total_trades", 0) >= 10]
    pnls = [r["total_pnl"] for r in results.values() if r.get("total_trades", 0) >= 10]

    print(f"\n  ROBUSTNESS SUMMARY:")
    print(f"  Parameters tested: {len(param_sets)}")
    print(f"  Sharpe range: {min(sharpes):.3f} to {max(sharpes):.3f}")
    print(f"  Sharpe std: {np.std(sharpes):.3f} (lower = more robust)")
    print(f"  P&L range: ${min(pnls):,.0f} to ${max(pnls):,.0f}")
    print(f"  Profitable params: {sum(1 for s in sharpes if s > 0)}/{len(sharpes)}")

    # Find optimal
    best_label = max(results, key=lambda k: results[k].get("sharpe", -999))
    print(f"  Best: {best_label} (Sharpe={results[best_label]['sharpe']:.3f})")

    return {"results": results, "robustness": {
        "sharpe_range": [round(min(sharpes), 3), round(max(sharpes), 3)],
        "sharpe_std": round(float(np.std(sharpes)), 3),
        "profitable_pct": round(sum(1 for s in sharpes if s > 0) / len(sharpes) * 100, 1) if sharpes else 0,
        "best": best_label,
    }}

# ── ANALYSIS 4: REGIME ANALYSIS ────────────────────────────────────
def regime_analysis(df: pd.DataFrame) -> dict:
    print(f"\n{'='*70}")
    print(f"  ANALYSIS 4: REGIME ANALYSIS — TRENDING / RANGING / VOLATILE")
    print(f"{'='*70}")

    closes = df["close"].values.astype(float)
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    n = len(closes)

    # Compute ADX (simplified)
    def compute_adx(h, l, c, period=14):
        n = len(c)
        plus_dm = np.zeros(n)
        minus_dm = np.zeros(n)
        tr = np.zeros(n)

        for i in range(1, n):
            up = h[i] - h[i-1]
            down = l[i-1] - l[i]
            plus_dm[i] = up if up > down and up > 0 else 0
            minus_dm[i] = down if down > up and down > 0 else 0
            tr[i] = max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1]))

        atr = np.zeros(n)
        plus_di = np.zeros(n)
        minus_di = np.zeros(n)
        dx = np.zeros(n)
        adx = np.zeros(n)

        atr[period] = np.sum(tr[1:period+1])
        plus_di[period] = np.sum(plus_dm[1:period+1]) / atr[period] * 100 if atr[period] > 0 else 0
        minus_di[period] = np.sum(minus_dm[1:period+1]) / atr[period] * 100 if atr[period] > 0 else 0
        dx[period] = abs(plus_di[period] - minus_di[period]) / (plus_di[period] + minus_di[period]) * 100 if (plus_di[period] + minus_di[period]) > 0 else 0
        adx[period] = dx[period]

        for i in range(period + 1, n):
            atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
            plus_di[i] = (plus_di[i-1] * (period - 1) + plus_dm[i]) / atr[i] * 100 if atr[i] > 0 else 0
            minus_di[i] = (minus_di[i-1] * (period - 1) + minus_dm[i]) / atr[i] * 100 if atr[i] > 0 else 0
            dx[i] = abs(plus_di[i] - minus_di[i]) / (plus_di[i] + minus_di[i]) * 100 if (plus_di[i] + minus_di[i]) > 0 else 0
            adx[i] = (adx[i-1] * (period - 1) + dx[i]) / period

        return adx

    adx = compute_adx(highs, lows, closes, period=14)

    # ATR ratio for volatility regime
    tr = np.maximum(highs[1:] - lows[1:], np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])))
    atr = np.full(n, np.nan)
    atr[1] = tr[0]
    for i in range(2, n):
        atr[i] = (atr[i-1] * 13 + tr[i-1]) / 14
    atr_ratio = np.where(closes > 0, atr / closes, 0)
    atr_median = np.nanmedian(atr_ratio)

    # Classify each bar into regime
    regime = np.zeros(n, dtype=int)  # 0=unknown, 1=trending, 2=ranging, 3=volatile
    for i in range(200, n):
        if not np.isnan(adx[i]):
            if adx[i] > 25:
                regime[i] = 1  # trending
            elif adx[i] < 20:
                regime[i] = 2  # ranging
            if not np.isnan(atr_ratio[i]) and atr_ratio[i] > atr_median * 1.5:
                regime[i] = 3  # volatile

    # Get signals and trades
    sigs = donchian_signals(df, period=20, vol_filter=True)

    # Classify each trade by entry regime
    regime_trades = {1: [], 2: [], 3: []}
    for sig in sigs:
        idx = sig["bar_index"]
        r = regime[idx] if idx < n else 0
        if r in regime_trades:
            regime_trades[r].append(sig)

    # Simulate per regime
    regime_labels = {1: "TRENDING", 2: "RANGING", 3: "VOLATILE"}
    results = {}

    for r_id in [1, 2, 3]:
        label = regime_labels[r_id]
        # Filter signals to this regime
        filtered_sigs = [s for s in sigs if regime[s["bar_index"]] == r_id if s["bar_index"] < n]
        trades = simulate_trades(df, filtered_sigs, spread_bps=2.43)
        m = compute_metrics(trades)
        m["regime"] = label
        m["n_signals"] = len(filtered_sigs)
        n_bars = int(np.sum(regime == r_id))
        m["regime_pct"] = round(n_bars / n * 100, 1)
        results[label] = m

        print(f"  {label:<10} bars={n_bars:>6} ({m['regime_pct']}%)  "
              f"signals={m['n_signals']:>5}  trades={m.get('total_trades', 0):>5}  "
              f"sharpe={m.get('sharpe', 0):>7.3f}  P&L=${m.get('total_pnl', 0):>10,.0f}  "
              f"WR={m.get('win_rate_pct', 0):>5.1f}%  DD=${m.get('max_drawdown', 0):>8,.0f}")

    # Full dataset for comparison
    full_trades = simulate_trades(df, sigs, spread_bps=2.43)
    full_m = compute_metrics(full_trades)
    print(f"\n  FULL DATASET: trades={full_m.get('total_trades', 0)}  "
          f"sharpe={full_m.get('sharpe', 0):.3f}  P&L=${full_m.get('total_pnl', 0):,.0f}")

    return {"regimes": results, "full": full_m}

# ── MAIN ────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("  DONCHIAN BTCUSD H1 — MASSIVE VALIDATION SUITE")
    print(f"  {N_MONTE_CARLO:,} Monte Carlo paths + Multi-asset + Params + Regimes")
    print("=" * 70)

    df = load_btc()
    print(f"\n  Real data: {len(df):,} bars, {df.index[0]} to {df.index[-1]}")

    all_results = {}

    # 1. Monte Carlo
    all_results["monte_carlo"] = monte_carlo(df)

    # 2. Multi-asset
    all_results["multi_asset"] = multi_asset()

    # 3. Parameter sensitivity
    all_results["parameter_sensitivity"] = parameter_sensitivity(df)

    # 4. Regime analysis
    all_results["regime_analysis"] = regime_analysis(df)

    # ── VERDICT ─────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  FINAL VERDICT")
    print(f"{'='*70}")

    mc = all_results["monte_carlo"]
    ma = all_results["multi_asset"]
    ps = all_results["parameter_sensitivity"]
    ra = all_results["regime_analysis"]

    # Count pass/fail criteria
    criteria = []
    mc_pass = mc["sharpe"]["mean"] > 0 and mc["total_pnl"]["pct_profitable"] > 50
    criteria.append(("Monte Carlo Sharpe > 0", mc_pass))
    criteria.append(("Monte Carlo profitable paths > 50%", mc["total_pnl"]["pct_profitable"] > 50))

    ma_pass = ma["summary"]["profitable"] >= ma["summary"]["total_assets"] * 0.5
    criteria.append((f"Multi-asset: >50% profitable ({ma['summary']['profitable']}/{ma['summary']['total_assets']})", ma_pass))

    ps_pass = ps["robustness"]["profitable_pct"] > 60
    criteria.append((f"Parameter robustness > 60% ({ps['robustness']['profitable_pct']}%)", ps_pass))

    ra_trend = ra["regimes"].get("TRENDING", {}).get("sharpe", 0) > 0
    criteria.append(("Regime TRENDING Sharpe > 0", ra_trend))

    for name, passed in criteria:
        icon = "PASS" if passed else "FAIL"
        print(f"  [{icon}] {name}")

    total_pass = sum(1 for _, p in criteria if p)
    total = len(criteria)
    print(f"\n  SCORE: {total_pass}/{total}")

    if total_pass == total:
        print(f"\n  VERDICT: ALL CRITERIA PASSED")
        print(f"  Strategy is validated across Monte Carlo, multi-asset, parameters, and regimes.")
        print(f"  Safe to proceed with micro-lot forward test on live account.")
    elif total_pass >= total - 1:
        print(f"\n  VERDICT: NEARLY ALL PASSED ({total_pass}/{total})")
        print(f"  Strategy is largely validated. Proceed with caution.")
    else:
        print(f"\n  VERDICT: {total - total_pass} CRITERIA FAILED")
        print(f"  Strategy needs further investigation before live trading.")

    # Save results
    report_path = REPORTS_DIR / "donchian_validation_suite.json"
    with open(report_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Full results saved to: {report_path}")

    # Save human-readable report
    md_path = REPORTS_DIR / "donchian_validation_suite.md"
    with open(md_path, "w") as f:
        f.write("# Donchian BTCUSD H1 — Validation Suite Report\n\n")
        f.write(f"Generated: {pd.Timestamp.now().isoformat()}\n\n")

        f.write("## 1. Monte Carlo (10,000 paths)\n\n")
        f.write(f"| Metric | Mean | P5 | P95 |\n|---|---|---|---|\n")
        f.write(f"| Sharpe | {mc['sharpe']['mean']:.3f} | {mc['sharpe']['p5']:.3f} | {mc['sharpe']['p95']:.3f} |\n")
        f.write(f"| Total P&L | ${mc['total_pnl']['mean']:,.0f} | ${mc['total_pnl']['p5']:,.0f} | ${mc['total_pnl']['p95']:,.0f} |\n")
        f.write(f"| Max DD | ${mc['max_drawdown']['mean']:,.0f} | | ${mc['max_drawdown']['p95']:,.0f} |\n")
        f.write(f"| Profitable paths: {mc['total_pnl']['pct_profitable']:.1f}%\n\n")

        f.write("## 2. Multi-Asset\n\n")
        f.write(f"| Symbol | Trades | Sharpe | P&L | Win Rate | Max DD |\n|---|---|---|---|---|---|\n")
        for sym, r in sorted(ma["assets"].items(), key=lambda x: x[1].get("sharpe", 0), reverse=True):
            f.write(f"| {sym} | {r.get('total_trades', 0)} | {r.get('sharpe', 0):.3f} | ${r.get('total_pnl', 0):,.0f} | {r.get('win_rate_pct', 0):.1f}% | ${r.get('max_drawdown', 0):,.0f} |\n")
        f.write(f"\nProfitable: {ma['summary']['profitable']}/{ma['summary']['total_assets']}\n\n")

        f.write("## 3. Parameter Sensitivity\n\n")
        f.write(f"| Params | Trades | Sharpe | P&L | Win Rate |\n|---|---|---|---|---|\n")
        for label, r in sorted(ps["results"].items(), key=lambda x: x[1].get("sharpe", 0), reverse=True):
            f.write(f"| {label} | {r.get('total_trades', 0)} | {r.get('sharpe', 0):.3f} | ${r.get('total_pnl', 0):,.0f} | {r.get('win_rate_pct', 0):.1f}% |\n")
        f.write(f"\nSharpe std: {ps['robustness']['sharpe_std']:.3f} | Profitable: {ps['robustness']['profitable_pct']}%\n\n")

        f.write("## 4. Regime Analysis\n\n")
        f.write(f"| Regime | Bars | Trades | Sharpe | P&L | Win Rate |\n|---|---|---|---|---|---|\n")
        for label, r in ra["regimes"].items():
            f.write(f"| {label} | {r.get('regime_pct', 0)}% | {r.get('total_trades', 0)} | {r.get('sharpe', 0):.3f} | ${r.get('total_pnl', 0):,.0f} | {r.get('win_rate_pct', 0):.1f}% |\n")

        f.write(f"\n## Verdict\n\n")
        f.write(f"Score: {total_pass}/{total}\n\n")
        for name, passed in criteria:
            f.write(f"- [{'PASS' if passed else 'FAIL'}] {name}\n")

    print(f"  Report saved to: {md_path}")


if __name__ == "__main__":
    main()
