"""
Label Shuffle Test — Donchian(25) EURUSD D1
Confirms whether OOS Sharpe 3.98 is genuine edge or chance.
Shuffles daily returns → reconstructs prices → re-evaluates strategy.
100 iterations. p-value = fraction of shuffled Sharpes >= real Sharpe.
"""
import numpy as np
import pandas as pd
from pathlib import Path
import json

BASE = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os")
DATA_FILE = BASE / "data" / "EURUSD_D1_clean.csv"
OUTPUT_FILE = BASE / "reports" / "donchian_label_shuffle.json"

COST_RT_BPS = 3.4
TRAIN_SPLIT = 0.80
N_SHUFFLES = 100
PERIOD = 25


def donchian_signals(highs, lows, closes, period):
    """Generate Donchian signals — EXACT replica of unified_strategy_scanner."""
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


def simulate_trades(opens, closes, signals, split_idx):
    """Simulate trades — EXACT replica of unified_strategy_scanner."""
    n = len(closes)
    position = 0
    entry_price = 0.0
    trades = []
    warmup = 200

    for i in range(warmup, n):
        bar_label = "IS" if i < split_idx else "OOS"
        signal = signals[i]

        if position == 0 and signal != 0:
            entry_idx = i + 1 if i + 1 < n else i
            entry_price = opens[entry_idx] if i + 1 < n else closes[i]
            position = signal

        elif position != 0 and signal != position:
            exit_idx = i + 1 if i + 1 < n else i
            exit_price = opens[exit_idx] if i + 1 < n else closes[i]

            if position == 1:
                raw_return = (exit_price - entry_price) / entry_price
            else:
                raw_return = (entry_price - exit_price) / entry_price

            net_return = raw_return - (COST_RT_BPS / 10000.0)
            if bar_label == "OOS":
                trades.append(net_return)

            position = 0
            if signal != 0:
                entry_price = exit_price
                entry_idx = exit_idx
                position = signal

    return trades


def sharpe_from_trades(trades):
    """Annualized Sharpe from trade returns."""
    if len(trades) < 5:
        return 0.0
    avg = np.mean(trades)
    std = np.std(trades, ddof=1) if len(trades) > 1 else 0
    if std == 0:
        return 0.0
    return avg / std * np.sqrt(252)


def run_label_shuffle():
    print("=" * 70)
    print(f"  LABEL SHUFFLE TEST — Donchian({PERIOD}) EURUSD D1")
    print(f"  {N_SHUFFLES} iterations")
    print("=" * 70)

    # Load data
    df = pd.read_csv(DATA_FILE)
    closes = df["Close"].values
    opens = df["Open"].values
    highs = df["High"].values
    lows = df["Low"].values
    n = len(closes)
    split_idx = int(n * TRAIN_SPLIT)

    # === STEP 1: Real performance ===
    print("\nStep 1: Real performance...")
    real_signals = donchian_signals(highs, lows, closes, PERIOD)
    real_trades = simulate_trades(opens, closes, real_signals, split_idx)
    real_sharpe = sharpe_from_trades(real_trades)
    print(f"  Real OOS Sharpe: {real_sharpe:.4f}")
    print(f"  Real OOS trades: {len(real_trades)}")
    print(f"  Real OOS Win Rate: {sum(1 for r in real_trades if r > 0)/max(1,len(real_trades))*100:.1f}%")

    # === STEP 2: Shuffle & re-evaluate ===
    print(f"\nStep 2: {N_SHUFFLES} shuffled iterations...")
    shuffled_sharpes = []
    shuffled_wrs = []
    shuffled_trades_count = []

    # Pre-compute the entire bar indices
    bar_indices = np.arange(n)

    for idx in range(N_SHUFFLES):
        # Shuffle bar indices — preserves OHLC within each bar, destroys serial dependence
        shuffled_idx = bar_indices.copy()
        np.random.shuffle(shuffled_idx)

        shuffled_opens = opens[shuffled_idx]
        shuffled_highs = highs[shuffled_idx]
        shuffled_lows = lows[shuffled_idx]
        shuffled_closes = closes[shuffled_idx]

        # Run strategy
        shuf_signals = donchian_signals(shuffled_highs, shuffled_lows, shuffled_closes, PERIOD)
        trades = simulate_trades(shuffled_opens, shuffled_closes, shuf_signals, split_idx)
        s = sharpe_from_trades(trades)
        wr = sum(1 for r in trades if r > 0) / len(trades) * 100 if len(trades) > 0 else 0

        shuffled_sharpes.append(s)
        shuffled_wrs.append(wr)
        shuffled_trades_count.append(len(trades))

        if (idx + 1) % 50 == 0:
            print(f"    [{idx+1}/{N_SHUFFLES}] mean shuffled Sharpe: {np.mean(shuffled_sharpes):.4f}")

    # === STEP 3: Statistics ===
    shuffled_sharpes = np.array(shuffled_sharpes)
    mean_null = np.mean(shuffled_sharpes)
    std_null = np.std(shuffled_sharpes, ddof=1)

    # p-value: fraction of shuffled Sharpes >= real Sharpe (one-tailed)
    p_value_exceed = np.mean(shuffled_sharpes >= real_sharpe)

    # Two-tailed p-value
    p_value_two_tail = np.mean(np.abs(shuffled_sharpes - mean_null) >= np.abs(real_sharpe - mean_null))

    # Percentile of real Sharpe in null distribution
    percentile = np.mean(shuffled_sharpes < real_sharpe) * 100

    print(f"\n{'='*70}")
    print(f"  LABEL SHUFFLE RESULTS")
    print(f"{'='*70}")
    print(f"  Real OOS Sharpe:      {real_sharpe:.4f}")
    print(f"  Null mean Sharpe:     {mean_null:.4f}")
    print(f"  Null std Sharpe:      {std_null:.4f}")
    print(f"  z-score:              {(real_sharpe - mean_null) / (std_null + 1e-10):.4f}")
    print(f"  p-value (>=):         {p_value_exceed:.6f}")
    print(f"  p-value (two-tailed): {p_value_two_tail:.6f}")
    print(f"  Percentile:           {percentile:.2f}%")
    print(f"  Null 95% CI:          [{np.percentile(shuffled_sharpes, 2.5):.4f}, {np.percentile(shuffled_sharpes, 97.5):.4f}]")
    print(f"  Null 99% CI:          [{np.percentile(shuffled_sharpes, 0.5):.4f}, {np.percentile(shuffled_sharpes, 99.5):.4f}]")

    # Significance
    if p_value_exceed < 0.01:
        sig = "*** p < 0.01 — STRONG evidence of genuine edge"
    elif p_value_exceed < 0.05:
        sig = "** p < 0.05 — Significant edge"
    elif p_value_exceed < 0.10:
        sig = "* p < 0.10 — Suggestive, needs more testing"
    else:
        sig = "NOT significant — likely noise"

    print(f"\n  Verdict: {sig}")

    # Histogram summary
    print(f"\n  Null distribution summary:")
    bins = [-10, -5, -2, -1, 0, 1, 2, 5, 10, 50]
    for i in range(len(bins) - 1):
        count = np.sum((shuffled_sharpes >= bins[i]) & (shuffled_sharpes < bins[i + 1]))
        bar = "#" * int(count / max(1, N_SHUFFLES / 50))
        print(f"    [{bins[i]:>5.0f}, {bins[i+1]:>5.0f}): {count:4d} {bar}")
    count_above = np.sum(shuffled_sharpes >= bins[-1])
    print(f"    [{bins[-1]:>5.0f}, +inf): {count_above:4d} {'#' * int(count_above / max(1, N_SHUFFLES / 50))}")

    print(f"\n    Real Sharpe ({real_sharpe:.2f}) position: {'^' * 5}")

    # Save
    result = {
        "test": "label_shuffle",
        "strategy": f"Donchian({PERIOD})",
        "symbol": "EURUSD",
        "timeframe": "D1",
        "n_shuffles": N_SHUFFLES,
        "real_oos_sharpe": round(float(real_sharpe), 4),
        "real_oos_trades": len(real_trades),
        "null_mean_sharpe": round(float(mean_null), 4),
        "null_std_sharpe": round(float(std_null), 4),
        "z_score": round(float((real_sharpe - mean_null) / std_null if std_null > 0 else 0), 4),
        "p_value_one_tailed": round(float(p_value_exceed), 6),
        "p_value_two_tailed": round(float(p_value_two_tail), 6),
        "percentile": round(float(percentile), 2),
        "null_95_ci": [round(float(np.percentile(shuffled_sharpes, 2.5)), 4),
                       round(float(np.percentile(shuffled_sharpes, 97.5)), 4)],
        "null_99_ci": [round(float(np.percentile(shuffled_sharpes, 0.5)), 4),
                       round(float(np.percentile(shuffled_sharpes, 99.5)), 4)],
        "verdict": sig,
        "shuffled_sharpes": [round(float(s), 4) for s in shuffled_sharpes.tolist()],
    }

    import os, json
    os.makedirs(OUTPUT_FILE.parent, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n  Saved: {OUTPUT_FILE}")
    print(f"{'='*70}")
    print("  LABEL SHUFFLE COMPLETE")
    print(f"{'='*70}")

    return result


if __name__ == "__main__":
    run_label_shuffle()
