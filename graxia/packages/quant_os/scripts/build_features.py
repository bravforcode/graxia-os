"""
FEATURE ENGINEERING — Build ML training features from tick data.

Reads tick CSVs, resamples to OHLCV candles, computes technical indicators,
and outputs a feature matrix ready for strategy model training.

Usage:
    python scripts/build_features.py [--symbols XAUUSD,EURUSD,GBPUSD] [--freqs 1min,5min,15min]
"""
import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from glob import glob

import numpy as np
import pandas as pd

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "features")


def load_ticks(tick_dir: str, symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Load tick CSVs into DataFrames. Returns {symbol: DataFrame}."""
    result = {}
    for sym in symbols:
        paths = glob(os.path.join(tick_dir, f"{sym}_bulk.csv")) + \
                glob(os.path.join(tick_dir, f"{sym}_ticks_*.csv"))
        if not paths:
            print(f"  [SKIP] {sym}: no tick files found")
            continue
        dfs = []
        for p in paths:
            df = pd.read_csv(p)
            if 'time' in df.columns:
                df['timestamp'] = pd.to_datetime(df['time'], unit='s', utc=True)
            elif 'timestamp_utc' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp_utc'], utc=True)
            else:
                continue
            df = df.sort_values('timestamp').drop_duplicates(subset='timestamp')
            dfs.append(df)
        if dfs:
            combined = pd.concat(dfs).sort_values('timestamp').drop_duplicates(subset='timestamp')
            result[sym] = combined
            print(f"  [OK] {sym}: {len(combined)} ticks loaded")
    return result


def resample_ohlcv(ticks: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Resample tick data to OHLCV candles at given frequency."""
    if ticks.empty or 'timestamp' not in ticks.columns:
        return pd.DataFrame()

    df = ticks.set_index('timestamp')

    ohlc = df.resample(freq).agg({
        'ask': 'last' if 'ask' in df.columns else 'last',
        'bid': 'last' if 'bid' in df.columns else 'last',
    })

    # Build OHLC from bid price
    if 'bid' in df.columns:
        bid_ohlc = df['bid'].resample(freq).ohlc()
        bid_ohlc.columns = ['open', 'high', 'low', 'close']
    elif 'last' in df.columns:
        bid_ohlc = df['last'].resample(freq).ohlc()
        bid_ohlc.columns = ['open', 'high', 'low', 'close']
    else:
        bid_ohlc = df['ask'].resample(freq).ohlc()
        bid_ohlc.columns = ['open', 'high', 'low', 'close']

    # Volume
    volume = df['volume'].resample(freq).sum() if 'volume' in df.columns else pd.Series(0, index=bid_ohlc.index)
    tick_count = df['bid'].resample(freq).count() if 'bid' in df.columns else df['ask'].resample(freq).count()

    # Spread
    if 'ask' in df.columns and 'bid' in df.columns:
        spread = (df['ask'] - df['bid']).resample(freq).mean()
    else:
        spread = pd.Series(0.0, index=bid_ohlc.index)

    result = pd.concat([bid_ohlc, volume.rename('volume'), tick_count.rename('tick_count'),
                        spread.rename('spread_mean')], axis=1)
    return result.dropna()


def compute_features(ohlc: pd.DataFrame) -> pd.DataFrame:
    """Compute technical indicators from OHLCV data."""
    if ohlc.empty:
        return ohlc

    df = ohlc.copy()

    # Returns
    df['return_1'] = df['close'].pct_change(1)
    df['return_5'] = df['close'].pct_change(5)
    df['return_15'] = df['close'].pct_change(15)
    df['log_return'] = np.log(df['close'] / df['close'].shift(1))

    # Price position
    df['high_minus_low'] = df['high'] - df['low']
    df['close_position'] = (df['close'] - df['low']) / (df['high'] - df['low'] + 1e-10)

    # Volatility (rolling std of returns)
    df['volatility_5'] = df['return_1'].rolling(5).std()
    df['volatility_15'] = df['return_1'].rolling(15).std()

    # ATR (Average True Range)
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1))
        )
    )
    df['atr_5'] = df['tr'].rolling(5).mean()
    df['atr_15'] = df['tr'].rolling(15).mean()

    # RSI (14-period)
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    df['rsi_14'] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # Bollinger Bands
    df['bb_mid'] = df['close'].rolling(20).mean()
    df['bb_std'] = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_mid'] + 2 * df['bb_std']
    df['bb_lower'] = df['bb_mid'] - 2 * df['bb_std']
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid']
    df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 1e-10)

    # Moving averages
    df['sma_5'] = df['close'].rolling(5).mean()
    df['sma_20'] = df['close'].rolling(20).mean()
    df['sma_ratio'] = df['sma_5'] / df['sma_20']

    # Target: next-period direction (1 = up, 0 = down)
    df['target'] = (df['close'].shift(-1) > df['close']).astype(int)

    # Target: continuous return (for regression)
    df['target_return'] = df['return_1'].shift(-1)

    return df.dropna()


def main():
    parser = argparse.ArgumentParser(description="Feature engineering from tick data")
    parser.add_argument("--symbols", type=str, default="XAUUSD,EURUSD,GBPUSD",
                        help="Comma-separated symbols")
    parser.add_argument("--freqs", type=str, default="1min,5min,15min",
                        help="Comma-separated resample frequencies")
    parser.add_argument("--tick-dir", type=str,
                        default=os.path.join("artifacts", "tick_data"),
                        help="Directory with tick CSVs")
    parser.add_argument("--output", type=str, default=OUTPUT_DIR,
                        help="Output directory for feature files")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]
    freqs = [f.strip() for f in args.freqs.split(",")]
    os.makedirs(args.output, exist_ok=True)

    print(f"{'='*60}")
    print("FEATURE ENGINEERING PIPELINE")
    print(f"  Symbols: {symbols}")
    print(f"  Frequencies: {freqs}")
    print(f"  Tick dir: {args.tick_dir}")
    print(f"{'='*60}")

    # Phase 1: Load ticks
    print("\n--- Loading ticks ---")
    ticks = load_ticks(args.tick_dir, symbols)
    if not ticks:
        print("No tick data loaded. Aborting.")
        return

    # Phase 2: Resample + feature engineering
    all_features = {}
    for sym, df in ticks.items():
        print(f"\n--- Processing {sym} ---")
        for freq in freqs:
            ohlc = resample_ohlcv(df, freq)
            if ohlc.empty:
                print(f"  [SKIP] {freq}: no OHLCV data")
                continue
            features = compute_features(ohlc)
            features['symbol'] = sym
            features['freq'] = freq
            all_features[f"{sym}_{freq}"] = features
            print(f"  [OK] {freq}: {len(features)} rows, {len(features.columns)} cols")

    # Phase 3: Save
    print("\n--- Saving features ---")
    feature_files = []
    for key, df in all_features.items():
        path = os.path.join(args.output, f"features_{key}.parquet")
        df.to_parquet(path)
        feature_files.append(path)
        print(f"  [OK] {key}: {path}")

    # Summary
    print(f"\n{'='*60}")
    print("FEATURE ENGINEERING COMPLETE")
    for key, df in all_features.items():
        cols = [c for c in df.columns if c not in ('symbol', 'freq', 'target', 'target_return')]
        print(f"  {key}: {len(df)} rows, {len(cols)} features + target")
    print(f"  Output: {args.output}")
    print(f"{'='*60}")

    # Save run record
    record = {
        "run_time_utc": datetime.now(timezone.utc).isoformat(),
        "symbols": symbols,
        "frequencies": freqs,
        "features_per_dataset": {k: len(v.columns) - 4 for k, v in all_features.items()},
        "total_rows": sum(len(v) for v in all_features.values()),
        "output_files": feature_files,
    }
    with open(os.path.join(args.output, "feature_run_record.json"), 'w') as f:
        json.dump(record, f, indent=2)


if __name__ == "__main__":
    main()
