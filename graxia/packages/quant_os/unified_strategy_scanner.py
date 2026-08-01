"""
Unified Strategy Scanner: TSMOM + Donchian + MA Crossover
Tests 3 proven quant strategies on EURUSD D1 with corrected costs.
Output: reports/unified_strategy_scan.json
"""
import numpy as np
import pandas as pd
from pathlib import Path
import json
import os
from itertools import product

BASE = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os")
DATA_FILE = BASE / "data" / "EURUSD_D1_clean.csv"
OUTPUT_FILE = BASE / "reports" / "unified_strategy_scan.json"

# Cost model
COST_RT_BPS = 3.4  # EURUSD round trip

# Split
TRAIN_SPLIT = 0.80
MIN_TRADES = 8


# ======================================================================
# Strategy 1: Time Series Momentum (TSMOM)
# ======================================================================
def tsmom_signals(closes, lookback: int, hold: int = 21):
    """
    Moskowitz, Ooi, Pedersen (2012) time series momentum.
    If close[i] > close[i-lookback] → long, else short.
    Hold for `hold` bars before re-evaluating.
    Uses volatility scaling (position size inversely proportional to recent vol).
    """
    n = len(closes)
    signals = np.zeros(n, dtype=int)
    position = 0
    bars_held = 0

    for i in range(lookback, n):
        if bars_held > 0:
            bars_held -= 1
            signals[i] = position
            continue

        # Re-evaluate
        if closes[i] > closes[i - lookback]:
            position = 1  # long
        else:
            position = -1  # short

        signals[i] = position
        bars_held = hold - 1

    return signals


# ======================================================================
# Strategy 2: Donchian Channel Breakout
# ======================================================================
def donchian_signals(highs, lows, closes, period: int = 55):
    """
    Turtle-style Donchian channel breakout.
    Long when close > highest high of `period` days.
    Short when close < lowest low of `period` days.
    Stay in position until opposite signal.
    """
    n = len(closes)
    signals = np.zeros(n, dtype=int)
    position = 0
    entry_price = 0.0
    highest_entry = 0.0
    lowest_entry = 0.0

    for i in range(period, n):
        hh = np.max(highs[i - period : i])
        ll = np.min(lows[i - period : i])

        if position == 0:
            if closes[i] > hh:
                position = 1
                entry_price = closes[i]
            elif closes[i] < ll:
                position = -1
                entry_price = closes[i]
        elif position == 1:
            # Exit on opposite breakout or trailing stop exit
            if closes[i] < ll:
                position = -1
                entry_price = closes[i]
            # Simple trailing stop: exit if drops 2*ATR from peak
        elif position == -1:
            if closes[i] > hh:
                position = 1
                entry_price = closes[i]

        signals[i] = position

    return signals


# ======================================================================
# Strategy 3: Dual Moving Average Crossover
# ======================================================================
def ma_cross_signals(closes, fast: int = 50, slow: int = 200):
    """
    Classic dual moving average crossover.
    Fast MA > Slow MA → long. Fast MA < Slow MA → short.
    Always in market, crossover triggers switch.
    """
    n = len(closes)
    signals = np.zeros(n, dtype=int)
    fast_ma = np.full(n, np.nan)
    slow_ma = np.full(n, np.nan)
    position = 0

    for i in range(slow, n):
        fast_ma[i] = np.mean(closes[i - fast + 1 : i + 1])
        slow_ma[i] = np.mean(closes[i - slow + 1 : i + 1])

        if np.isnan(fast_ma[i]) or np.isnan(slow_ma[i]):
            continue

        if fast_ma[i] > slow_ma[i]:
            if position != 1:
                position = 1
        else:
            if position != -1:
                position = -1

        signals[i] = position

    return signals


# ======================================================================
# Trade Simulator
# ======================================================================
def simulate_trades(opens, closes, signals, split_idx):
    """
    Walk-forward simulator. Returns trades as list of dicts.
    Each trade: {net_return, bar_label, entry_idx}
    Applies cost on entry AND exit.
    """
    n = len(closes)
    position = 0
    entry_price = 0.0
    entry_idx = 0
    trades = []
    warmup = 200  # skip initial warmup for indicators

    for i in range(warmup, n):
        bar_label = "IS" if i < split_idx else "OOS"
        signal = signals[i]

        if position == 0 and signal != 0:
            # Open on next bar's open
            entry_idx = i + 1 if i + 1 < n else i
            entry_price = opens[entry_idx] if i + 1 < n else closes[i]
            position = signal

        elif position != 0 and signal != position:
            # Close position (signal flipped or went to 0)
            exit_idx = i + 1 if i + 1 < n else i
            exit_price = opens[exit_idx] if i + 1 < n else closes[i]

            # Raw return
            if position == 1:
                raw_return = (exit_price - entry_price) / entry_price
            else:
                raw_return = (entry_price - exit_price) / entry_price

            # Apply cost (both entry and exit)
            net_return = raw_return - (COST_RT_BPS / 10000.0)

            trades.append({
                "net_return": net_return,
                "raw_return": raw_return,
                "bar_label": bar_label,
                "entry_idx": entry_idx,
                "exit_idx": exit_idx,
                "duration": i - entry_idx + 1,
                "direction": "LONG" if position == 1 else "SHORT",
            })

            # Open new position if signal flipped
            if signal != 0:
                entry_idx = exit_idx
                entry_price = exit_price  # exit at same price as entry for next
                position = signal
            else:
                position = 0

    return trades


def compute_metrics(trades, label_filter=None):
    """Compute strategy metrics from trade list."""
    if label_filter:
        t = [x for x in trades if x["bar_label"] == label_filter]
    else:
        t = trades

    n = len(t)
    if n < MIN_TRADES:
        return {"n_trades": n, "net_sharpe": 0, "winrate": 0,
                "profit_factor": 0, "avg_return": 0, "max_dd": 0, "is_valid": False}

    returns = [x["net_return"] for x in t]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    avg_r = np.mean(returns)
    std_r = np.std(returns, ddof=1) if n > 1 else 0
    sharpe = avg_r / (std_r + 1e-10) * np.sqrt(252)  # annualized

    wr = len(wins) / n * 100
    avg_win = np.mean(wins) if wins else 0
    avg_loss = abs(np.mean(losses)) if losses else 0
    pf = (len(wins) * avg_win) / (len(losses) * avg_loss) if avg_loss > 0 and len(losses) > 0 else 0

    # Max DD from cumulative returns
    cum = np.cumprod([1 + r for r in returns])
    peak = np.maximum.accumulate(cum)
    dd = (peak - cum) / peak
    max_dd = np.max(dd) * 100

    return {
        "n_trades": n,
        "net_sharpe": round(sharpe, 4),
        "winrate": round(wr, 2),
        "avg_return": round(avg_r * 100, 4),
        "profit_factor": round(pf, 4),
        "max_dd_pct": round(max_dd, 2),
        "is_valid": True,
    }


def run_scan():
    print("=" * 70)
    print("  UNIFIED STRATEGY SCANNER — TSMOM + Donchian + MA Cross")
    print("  EURUSD D1 | Cost: %.1f bps/RT" % COST_RT_BPS)
    print("=" * 70)
    print()

    # Load data
    df = pd.read_csv(DATA_FILE)
    closes = df["Close"].values
    opens = df["Open"].values
    highs = df["High"].values
    lows = df["Low"].values
    n = len(closes)
    split_idx = int(n * TRAIN_SPLIT)
    print(f"Data: {n} bars | IS: {split_idx} | OOS: {n - split_idx}")
    print()

    all_results = []

    # ================================================================
    # Strategy 1: Time Series Momentum
    # ================================================================
    print("-" * 70)
    print("  STRATEGY 1: Time Series Momentum (TSMOM)")
    print("-" * 70)

    tsmom_params = list(product(
        [63, 126, 252],     # lookback: 3mo, 6mo, 12mo
        [21, 42, 63],       # hold period: 1mo, 2mo, 3mo
    ))

    for lb, hold in tsmom_params:
        signals = tsmom_signals(closes, lb, hold)
        trades = simulate_trades(opens, closes, signals, split_idx)
        is_m = compute_metrics(trades, "IS")
        oos_m = compute_metrics(trades, "OOS")

        wf = oos_m["net_sharpe"] / is_m["net_sharpe"] if is_m["net_sharpe"] > 0.05 else 0

        all_results.append({
            "strategy": "TSMOM",
            "params": f"lb={lb},hold={hold}",
            "lookback": lb,
            "hold": hold,
            "is": is_m,
            "oos": oos_m,
            "wf_pct": round(wf * 100, 1),
        })

    print(f"  Combinations: {len(tsmom_params)}")

    # ================================================================
    # Strategy 2: Donchian Channel Breakout
    # ================================================================
    print("-" * 70)
    print("  STRATEGY 2: Donchian Channel Breakout")
    print("-" * 70)

    donchian_params = [20, 55, 200]

    for period in donchian_params:
        signals = donchian_signals(highs, lows, closes, period)
        trades = simulate_trades(opens, closes, signals, split_idx)
        is_m = compute_metrics(trades, "IS")
        oos_m = compute_metrics(trades, "OOS")

        wf = oos_m["net_sharpe"] / is_m["net_sharpe"] if is_m["net_sharpe"] > 0.05 else 0

        all_results.append({
            "strategy": "Donchian",
            "params": f"period={period}",
            "period": period,
            "is": is_m,
            "oos": oos_m,
            "wf_pct": round(wf * 100, 1),
        })

    print(f"  Combinations: {len(donchian_params)}")

    # ================================================================
    # Strategy 3: Dual MA Crossover
    # ================================================================
    print("-" * 70)
    print("  STRATEGY 3: Dual Moving Average Crossover")
    print("-" * 70)

    ma_params = [
        (20, 50),
        (20, 100),
        (50, 200),
        (10, 30),
        (10, 50),
    ]

    for fast, slow in ma_params:
        signals = ma_cross_signals(closes, fast, slow)
        trades = simulate_trades(opens, closes, signals, split_idx)
        is_m = compute_metrics(trades, "IS")
        oos_m = compute_metrics(trades, "OOS")

        wf = oos_m["net_sharpe"] / is_m["net_sharpe"] if is_m["net_sharpe"] > 0.05 else 0

        all_results.append({
            "strategy": "MA_Crossover",
            "params": f"fast={fast},slow={slow}",
            "fast": fast,
            "slow": slow,
            "is": is_m,
            "oos": oos_m,
            "wf_pct": round(wf * 100, 1),
        })

    print(f"  Combinations: {len(ma_params)}")

    # ================================================================
    # Ranking
    # ================================================================
    print()
    print("=" * 70)
    print("  FINAL RANKING — All Strategies")
    print("=" * 70)

    # Filter: need valid OOS
    valid = [r for r in all_results if r["oos"]["is_valid"]]
    # Sort by OOS Sharpe (primary), then profit factor
    valid.sort(key=lambda x: (x["oos"]["net_sharpe"], x["oos"]["profit_factor"]), reverse=True)

    print(f"\n{'#':<3} {'Strategy':<14} {'Params':<22} {'IS Sharpe':<11} {'OOS Sharpe':<11} {'OOS WR':<8} {'OOS Trades':<11} {'WF%':<8} {'Max DD%':<8}")
    print("-" * 100)

    for i, r in enumerate(valid[:20], 1):
        print(f"{i:<3} {r['strategy']:<14} {r['params']:<22} "
              f"{r['is']['net_sharpe']:<11.4f} {r['oos']['net_sharpe']:<11.4f} "
              f"{r['oos']['winrate']:<7.1f}% {r['oos']['n_trades']:<5}      "
              f"{r['wf_pct']:<7.1f}% {r['oos']['max_dd_pct']:<7.1f}%")

    # Pass criteria
    passes = [r for r in valid if r["oos"]["net_sharpe"] > 0 and r["wf_pct"] > 40]
    print(f"\nPass WF% > 40% + OOS Sharpe > 0: {len(passes)}")

    if passes:
        print("\n=== PASSING STRATEGIES ===")
        for r in passes:
            print(f"  {r['strategy']} {r['params']}: "
                  f"IS={r['is']['net_sharpe']:.2f} OOS={r['oos']['net_sharpe']:.2f} "
                  f"WR={r['oos']['winrate']:.1f}% Trades={r['oos']['n_trades']}")

    # Save
    os.makedirs(OUTPUT_FILE.parent, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump({
            "scan_date": pd.Timestamp.now().isoformat(),
            "cost_rt_bps": COST_RT_BPS,
            "total_combinations": len(all_results),
            "valid_combinations": len(valid),
            "passing": len(passes),
            "top_20": valid[:20],
            "all_results": all_results,
        }, f, indent=2)

    print(f"\nSaved: {OUTPUT_FILE}")
    print("=" * 70)

    return valid, passes


if __name__ == "__main__":
    run_scan()
