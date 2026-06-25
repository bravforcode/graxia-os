"""
SYNTHETIC FILL SIMULATOR — Generate slippage training samples from tick data.

Walks through historical tick data, simulates "what if" market orders at each
decision point (every M1/M5 bar close), and computes actual fill price by
advancing through tick stream by assumed latency.

Generates thousands of training samples instantly from existing data.
No waiting for live orders needed.

Usage:
    python scripts/simulate_fills.py [--symbol XAUUSD] [--freq 1min] [--output artifacts/fill_samples]
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from glob import glob

import numpy as np
import pandas as pd


def load_ticks(tick_dir: str, symbol: str) -> pd.DataFrame:
    """Load tick data for a symbol. Tries CSV then Parquet."""
    paths = []
    for ext in ['.parquet', '.csv']:
        suffix = f"_bulk{ext}" if ext == '.csv' else f"_ticks_*{ext}"
        found = glob(os.path.join(tick_dir, f"{symbol}{suffix}"))
        paths.extend(found)
        if paths:
            break

    if not paths:
        raise FileNotFoundError(f"No tick files for {symbol} in {tick_dir}")

    dfs = []
    for p in paths:
        if p.endswith('.parquet'):
            df = pd.read_parquet(p)
        else:
            df = pd.read_csv(p)

        # Unify timestamp column
        for col in ['timestamp_utc', 'timestamp', 'time']:
            if col in df.columns:
                if col in ('timestamp_utc', 'timestamp'):
                    df['timestamp'] = pd.to_datetime(df[col], utc=True)
                elif col == 'time':
                    df['timestamp'] = pd.to_datetime(df['time'], unit='s', utc=True)
                break
        dfs.append(df)

    combined = pd.concat(dfs).sort_values('timestamp')
    # Normalize columns
    if 'bid' not in combined.columns and 'ask' in combined.columns:
        combined['bid'] = combined['ask']  # Fallback
    combined = combined.dropna(subset=['bid', 'ask', 'timestamp'])
    return combined.reset_index(drop=True)


def compute_volatility_regime(ticks: pd.DataFrame, window: int = 100) -> np.ndarray:
    """Compute rolling ATR-like volatility from tick mid-price."""
    mid = (ticks['bid'] + ticks['ask']) / 2
    ret = abs(mid.diff())
    roll = ret.rolling(window, min_periods=10).mean()
    # Bucket into low/med/high
    q33, q66 = roll.quantile(0.33), roll.quantile(0.66)
    regime = np.where(roll <= q33, "low", np.where(roll <= q66, "med", "high"))
    return regime


def compute_spread_bucket(ticks: pd.DataFrame) -> np.ndarray:
    """Bucket spread into tight/medium/wide."""
    spread = ticks['ask'] - ticks['bid']
    q33, q66 = spread.quantile(0.33), spread.quantile(0.66)
    bucket = np.where(spread <= q33, "tight", np.where(spread <= q66, "med", "wide"))
    return bucket


def compute_session_label(timestamps: pd.Series) -> np.ndarray:
    """Label each tick with trading session."""
    hours = pd.Series(timestamps).dt.hour
    labels = np.full(len(hours), "asian", dtype=object)
    # London: 07:00-17:00 UTC
    labels[(hours >= 7) & (hours < 17)] = "london"
    # NY: 12:00-22:00 UTC
    labels[(hours >= 12) & (hours < 22)] = "ny"
    # Overlap: 12:00-17:00 UTC
    labels[(hours >= 12) & (hours < 17)] = "overlap"
    return labels


def simulate_fills(
    ticks: pd.DataFrame,
    decision_idxs: np.ndarray,
    latencies_ms: list[float],
    sides: list[str],
) -> list[dict]:
    """
    Simulate fills at given decision points.
    For each decision_idx, walk forward through tick stream until
    time advanced by latency_ms, then record fill price.
    """
    samples = []
    tick_times = ticks['timestamp'].values.astype('datetime64[ms]').astype('int64')

    for idx in decision_idxs:
        decision_tick = ticks.iloc[idx]
        decision_time = tick_times[idx]
        mid = decision_tick['bid'] + decision_tick['ask'] / 2
        spread_price = decision_tick['ask'] - decision_tick['bid']
        spread_pts = spread_price / 0.00001  # point value (forex)

        # Context features
        session = decision_tick['session_label']
        vol_regime = decision_tick['vol_regime']
        spread_bucket = decision_tick['spread_bucket']

        for side in sides:
            decision_price_fast = decision_tick['ask'] if side == 'buy' else decision_tick['bid']
            for lat_ms in latencies_ms:
                target_time = decision_time + lat_ms  # both in ms
                # Binary search through remaining ticks
                remaining = tick_times[idx:]
                # Find first tick where time >= target_time
                fill_idx = np.searchsorted(remaining, target_time)
                if fill_idx >= len(remaining):
                    continue  # Not enough ticks to simulate
                fill_tick = ticks.iloc[idx + fill_idx]
                fill_price = fill_tick['ask'] if side == 'buy' else fill_tick['bid']

                # Compute slippage in points
                point_val = 0.01 if 'XAU' in str(ticks.attrs.get('symbol', '')) else 0.00001
                slippage_pts = (fill_price - decision_price_fast) / point_val if side == 'buy' else \
                               (decision_price_fast - fill_price) / point_val

                # Time since previous tick (proxy for liquidity density)
                prev_tick_time = tick_times[idx - 1] if idx > 0 else decision_time
                ms_since_last_tick = (decision_time - prev_tick_time) / 1e6

                samples.append({
                    "symbol": ticks.attrs.get('symbol', 'UNKNOWN'),
                    "decision_time": decision_tick['timestamp'].isoformat(),
                    "side": side,
                    "latency_ms": lat_ms,
                    "decision_price": round(decision_price_fast, 5),
                    "fill_price": round(fill_price, 5),
                    "slippage_points": round(slippage_pts, 2),
                    "spread_price": round(spread_price, 5),
                    "spread_bucket": spread_bucket,
                    "vol_regime": vol_regime,
                    "session": session,
                    "ms_since_last_tick": round(ms_since_last_tick, 1),
                })

    return samples


def main():
    parser = argparse.ArgumentParser(description="Synthetic fill simulator")
    parser.add_argument("--symbol", type=str, default="XAUUSD",
                        help="Symbol to simulate fills for")
    parser.add_argument("--tick-dir", type=str,
                        default=os.path.join("artifacts", "mega_data", "ticks"),
                        help="Directory with tick data")
    parser.add_argument("--freq", type=str, default="1min",
                        help="Decision frequency (bar close interval)")
    parser.add_argument("--latencies", type=str, default="50,150,300,500",
                        help="Comma-separated latency assumptions in ms")
    parser.add_argument("--sides", type=str, default="buy,sell",
                        help="Order sides to simulate")
    parser.add_argument("--output", type=str,
                        default=os.path.join("artifacts", "fill_samples"),
                        help="Output directory")
    args = parser.parse_args()

    latencies_ms = [int(x) for x in args.latencies.split(",")]
    sides = args.sides.split(",")
    os.makedirs(args.output, exist_ok=True)

    print(f"{'='*60}")
    print("SYNTHETIC FILL SIMULATOR")
    print(f"  Symbol: {args.symbol}")
    print(f"  Decision freq: {args.freq}")
    print(f"  Latencies: {latencies_ms} ms")
    print(f"  Sides: {sides}")
    print(f"{'='*60}")

    # Load ticks
    print("\n--- Loading ticks ---")
    ticks = load_ticks(args.tick_dir, args.symbol)
    ticks.attrs['symbol'] = args.symbol
    print(f"  Loaded {len(ticks)} ticks")

    # Compute features
    print("\n--- Computing features ---")
    ticks['vol_regime'] = compute_volatility_regime(ticks)
    ticks['spread_bucket'] = compute_spread_bucket(ticks)
    ticks['session_label'] = compute_session_label(ticks['timestamp'])
    print(f"  Vol regimes: {dict(ticks['vol_regime'].value_counts())}")
    print(f"  Spread buckets: {dict(ticks['spread_bucket'].value_counts())}")
    print(f"  Sessions: {dict(ticks['session_label'].value_counts())}")

    # Determine decision points (every M1 bar)
    print(f"\n--- Simulating fills at {args.freq} intervals ---")
    freq_seconds = {'1min': 60, '5min': 300, '15min': 900}.get(args.freq, 60)
    tick_interval_ns = freq_seconds * 1e9
    tick_times_ns = ticks['timestamp'].values.astype('datetime64[ns]').astype('int64')
    start_time = tick_times_ns[0]
    end_time = tick_times_ns[-1]

    # Generate decision times at bar boundaries
    decision_times_ns = np.arange(start_time, end_time, int(tick_interval_ns))
    # Snap each decision time to nearest tick
    decision_idxs = [np.searchsorted(tick_times_ns, t) for t in decision_times_ns]
    decision_idxs = [i for i in decision_idxs if 0 < i < len(ticks) - 500]  # Need enough ticks ahead

    print(f"  Decision points: {len(decision_idxs)}")
    print(f"  Generating ~{len(decision_idxs) * len(sides) * len(latencies_ms)} samples...")

    # Simulate fills
    samples = simulate_fills(ticks, decision_idxs, latencies_ms, sides)
    print(f"  Generated {len(samples)} samples")

    # Save
    df = pd.DataFrame(samples)
    csv_path = os.path.join(args.output, f"fill_samples_{args.symbol}_{args.freq}.csv")
    df.to_csv(csv_path, index=False)
    print(f"\n  Saved: {csv_path}")

    # Distributional stats
    print(f"\n--- Slippage distribution by latency ---")
    for lat in latencies_ms:
        subset = df[df['latency_ms'] == lat]
        if len(subset) > 0:
            sl = subset['slippage_points']
            print(f"  {lat}ms: n={len(sl)}, P50={sl.quantile(0.5):.2f}, P90={sl.quantile(0.9):.2f}, "
                  f"P99={sl.quantile(0.99):.2f}, mean={sl.mean():.2f}, std={sl.std():.2f}")

    print(f"\n--- Slippage P90 by condition bucket ---")
    for bucket_col in ['session', 'vol_regime', 'spread_bucket']:
        print(f"  {bucket_col}:")
        for bucket in sorted(df[bucket_col].unique()):
            sl = df[df[bucket_col] == bucket]['slippage_points']
            if len(sl) > 0:
                print(f"    {bucket}: n={len(sl)}, P50={sl.quantile(0.5):.2f}, "
                      f"P90={sl.quantile(0.9):.2f}, P99={sl.quantile(0.99):.2f}")

    # Summary
    summary = {
        "symbol": args.symbol,
        "freq": args.freq,
        "latencies": latencies_ms,
        "total_ticks": len(ticks),
        "decision_points": len(decision_idxs),
        "total_samples": len(samples),
        "output": csv_path,
    }
    with open(os.path.join(args.output, f"fill_summary_{args.symbol}.json"), 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*60}")
    print("FILL SIMULATION COMPLETE")
    print(f"  {len(samples)} samples from {len(decision_idxs)} decision points")
    print(f"  Output: {csv_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
