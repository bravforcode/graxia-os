"""
Donchian Deep Dive — Everything Mode
1. Paper trade simulation with risk management (Donchian 20)
2. Fine-tune: scan Donchian period [5..100]
3. Cross-timeframe: EURUSD D1, H4, H1
4. Cross-pair: D1 on EURUSD, GBPUSD, AUDUSD, US30
"""
import numpy as np
import pandas as pd
from pathlib import Path
import json
import os

BASE = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os")
DATA_DIR = BASE / "data"
OUTPUT_DIR = BASE / "reports"
os.makedirs(OUTPUT_DIR, exist_ok=True)

COST_RT_BPS_FX = 3.4
COST_RT_BPS_US30 = 5.0
TRAIN_SPLIT = 0.80
MIN_TRADES = 8
INITIAL_EQUITY = 10_000
RISK_PCT = 0.01  # 1% per trade


# ========================= DATA LOADING =========================
def load_data(filename):
    p = DATA_DIR / filename
    if not p.exists():
        return None
    df = pd.read_csv(p)
    cols_lower = {c.lower(): c for c in df.columns}

    o_col = cols_lower.get("open")
    h_col = cols_lower.get("high")
    l_col = cols_lower.get("low")
    c_col = cols_lower.get("close")
    if not all([o_col, h_col, l_col, c_col]):
        return None

    return (
        pd.to_numeric(df[o_col], errors="coerce").values,
        pd.to_numeric(df[h_col], errors="coerce").values,
        pd.to_numeric(df[l_col], errors="coerce").values,
        pd.to_numeric(df[c_col], errors="coerce").values,
    )


# ========================= DONCHIAN =============================
def donchian_signals(highs, lows, closes, period):
    n = len(closes)
    signals = np.zeros(n, dtype=int)
    position = 0
    for i in range(period, n):
        hh = np.max(highs[i - period : i])
        ll = np.min(lows[i - period : i])
        if closes[i] > hh:
            position = 1
        elif closes[i] < ll:
            position = -1
        signals[i] = position
    return signals


# ========================= PAPER TRADE ==========================
def paper_trade(opens, highs, lows, closes, period, split_idx, cost_rt_bps):
    """Risk-managed paper trade simulation."""
    n = len(closes)
    signals = donchian_signals(highs, lows, closes, period)
    position = 0
    entry_price = 0.0
    entry_idx = 0
    entry_sl_dist = 1.0  # saved from entry for correct PnL
    equity = INITIAL_EQUITY
    equity_curve = [equity]
    trades = []

    # ATR for position sizing
    atr = np.zeros(n)
    for i in range(14, n):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]),
                 abs(lows[i] - closes[i-1]))
        atr[i] = (atr[i-1] * 13 + tr) / 14 if atr[i-1] else tr

    warmup = max(period, 50)
    for i in range(warmup, n):
        bar_label = "IS" if i < split_idx else "OOS"
        signal = signals[i]

        if position == 0 and signal != 0:
            entry_idx = i + 1 if i + 1 < n else i
            entry_price = opens[entry_idx] if i + 1 < n else closes[i]
            # Save stop distance at entry time
            entry_sl_dist = atr[i] * 1.5 if not np.isnan(atr[i]) and atr[i] > 0 else entry_price * 0.01
            position = signal

        elif position != 0 and signal != position:
            exit_idx = i + 1 if i + 1 < n else i
            exit_price = opens[exit_idx] if i + 1 < n else closes[i]

            # Raw return
            if position == 1:
                raw_ret = (exit_price - entry_price) / entry_price
            else:
                raw_ret = (entry_price - exit_price) / entry_price

            # Risk-sized PnL using entry-time stop distance
            sl_ratio = entry_sl_dist / entry_price if entry_price > 0 else 0.01
            net_ret = raw_ret - (cost_rt_bps / 10000.0)
            leveraged = net_ret / (sl_ratio + 1e-10) * RISK_PCT
            equity *= (1.0 + leveraged)

            trades.append({
                "net_return": net_ret,
                "leverage_return": leveraged,
                "bar_label": bar_label,
                "direction": "LONG" if position == 1 else "SHORT",
                "entry_idx": entry_idx,
                "exit_idx": exit_idx,
                "duration": i - entry_idx + 1,
                "equity": round(equity, 2),
            })

            position = 0
            if signal != 0:
                entry_price = exit_price
                entry_idx = exit_idx
                entry_sl_dist = atr[i] * 1.5 if not np.isnan(atr[i]) and atr[i] > 0 else entry_price * 0.01
                position = signal

        equity_curve.append(equity)

    return trades, equity_curve


def compute_metrics(trades, label=None):
    t = [x for x in trades if x["bar_label"] == label] if label else trades
    n = len(t)
    if n < MIN_TRADES:
        return {"n_trades": n, "sharpe": 0, "winrate": 0, "profit_factor": 0,
                "avg_return": 0, "max_dd": 0, "is_valid": False}

    rets = [x["net_return"] for x in t]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r < 0]
    avg_r = np.mean(rets)
    std_r = np.std(rets, ddof=1) if n > 1 else 0
    sharpe = avg_r / (std_r + 1e-10) * np.sqrt(252)
    wr = len(wins) / n * 100
    avg_win = np.mean(wins) if wins else 0
    avg_loss = abs(np.mean(losses)) if losses else 0
    pf = (len(wins) * avg_win) / (len(losses) * avg_loss) if avg_loss > 0 and len(losses) > 0 else 0

    cum = np.cumprod([1 + r for r in rets])
    peak = np.maximum.accumulate(cum)
    dd = (peak - cum) / peak
    max_dd = np.max(dd) * 100

    return {"n_trades": n, "sharpe": round(sharpe, 4),
            "winrate": round(wr, 2), "profit_factor": round(pf, 4),
            "avg_pct": round(avg_r * 100, 4), "max_dd_pct": round(max_dd, 2),
            "is_valid": True}


# ========================= MAIN SCAN ============================
def run_deep_dive():
    print("=" * 70)
    print("  DONCHIAN DEEP DIVE — Everything Mode")
    print("=" * 70)

    # ---- PART A: Fine-tune Donchian on EURUSD D1 ----
    print("\n" + "-" * 70)
    print("  PART A: Fine-Tune Donchian Period [EURUSD D1]")
    print("-" * 70)

    data = load_data("EURUSD_D1_clean.csv")
    if data is None:
        print("  ERROR: EURUSD D1 data not found")
        return
    opens, highs, lows, closes = data
    n = len(closes)
    split_idx = int(n * TRAIN_SPLIT)

    periods_to_test = [5, 10, 15, 20, 25, 30, 40, 55, 80, 100]
    ft_results = []

    for period in periods_to_test:
        trades, eq = paper_trade(opens, highs, lows, closes, period, split_idx, COST_RT_BPS_FX)
        is_m = compute_metrics(trades, "IS")
        oos_m = compute_metrics(trades, "OOS")
        wf = oos_m["sharpe"] / is_m["sharpe"] if is_m["sharpe"] > 0.05 else 0
        final_eq = trades[-1]["equity"] if trades else INITIAL_EQUITY
        total_ret = (final_eq / INITIAL_EQUITY - 1) * 100

        ft_results.append({
            "period": period, "is": is_m, "oos": oos_m,
            "wf_pct": round(wf * 100, 1), "total_return_pct": round(total_ret, 2),
            "final_equity": round(final_eq, 2),
        })

    # Print fine-tune results
    print(f"\n{'Period':<8} {'IS Sharpe':<11} {'OOS Sharpe':<11} {'WF%':<8} "
          f"{'OOS WR':<8} {'OOS Trades':<11} {'Max DD%':<8} {'Return%':<10}")
    print("-" * 80)
    for r in sorted(ft_results, key=lambda x: x["oos"]["sharpe"], reverse=True):
        if r["oos"]["is_valid"]:
            print(f"{r['period']:<8} {r['is']['sharpe']:<11.4f} {r['oos']['sharpe']:<11.4f} "
                  f"{r['wf_pct']:<7.1f}% {r['oos']['winrate']:<7.1f}% "
                  f"{r['oos']['n_trades']:<5}      {r['oos']['max_dd_pct']:<7.1f}% "
                  f"{r['total_return_pct']:<9.1f}%")

    # Best period
    valid_ft = [r for r in ft_results if r["oos"]["is_valid"]]
    if valid_ft:
        best = max(valid_ft, key=lambda x: x["oos"]["sharpe"])
        print(f"\n  BEST: Donchian({best['period']}) — "
              f"IS={best['is']['sharpe']:.2f} OOS={best['oos']['sharpe']:.2f} "
              f"Return={best['total_return_pct']:.1f}%")

    # ---- PART B: Donchian 20 Detailed Paper Trade ----
    print("\n" + "-" * 70)
    print("  PART B: Donchian(20) Detailed Paper Trade [EURUSD D1]")
    print("-" * 70)

    trades, eq = paper_trade(opens, highs, lows, closes, 20, split_idx, COST_RT_BPS_FX)
    is_m = compute_metrics(trades, "IS")
    oos_m = compute_metrics(trades, "OOS")
    final_eq = trades[-1]["equity"] if trades else INITIAL_EQUITY
    total_ret = (final_eq / INITIAL_EQUITY - 1) * 100

    print(f"\n  Initial: ${INITIAL_EQUITY:,.0f} | Final: ${final_eq:,.0f} "
          f"| Return: {total_ret:+.1f}%")
    print(f"\n  {'':20s} {'IS':>12s} {'OOS':>12s} {'ALL':>12s}")
    print(f"  {'-'*20} {'-'*12} {'-'*12} {'-'*12}")
    is_t = [t for t in trades if t["bar_label"] == "IS"]
    oos_t = [t for t in trades if t["bar_label"] == "OOS"]
    print(f"  {'Trades':20s} {len(is_t):>12d} {len(oos_t):>12d} {len(trades):>12d}")
    print(f"  {'Sharpe':20s} {is_m['sharpe']:>12.4f} {oos_m['sharpe']:>12.4f} {'—':>12s}")
    print(f"  {'Win Rate':20s} {is_m['winrate']:>11.1f}% {oos_m['winrate']:>11.1f}% {'—':>12s}")
    print(f"  {'Profit Factor':20s} {is_m['profit_factor']:>12.4f} {oos_m['profit_factor']:>12.4f} {'—':>12s}")
    print(f"  {'Max DD':20s} {is_m['max_dd_pct']:>11.2f}% {oos_m['max_dd_pct']:>11.2f}% {'—':>12s}")

    # Print last 5 trades
    print(f"\n  Last 5 OOS trades:")
    oos_last = [t for t in trades if t["bar_label"] == "OOS"][-5:]
    for t in oos_last:
        print(f"    {t['direction']:5s} | ret={t['leverage_return']*100:+.2f}% | eq={t['equity']:.0f}")

    # ---- PART C: Cross-Timeframe (EURUSD) ----
    print("\n" + "-" * 70)
    print("  PART C: Cross-Timeframe — Donchian(20) on EURUSD")
    print("-" * 70)

    tf_files = {
        "D1": "EURUSD_D1_clean.csv",
        "H4": "EURUSD_H4.csv",
        "H1": "EURUSD_H1.csv",
    }

    tf_results = []
    for tf_name, filename in tf_files.items():
        data = load_data(filename)
        if data is None:
            print(f"  {tf_name}: FILE NOT FOUND")
            continue
        o, h, l, c = data
        n = len(c)
        sp = int(n * TRAIN_SPLIT)
        trades, eq = paper_trade(o, h, l, c, 20, sp, COST_RT_BPS_FX)
        is_m = compute_metrics(trades, "IS")
        oos_m = compute_metrics(trades, "OOS")
        wf = oos_m["sharpe"] / is_m["sharpe"] if is_m["sharpe"] > 0.05 else 0
        final_eq = trades[-1]["equity"] if trades else INITIAL_EQUITY
        total_ret = (final_eq / INITIAL_EQUITY - 1) * 100

        print(f"  {tf_name:4s}: {n:6d} bars | "
              f"IS={is_m['sharpe']:.2f} OOS={oos_m['sharpe']:.2f} "
              f"WR={oos_m['winrate']:.1f}% Trades={oos_m['n_trades']} "
              f"DD={oos_m['max_dd_pct']:.1f}% Ret={total_ret:+.1f}%")

        tf_results.append({
            "timeframe": tf_name, "bars": n, "is": is_m, "oos": oos_m,
            "wf_pct": round(wf * 100, 1), "total_return_pct": total_ret,
        })

    # ---- PART D: Cross-Pair (D1) ----
    print("\n" + "-" * 70)
    print("  PART D: Cross-Pair — Donchian(20) on D1")
    print("-" * 70)

    pair_files = {
        "EURUSD": ("EURUSD_D1_clean.csv", COST_RT_BPS_FX),
        "GBPUSD": ("GBPUSD_D1.csv", COST_RT_BPS_FX),
        "AUDUSD": ("AUDUSD_D1.csv", COST_RT_BPS_FX),
        "US30": ("US30_D1.csv", COST_RT_BPS_US30),
    }

    pair_results = []
    for pair, (filename, cost) in pair_files.items():
        data = load_data(filename)
        if data is None:
            print(f"  {pair:8s}: FILE NOT FOUND")
            continue
        o, h, l, c = data
        n = len(c)
        sp = int(n * TRAIN_SPLIT)
        trades, eq = paper_trade(o, h, l, c, 20, sp, cost)
        is_m = compute_metrics(trades, "IS")
        oos_m = compute_metrics(trades, "OOS")
        wf = oos_m["sharpe"] / is_m["sharpe"] if is_m["sharpe"] > 0.05 else 0
        final_eq = trades[-1]["equity"] if trades else INITIAL_EQUITY
        total_ret = (final_eq / INITIAL_EQUITY - 1) * 100

        print(f"  {pair:8s}: {n:6d} bars | "
              f"IS={is_m['sharpe']:.2f} OOS={oos_m['sharpe']:.2f} "
              f"WR={oos_m['winrate']:.1f}% Trades={oos_m['n_trades']} "
              f"DD={oos_m['max_dd_pct']:.1f}% Ret={total_ret:+.1f}%")

        pair_results.append({
            "pair": pair, "bars": n, "cost_rt_bps": cost,
            "is": is_m, "oos": oos_m,
            "wf_pct": round(wf * 100, 1), "total_return_pct": total_ret,
        })

    # ---- SAVE ALL ----
    output = {
        "date": pd.Timestamp.now().isoformat(),
        "strategy": "Donchian Breakout",
        "cost_models": {"FX": f"{COST_RT_BPS_FX} bps/RT", "US30": f"{COST_RT_BPS_US30} bps/RT"},
        "fine_tune": ft_results,
        "paper_trade_d20": {
            "is": is_m, "oos": oos_m, "total_return_pct": total_ret,
            "final_equity": final_eq,
        },
        "cross_timeframe": tf_results,
        "cross_pair": pair_results,
    }

    out_path = OUTPUT_DIR / "donchian_deep_dive.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n{'='*70}")
    print(f"  Saved: {out_path}")
    print(f"{'='*70}")
    print("  DEEP DIVE COMPLETE")
    print(f"{'='*70}")


if __name__ == "__main__":
    run_deep_dive()
