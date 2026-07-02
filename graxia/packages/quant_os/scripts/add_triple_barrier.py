#!/usr/bin/env python3
"""
add_triple_barrier.py — Add triple-barrier labels to features_v3
================================================================

Adds tb_label (triple-barrier) to features_v3_mega_XAUUSD_15min.parquet
with configurable TP/SL multipliers.

Usage:
    python scripts/add_triple_barrier.py --tp-mult 2.0 --sl-mult 1.0 --max-bars 12
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
FEAT_PATH = BASE / "artifacts" / "features_v3" / "features_v3_mega_XAUUSD_15min.parquet"
OUT_PATH = BASE / "artifacts" / "features_v3" / "features_v3_mega_XAUUSD_15min.parquet"


def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def compute_triple_barrier(
    close_arr: np.ndarray,
    high_arr: np.ndarray,
    low_arr: np.ndarray,
    atr_arr: np.ndarray,
    tp_mult: float = 2.0,
    sl_mult: float = 1.0,
    max_bars: int = 12,
) -> np.ndarray:
    """
    Compute triple-barrier labels using pure numpy for speed.

    Returns:
        Array of labels: 1 (win), -1 (loss), 0 (timeout)
    """
    n = len(close_arr)
    labels = np.zeros(n, dtype=np.int8)

    tp_hits = 0
    sl_hits = 0
    timeouts = 0
    both_hits = 0

    for i in range(n - max_bars):
        current_close = close_arr[i]
        volatility = atr_arr[i]

        if volatility <= 0 or np.isnan(volatility):
            labels[i] = 0
            timeouts += 1
            continue

        tp_price = current_close + (volatility * tp_mult)
        sl_price = current_close - (volatility * sl_mult)

        outcome = 0  # default = timeout

        for j in range(1, max_bars + 1):
            bar_high = high_arr[i + j]
            bar_low = low_arr[i + j]

            hit_tp = bar_high >= tp_price
            hit_sl = bar_low <= sl_price

            if hit_tp and hit_sl:
                outcome = -1
                both_hits += 1
                break
            elif hit_sl:
                outcome = -1
                sl_hits += 1
                break
            elif hit_tp:
                outcome = 1
                tp_hits += 1
                break

        labels[i] = outcome
        if outcome == 0:
            timeouts += 1

    total_labeled = n - max_bars
    win_rate = tp_hits / max(total_labeled, 1) * 100

    log(f"  Triple-barrier results (k_tp={tp_mult}, k_sl={sl_mult}, max_bars={max_bars}):")
    log(f"    Total bars: {n}")
    log(f"    Labeled: {total_labeled}")
    log(f"    TP hits (wins): {tp_hits} ({win_rate:.1f}%)")
    log(f"    SL hits (losses): {sl_hits} ({sl_hits/max(total_labeled,1)*100:.1f}%)")
    log(f"    Both hits: {both_hits}")
    log(f"    Timeouts: {timeouts} ({timeouts/max(total_labeled,1)*100:.1f}%)")

    return labels


def main():
    parser = argparse.ArgumentParser(description="Add triple-barrier labels to features_v3")
    parser.add_argument("--tp-mult", type=float, default=2.0, help="TP ATR multiplier (default: 2.0)")
    parser.add_argument("--sl-mult", type=float, default=1.0, help="SL ATR multiplier (default: 1.0)")
    parser.add_argument("--max-bars", type=int, default=12, help="Max holding period in bars (default: 12)")
    parser.add_argument("--input", type=str, default=str(FEAT_PATH), help="Input parquet path")
    parser.add_argument("--output", type=str, default=str(OUT_PATH), help="Output parquet path")
    args = parser.parse_args()

    log(f"Loading features from {args.input}...")
    df = pd.read_parquet(args.input)
    log(f"  Shape: {df.shape}")

    # Ensure we have required columns
    required = ["open", "high", "low", "close", "atr_14"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        log(f"  [ERROR] Missing columns: {missing}")
        sys.exit(1)

    # Get datetime index
    if "datetime" in df.columns:
        dt_col = df["datetime"]
    elif "timestamp" in df.columns:
        dt_col = df["timestamp"]
    else:
        dt_col = pd.Series(range(len(df)), index=df.index)

    # Extract arrays
    close_arr = df["close"].values.astype(np.float64)
    high_arr = df["high"].values.astype(np.float64)
    low_arr = df["low"].values.astype(np.float64)
    atr_arr = df["atr_14"].values.astype(np.float64)

    # Convert ATR from return units to price units (multiply by close)
    atr_price = atr_arr * close_arr
    log(f"  ATR in return units: min={atr_arr.min():.6f}, mean={atr_arr.mean():.6f}, max={atr_arr.max():.6f}")
    log(f"  ATR in price units: min={atr_price.min():.2f}, mean={atr_price.mean():.2f}, max={atr_price.max():.2f}")
    log(f"  Bar range (high-low): mean={(high_arr - low_arr).mean():.2f}")

    # Compute triple-barrier labels (using ATR in price units)
    log("Computing triple-barrier labels...")
    tb_labels = compute_triple_barrier(
        close_arr, high_arr, low_arr, atr_price,
        tp_mult=args.tp_mult,
        sl_mult=args.sl_mult,
        max_bars=args.max_bars,
    )

    # Add to dataframe
    df["tb_label"] = tb_labels

    # Also compute tb_win as binary (1 if tp hit first, 0 otherwise)
    df["tb_win"] = (tb_labels == 1).astype(int)

    # Add metadata columns
    df["tb_tp_mult"] = args.tp_mult
    df["tb_sl_mult"] = args.sl_mult
    df["tb_max_bars"] = args.max_bars

    # Drop last max_bars rows (incomplete labels)
    if args.max_bars > 0:
        df = df.iloc[:-args.max_bars]

    # Save
    log(f"Saving to {args.output}...")
    df.to_parquet(args.output, index=False)
    log(f"  Final shape: {df.shape}")

    # Summary
    log("\nLabel distribution:")
    label_counts = df["tb_label"].value_counts().sort_index()
    for label, count in label_counts.items():
        label_name = {1: "WIN", -1: "LOSS", 0: "TIMEOUT"}.get(label, str(label))
        log(f"  {label_name} ({label}): {count} ({count/len(df)*100:.1f}%)")

    log(f"\nWin rate: {(df['tb_label']==1).sum() / len(df) * 100:.1f}%")
    log(f"Loss rate: {(df['tb_label']==-1).sum() / len(df) * 100:.1f}%")
    log(f"Timeout rate: {(df['tb_label']==0).sum() / len(df) * 100:.1f}%")


if __name__ == "__main__":
    main()
