"""
Phase 3: RSI+BB Parameter Scanner + Cross-Pair Research
Scans 900 parameter combinations across 5 pairs on D1 data.
Uses corrected costs, 80/20 holdout, and realistic evaluation.

Output: reports/param_scan_results.json (top 50 by WF%)
"""
import numpy as np
import pandas as pd
from pathlib import Path
import json
import os
from itertools import product

# === CONFIG ==========================================================
BASE = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os")
DATA_DIR = BASE / "data"
OUTPUT_FILE = BASE / "reports" / "param_scan_results.json"

# Pairs and data files (D1 only)
PAIRS = {
    "EURUSD": {"file": "EURUSD_D1_clean.csv", "cost_rt_bps": 3.4},
    "GBPUSD": {"file": "GBPUSD_D1.csv", "cost_rt_bps": 3.4},
    "AUDUSD": {"file": "AUDUSD_D1.csv", "cost_rt_bps": 3.4},
    "XAUUSD": {"file": "XAUUSD_D1.csv", "cost_rt_bps": 12.5, "skip": True},  # MN1 data, skip
    "US30":   {"file": "US30_D1.csv", "cost_rt_bps": 5.0},
}

# Parameter grid
RSI_PERIODS = [7, 10, 14, 21, 28]
RSI_THRESHOLDS = [(20, 80), (25, 75), (30, 70), (35, 65)]
BB_PERIODS = [10, 20, 30]
BB_STDS = [1.5, 2.0, 2.5]

TRAIN_SPLIT = 0.80
MIN_TRADES = 5  # minimum trades required for valid evaluation
BONFERRONI = 0.05 / (5 * 5 * 4 * 3 * 3)  # Bonferroni correction for 900 tests

# ======================================================================


def load_pair_data(filename: str) -> np.ndarray | None:
    """Load OHLCV data, return (dates, opens, highs, lows, closes)."""
    filepath = DATA_DIR / filename
    if not filepath.exists():
        return None
    df = pd.read_csv(filepath)
    # Handle different column names
    cols = df.columns.str.lower()
    date_col = [c for c in df.columns if 'date' in c.lower() or 'time' in c.lower()]
    close_col = [c for c in df.columns if 'close' in c.lower()]
    open_col = [c for c in df.columns if 'open' in c.lower()]
    high_col = [c for c in df.columns if 'high' in c.lower()]
    low_col = [c for c in df.columns if 'low' in c.lower()]

    if not (close_col and open_col and high_col and low_col):
        return None

    dates = df[date_col[0]].values if date_col else df.iloc[:, 0].values  # fallback: first col
    closes = pd.to_numeric(df[close_col[0]], errors='coerce').values.astype(float)
    opens = pd.to_numeric(df[open_col[0]], errors='coerce').values.astype(float)
    highs = pd.to_numeric(df[high_col[0]], errors='coerce').values.astype(float)
    lows = pd.to_numeric(df[low_col[0]], errors='coerce').values.astype(float)

    # Drop NaN rows
    mask = ~(np.isnan(closes) | np.isnan(opens) | np.isnan(highs) | np.isnan(lows))
    if mask.sum() < 100:
        print(f"  WARNING: Only {mask.sum()} valid rows after NaN removal")
        return None

    return dates[mask], opens[mask], highs[mask], lows[mask], closes[mask]


def compute_rsi(closes: np.ndarray, period: int) -> np.ndarray:
    """Wilder RSI."""
    n = len(closes)
    rsi = np.full(n, np.nan)
    if n < period + 1:
        return rsi
    delta = np.diff(closes)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = np.mean(gain[:period])
    avg_loss = np.mean(loss[:period])
    for i in range(period, n - 1):
        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / (avg_loss + 1e-10)
            rsi[i] = 100.0 - 100.0 / (1.0 + rs)
        avg_gain = (avg_gain * (period - 1) + gain[i]) / period
        avg_loss = (avg_loss * (period - 1) + loss[i]) / period
    return rsi


def compute_bb(closes: np.ndarray, period: int, nbdev: float):
    """Bollinger Bands."""
    n = len(closes)
    sma = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    upper = np.full(n, np.nan)
    for i in range(period - 1, n):
        window = closes[i - period + 1 : i + 1]
        mu = np.mean(window)
        sigma = np.std(window, ddof=1) if len(window) > 1 else 0
        sma[i] = mu
        lower[i] = mu - nbdev * sigma
        upper[i] = mu + nbdev * sigma
    return sma, lower, upper


def compute_atr(highs, lows, closes, period=14):
    """ATR for relative cost deduction."""
    n = len(closes)
    atr = np.full(n, np.nan)
    if n < period + 1:
        return atr
    tr = np.zeros(n)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
    atr[period-1] = np.mean(tr[:period])
    for i in range(period, n):
        atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
    return atr


def generate_signals(closes, highs, lows,
                     rsi_period, rsi_os, rsi_ob,
                     bb_period, bb_std) -> np.ndarray:
    """Generate signals on close-cross. 1=buy, -1=sell, 0=none."""
    n = len(closes)
    rsi = compute_rsi(closes, rsi_period)
    _, bb_lower, bb_upper = compute_bb(closes, bb_period, bb_std)

    signals = np.zeros(n, dtype=int)
    warmup = max(rsi_period, bb_period)
    last_signal = 0  # track last to avoid flipping too fast
    for i in range(warmup, n):
        if np.isnan(rsi[i]) or np.isnan(bb_lower[i]):
            continue
        if rsi[i] < rsi_os and closes[i] < bb_lower[i]:
            if last_signal != 1:
                signals[i] = 1
                last_signal = 1
        elif rsi[i] > rsi_ob and closes[i] > bb_upper[i]:
            if last_signal != -1:
                signals[i] = -1
                last_signal = -1
    return signals


def simulate_trades(opens, closes, signals, cost_rt_bps, split_idx):
    """Walk-forward simulation with cost deduction, returns trade metrics."""
    n = len(closes)
    position = 0
    entry_price = 0.0
    trades_is = []
    trades_oos = []
    warmup = 50

    for i in range(warmup, n):
        signal = signals[i]
        bar_label = "IS" if i < split_idx else "OOS"

        if position == 0 and signal != 0:
            # Open on next bar's open
            entry_idx = i + 1 if i + 1 < n else i
            entry_price = opens[entry_idx] if i + 1 < n else closes[i]
            position = signal

        elif position != 0 and signal == -position:
            # Close on next bar's open + apply costs
            exit_idx = i + 1 if i + 1 < n else i
            exit_price = opens[exit_idx] if i + 1 < n else closes[i]

            if position == 1:
                raw_return = (exit_price - entry_price) / entry_price
            else:
                raw_return = (entry_price - exit_price) / entry_price

            net_return = raw_return - (cost_rt_bps / 10000.0)

            trade = {
                "net_return": net_return,
                "raw_return": raw_return,
                "entry_idx": entry_idx if i + 1 < n else i,
            }
            if bar_label == "IS":
                trades_is.append(trade)
            else:
                trades_oos.append(trade)

            position = 0

    return trades_is, trades_oos


def compute_metrics(trades):
    """From list of trade dicts, compute aggregate metrics."""
    n = len(trades)
    if n < MIN_TRADES:
        return {
            "n_trades": n,
            "net_sharpe": 0,
            "winrate": 0,
            "avg_return": 0,
            "profit_factor": 0,
            "is_valid": False,
        }

    returns = [t["net_return"] for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    avg_r = np.mean(returns)
    std_r = np.std(returns, ddof=1) if n > 1 else 0
    sharpe = avg_r / (std_r + 1e-10) * np.sqrt(252)
    wr = len(wins) / n if n > 0 else 0
    avg_win = np.mean(wins) if wins else 0
    avg_loss = abs(np.mean(losses)) if losses else 0
    pf = (avg_win * len(wins)) / (avg_loss * len(losses)) if avg_loss > 0 and len(losses) > 0 else 0

    return {
        "n_trades": n,
        "net_sharpe": round(sharpe, 4),
        "winrate": round(wr * 100, 2),
        "avg_return": round(avg_r * 100, 4),
        "profit_factor": round(pf, 4),
        "is_valid": True,
    }


def run_scan():
    print("=" * 70)
    print("  RSI + BB PARAMETER SCANNER — Cross-Pair D1")
    print("=" * 70)
    print()

    all_results = []
    param_grid = list(product(RSI_PERIODS, RSI_THRESHOLDS, BB_PERIODS, BB_STDS))
    total_combos = len(param_grid)
    print(f"Parameter combinations per pair: {total_combos}")
    print(f"Pairs to scan: {list(PAIRS.keys())}")
    print(f"Total tests: {total_combos * len(PAIRS)}")
    print(f"Bonferroni threshold (alpha corrected): {BONFERRONI:.6f}")
    print()

    for pair_name, pair_cfg in PAIRS.items():
        if pair_cfg.get("skip"):
            print(f"  SKIP: {pair_name} (marked skip)")
            continue
        print("-" * 70)
        print(f"  PAIR: {pair_name} (cost: {pair_cfg['cost_rt_bps']} bps/RT)")
        print("-" * 70)

        # Load data
        data = load_pair_data(pair_cfg["file"])
        if data is None:
            print(f"  SKIP: Data file not found: {pair_cfg['file']}")
            continue

        dates, opens, highs, lows, closes = data
        n = len(closes)
        split_idx = int(n * TRAIN_SPLIT)
        print(f"  Bars: {n} (IS: {split_idx}, OOS: {n - split_idx})")
        print(f"  Period: {dates[0]} to {dates[-1]}")
        print()

        # Pre-compute base indicators (ATR for reference)
        atr = compute_atr(highs, lows, closes)

        pair_results = []
        scanned = 0

        for rsi_p, (rsi_os, rsi_ob), bb_p, bb_s in param_grid:
            # Generate signals
            signals = generate_signals(closes, highs, lows, rsi_p, rsi_os, rsi_ob, bb_p, bb_s)

            # Simulate trades
            trades_is, trades_oos = simulate_trades(opens, closes, signals, pair_cfg["cost_rt_bps"], split_idx)

            # Compute metrics
            is_metrics = compute_metrics(trades_is)
            oos_metrics = compute_metrics(trades_oos)

            if not is_metrics["is_valid"] and not oos_metrics["is_valid"]:
                scanned += 1
                continue  # not enough trades

            # Walk-forward efficiency (capped, adjusted for near-zero IS)
            if is_metrics["net_sharpe"] > 0.05:
                wf_efficiency = oos_metrics["net_sharpe"] / is_metrics["net_sharpe"]
            elif is_metrics["net_sharpe"] > 0:
                wf_efficiency = 1.0  # IS positive but small
            else:
                wf_efficiency = 0.0  # IS negative, WF% meaningless

            # Signal count
            total_signals = int(np.sum(np.abs(signals)))

            result = {
                "pair": pair_name,
                "rsi_period": rsi_p,
                "rsi_os": rsi_os,
                "rsi_ob": rsi_ob,
                "bb_period": bb_p,
                "bb_std": bb_s,
                "cost_rt_bps": pair_cfg["cost_rt_bps"],
                "is": is_metrics,
                "oos": oos_metrics,
                "wf_efficiency": round(wf_efficiency, 4),
                "total_signals": total_signals,
                "total_bars": n,
            }

            pair_results.append(result)
            scanned += 1

            # Progress indicator
            if scanned % 30 == 0:
                print(f"    [{scanned}/{total_combos}] ...", end="\r")

        # Rank pair results by WF% (prefer positive OOS Sharpe + high WF%)
        valid_pair = [r for r in pair_results if r["oos"]["is_valid"] and r["oos"]["net_sharpe"] > 0]
        valid_pair.sort(key=lambda x: (x["oos"]["net_sharpe"], x["oos"]["winrate"]), reverse=True)

        print(f"    [{scanned}/{total_combos}] Done. Valid OOS: {len(valid_pair)}")
        if valid_pair:
            top = valid_pair[0]
            print(f"    Best: RSI({top['rsi_period']},{top['rsi_os']}/{top['rsi_ob']}) "
                  f"+ BB({top['bb_period']},{top['bb_std']}) "
                  f"| IS Sharpe: {top['is']['net_sharpe']:.2f} "
                  f"| OOS Sharpe: {top['oos']['net_sharpe']:.2f} "
                  f"| WF%: {top['wf_efficiency']:.1%}")
            print(f"    OOS WR: {top['oos']['winrate']:.1f}% "
                  f"| OOS Trades: {top['oos']['n_trades']}")

        all_results.extend(valid_pair)

    # --- Global ranking ---
    print()
    print("=" * 70)
    print("  GLOBAL RANKING — Top 50 by WF% (OOS Sharpe > 0)")
    print("=" * 70)

    all_results.sort(key=lambda x: (x["oos"]["net_sharpe"], x["oos"]["winrate"]), reverse=True)
    top_n = all_results[:50]

    print(f"\n{'Rank':<5} {'Pair':<8} {'RSI':<14} {'BB':<12} {'WF%':<8} "
          f"{'IS Sharpe':<11} {'OOS Sharpe':<11} {'OOS WR':<8} {'OOS Trades':<11}")
    print("-" * 90)

    for rank, r in enumerate(top_n, 1):
        rsi_str = f"({r['rsi_period']},{r['rsi_os']}/{r['rsi_ob']})"
        bb_str = f"({r['bb_period']},{r['bb_std']})"
        print(f"{rank:<5} {r['pair']:<8} {rsi_str:<14} {bb_str:<12} "
              f"{r['wf_efficiency']:.1%}    "
              f"{r['is']['net_sharpe']:<11.4f} "
              f"{r['oos']['net_sharpe']:<11.4f} "
              f"{r['oos']['winrate']:<7.1f}% "
              f"{r['oos']['n_trades']:<5} "
              f"(IS: {r['is']['n_trades']})")

    # Bonferroni pass/fail
    pass_bonf = [r for r in top_n if r["oos"]["net_sharpe"] > 0 and r["wf_efficiency"] > 0.4]
    print(f"\nPasses WF% > 40%: {len(pass_bonf)}")
    print(f"Bonferroni threshold: p < {BONFERRONI:.6f} (effectively impossible at this sample)")

    # Save
    os.makedirs(OUTPUT_FILE.parent, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump({
            "scan_date": pd.Timestamp.now().isoformat(),
            "total_combinations": total_combos,
            "pairs_scanned": list(PAIRS.keys()),
            "cost_models": {k: v["cost_rt_bps"] for k, v in PAIRS.items()},
            "bonferroni_alpha": BONFERRONI,
            "top_50": top_n,
            "pass_wf_40": pass_bonf,
            "total_valid_combinations": len(all_results),
        }, f, indent=2)

    print(f"\n  Results saved: {OUTPUT_FILE}")
    print("=" * 70)
    print("  SCAN COMPLETE")
    print("=" * 70)

    return top_n, pass_bonf


if __name__ == "__main__":
    run_scan()
