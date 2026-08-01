"""
High-Frequency Strategy Scanner — Target 50+ OOS trades
Focuses on strategies with frequent signals for statistical power.
"""
import numpy as np
import pandas as pd
from pathlib import Path
import json
import os

BASE = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os")
DATA_FILE = BASE / "data" / "EURUSD_D1_clean.csv"
OUTPUT_FILE = BASE / "reports" / "high_freq_scan.json"

COST_RT_BPS = 3.4
TRAIN_SPLIT = 0.80
MIN_TRADES = 20
WARMUP = 200


def load_data():
    df = pd.read_csv(DATA_FILE)
    return (df["Open"].values, df["High"].values, df["Low"].values,
            df["Close"].values, len(df["Close"]))


def sharpe_from_trades(trades):
    if len(trades) < 5:
        return 0, len(trades), 0
    avg = np.mean(trades)
    std = np.std(trades, ddof=1) if len(trades) > 1 else 0
    sharpe = avg / (std + 1e-10) * np.sqrt(252)
    wr = sum(1 for r in trades if r > 0) / len(trades) * 100
    return round(float(sharpe), 4), len(trades), round(wr, 2)


def simulate_always_in(opens, closes, signals, split_idx):
    """Always-in strategy: long or short, flip on signal change."""
    n = len(closes)
    position = 0
    entry_price = 0.0
    trades_is, trades_oos = [], []

    for i in range(WARMUP, n):
        bar_label = "IS" if i < split_idx else "OOS"
        signal = signals[i]

        if position == 0 and signal != 0:
            entry_idx = i + 1 if i + 1 < n else i
            entry_price = opens[entry_idx] if i + 1 < n else closes[i]
            position = signal
        elif position != 0 and signal != position:
            exit_idx = i + 1 if i + 1 < n else i
            exit_price = opens[exit_idx] if i + 1 < n else closes[i]
            raw = ((exit_price - entry_price) / entry_price if position == 1
                   else (entry_price - exit_price) / entry_price)
            net = raw - (COST_RT_BPS / 10000.0)
            (trades_is if bar_label == "IS" else trades_oos).append(net)
            position = 0
            if signal != 0:
                entry_price = exit_price
                entry_idx = exit_idx
                position = signal

    return trades_is, trades_oos


def simulate_entry_exit(opens, closes, signals, split_idx):
    """Entry/exit: position only when signal=1 or -1, flat on 0."""
    n = len(closes)
    position = 0
    entry_price = 0.0
    trades_is, trades_oos = [], []

    for i in range(WARMUP, n):
        bar_label = "IS" if i < split_idx else "OOS"
        signal = signals[i]

        if position == 0 and signal != 0:
            entry_idx = i + 1 if i + 1 < n else i
            entry_price = opens[entry_idx] if i + 1 < n else closes[i]
            position = signal
        elif position != 0 and signal == 0:
            exit_idx = i + 1 if i + 1 < n else i
            exit_price = opens[exit_idx] if i + 1 < n else closes[i]
            raw = ((exit_price - entry_price) / entry_price if position == 1
                   else (entry_price - exit_price) / entry_price)
            net = raw - (COST_RT_BPS / 10000.0)
            (trades_is if bar_label == "IS" else trades_oos).append(net)
            position = 0

    return trades_is, trades_oos


def run_scan():
    print("=" * 70)
    print("  HIGH-FREQ STRATEGY SCANNER — Target 50+ OOS Trades")
    print("  EURUSD D1 | Cost: %.1f bps/RT" % COST_RT_BPS)
    print("=" * 70)

    opens, highs, lows, closes, n = load_data()
    split_idx = int(n * TRAIN_SPLIT)
    print(f"  Data: {n} bars | IS: {split_idx} | OOS: {n - split_idx}\n")

    all_results = []

    # ==============================================================
    # 1. Donchian Small Period (5, 10, 15)
    # ==============================================================
    print("-" * 70)
    print("  1. Donchian Small Period")
    print("-" * 70)

    for period in [3, 5, 8, 10, 15]:
        # Generate signals
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

        trades_is, trades_oos = simulate_always_in(opens, closes, signals, split_idx)
        is_s, is_n, is_wr = sharpe_from_trades(trades_is)
        oos_s, oos_n, oos_wr = sharpe_from_trades(trades_oos)
        wf = oos_s / is_s if is_s > 0.05 else 0

        all_results.append({
            "strategy": "Donchian", "params": f"period={period}",
            "is_sharpe": is_s, "oos_sharpe": oos_s,
            "oos_trades": oos_n, "oos_wr": oos_wr, "wf_pct": round(wf*100, 1),
        })
        print(f"    Donchian({period:2d}): IS={is_s:7.2f} OOS={oos_s:7.2f} "
              f"WR={oos_wr:5.1f}% Trades={oos_n:4d}")

    # ==============================================================
    # 2. Fixed-Interval Momentum (weekly rebalance)
    # ==============================================================
    print("-" * 70)
    print("  2. Fixed-Interval Momentum")
    print("-" * 70)

    for lb in [5, 10, 21, 42, 63]:
        for hold in [5, 10, 21]:
            signals = np.zeros(n, dtype=int)
            pos = 0
            held = 0
            for i in range(max(lb, WARMUP), n):
                if held > 0:
                    held -= 1
                    signals[i] = pos
                    continue
                pos = 1 if closes[i] > closes[i - lb] else -1
                signals[i] = pos
                held = hold - 1

            trades_is, trades_oos = simulate_always_in(opens, closes, signals, split_idx)
            is_s, is_n, is_wr = sharpe_from_trades(trades_is)
            oos_s, oos_n, oos_wr = sharpe_from_trades(trades_oos)
            wf = oos_s / is_s if is_s > 0.05 else 0

            if oos_n >= MIN_TRADES:
                all_results.append({
                    "strategy": "FixIntMomentum", "params": f"lb={lb},hold={hold}",
                    "is_sharpe": is_s, "oos_sharpe": oos_s,
                    "oos_trades": oos_n, "oos_wr": oos_wr, "wf_pct": round(wf*100, 1),
                })
                print(f"    lb={lb:3d},hold={hold:2d}: IS={is_s:7.2f} OOS={oos_s:7.2f} "
                      f"WR={oos_wr:5.1f}% Trades={oos_n:4d}")

    # ==============================================================
    # 3. Mean Reversion z-score (entry/exit)
    # ==============================================================
    print("-" * 70)
    print("  3. Mean Reversion z-score")
    print("-" * 70)

    for window in [5, 10, 20]:
        for threshold in [1.0, 1.5, 2.0]:
            signals = np.zeros(n, dtype=int)
            for i in range(max(window, WARMUP), n):
                w = closes[i - window : i]
                mu = np.mean(w)
                sigma = np.std(w, ddof=1) if len(w) > 1 else 0
                if sigma == 0:
                    continue
                z = (closes[i] - mu) / sigma
                if z < -threshold:
                    signals[i] = 1   # oversold → long
                elif z > threshold:
                    signals[i] = -1  # overbought → short

            trades_is, trades_oos = simulate_entry_exit(opens, closes, signals, split_idx)
            is_s, is_n, is_wr = sharpe_from_trades(trades_is)
            oos_s, oos_n, oos_wr = sharpe_from_trades(trades_oos)
            wf = oos_s / is_s if is_s > 0.05 else 0

            if oos_n >= MIN_TRADES:
                all_results.append({
                    "strategy": "MeanRevZ", "params": f"win={window},z={threshold}",
                    "is_sharpe": is_s, "oos_sharpe": oos_s,
                    "oos_trades": oos_n, "oos_wr": oos_wr, "wf_pct": round(wf*100, 1),
                })
                print(f"    win={window:2d},z={threshold:.1f}: IS={is_s:7.2f} OOS={oos_s:7.2f} "
                      f"WR={oos_wr:5.1f}% Trades={oos_n:4d}")

    # ==============================================================
    # 4. Volatility Breakout (BB squeeze)
    # ==============================================================
    print("-" * 70)
    print("  4. Volatility Breakout (BB squeeze)")
    print("-" * 70)

    for period in [10, 20, 30]:
        for k in [1.5, 2.0, 2.5]:
            signals = np.zeros(n, dtype=int)
            pos = 0
            for i in range(max(period, WARMUP), n):
                w = closes[i - period : i]
                mu = np.mean(w)
                sigma = np.std(w, ddof=1) if len(w) > 1 else 0
                upper = mu + k * sigma
                lower = mu - k * sigma
                if closes[i] > upper:
                    pos = 1
                elif closes[i] < lower:
                    pos = -1
                signals[i] = pos

            trades_is, trades_oos = simulate_always_in(opens, closes, signals, split_idx)
            is_s, is_n, is_wr = sharpe_from_trades(trades_is)
            oos_s, oos_n, oos_wr = sharpe_from_trades(trades_oos)
            wf = oos_s / is_s if is_s > 0.05 else 0

            all_results.append({
                "strategy": "BBreakout", "params": f"p={period},k={k}",
                "is_sharpe": is_s, "oos_sharpe": oos_s,
                "oos_trades": oos_n, "oos_wr": oos_wr, "wf_pct": round(wf*100, 1),
            })
            print(f"    period={period:2d},k={k:.1f}: IS={is_s:7.2f} OOS={oos_s:7.2f} "
                  f"WR={oos_wr:5.1f}% Trades={oos_n:4d}")

    # ==============================================================
    # Ranking
    # ==============================================================
    print()
    print("=" * 70)
    print("  RANKED BY OOS Sharpe (min %d OOS trades)" % MIN_TRADES)
    print("=" * 70)

    valid = [r for r in all_results if r["oos_trades"] >= MIN_TRADES]
    valid.sort(key=lambda x: x["oos_sharpe"], reverse=True)

    print(f"\n{'#':<3} {'Strategy':<18} {'Params':<20} "
          f"{'IS Sharpe':<10} {'OOS Sharpe':<10} {'WR%':<7} {'Trades':<7} {'WF%':<8}")
    print("-" * 85)

    for i, r in enumerate(valid[:25], 1):
        print(f"{i:<3} {r['strategy']:<18} {r['params']:<20} "
              f"{r['is_sharpe']:<10.4f} {r['oos_sharpe']:<10.4f} "
              f"{r['oos_wr']:<6.1f}% {r['oos_trades']:<4d}    {r['wf_pct']:<7.1f}%")

    # Highlight high-trade-count winners
    high_trades = [r for r in valid if r["oos_trades"] >= 50 and r["oos_sharpe"] > 0]
    print(f"\n  High-trade (50+) + OOS Sharpe > 0: {len(high_trades)}")

    os.makedirs(OUTPUT_FILE.parent, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump({"date": pd.Timestamp.now().isoformat(),
                   "total": len(all_results), "valid": len(valid),
                   "top_25": valid[:25],
                   "high_trade_winners": high_trades}, f, indent=2)

    print(f"\n  Saved: {OUTPUT_FILE}")
    print("=" * 70)

    return valid, high_trades


if __name__ == "__main__":
    run_scan()
