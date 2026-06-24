"""
ADVANCED FEATURES -- Order-flow proxy, volume profile, multi-TF confluence.

Reads tick data + existing feature files, adds NEW feature sources that the
diagnostic found missing (price-only features = HIGH BIAS, r~0.06).

New feature families:
  1. Order-flow proxy   -- tick imbalance, direction ratio, micro-price bias
  2. Volume profile     -- tick concentration, volume-at-price, velocity
  3. Multi-TF confluence -- trend alignment, volatility regime, RSI divergence

Usage:
    # Order-flow + volume profile from ticks (requires tick parquets)
    python scripts/features_advanced.py --mode orderflow --symbols XAUUSD --freqs 1min

    # Multi-TF confluence (requires existing feature files for all TFs)
    python scripts/features_advanced.py --mode multitf --symbol XAUUSD --main-tf 1min --higher-tfs 5min,15min

    # All in one
    python scripts/features_advanced.py --mode all --symbols XAUUSD --freqs 1min,5min,15min
"""
import argparse
import json
import os
import sys
import warnings
from datetime import datetime, timezone
from glob import glob

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = os.path.dirname(os.path.dirname(__file__))
TICK_DIR = os.path.join(ROOT, "artifacts", "tick_data")
MEGA_TICK_DIR = os.path.join(ROOT, "artifacts", "mega_data", "ticks")
FEAT_DIR = os.path.join(ROOT, "artifacts", "features")
OUT_DIR = os.path.join(ROOT, "artifacts", "features_v2")


# ──────────────────────────────────────────────
# 1. ORDER-FLOW PROXY + VOLUME PROFILE FROM TICKS
# ──────────────────────────────────────────────

def load_ticks(symbol: str) -> pd.DataFrame:
    """Load tick data from all available directories."""
    search_dirs = [TICK_DIR, MEGA_TICK_DIR]
    paths = []
    for d in search_dirs:
        paths += glob(os.path.join(d, f"{symbol}_bulk.csv"))
        paths += glob(os.path.join(d, f"{symbol}_ticks_*.parquet"))
        paths += glob(os.path.join(d, f"{symbol}_ticks_*.csv"))

    # Deduplicate by normalizing path
    paths = list(dict.fromkeys(paths))

    if not paths:
        print(f"  [SKIP] {symbol}: no tick files")
        return pd.DataFrame()

    dfs = []
    for p in paths:
        try:
            df = pd.read_parquet(p) if p.endswith('.parquet') else pd.read_csv(p)
        except Exception:
            continue
        if 'time' in df.columns:
            df['timestamp'] = pd.to_datetime(df['time'], unit='s', utc=True)
        elif 'timestamp_utc' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp_utc'], utc=True)
        else:
            continue
        df = df.sort_values('timestamp').drop_duplicates(subset='timestamp')
        dfs.append(df)

    if not dfs:
        return pd.DataFrame()

    combined = pd.concat(dfs).sort_values('timestamp').drop_duplicates(subset='timestamp')

    # Ensure bid/ask exist
    if 'bid' not in combined.columns or 'ask' not in combined.columns:
        print(f"  [SKIP] {symbol}: needs bid/ask columns")
        return pd.DataFrame()

    print(f"  [OK] {symbol}: {len(combined)} ticks from {len(paths)} file(s)")
    return combined


def classify_ticks(ticks: pd.DataFrame) -> pd.DataFrame:
    """Add tick-direction columns using the tick rule (last-price comparison)."""
    df = ticks.copy()
    # Use 'last' if available, else mid-price
    price_col = 'last' if 'last' in df.columns and df['last'].notna().any() else None
    if price_col is None:
        df['mid'] = (df['bid'] + df['ask']) / 2
        price_col = 'mid'

    # Tick rule: uptick if price > prev, downtick if < prev, zero-tick if ==
    df['price_prev'] = df[price_col].shift(1)
    df['tick_up'] = ((df[price_col] > df['price_prev'])).astype(int)
    df['tick_down'] = ((df[price_col] < df['price_prev'])).astype(int)
    df['tick_zero'] = ((df[price_col] == df['price_prev'])).astype(int)

    # Cumulative delta (up - down ticks within bar)
    df['tick_delta'] = df['tick_up'] - df['tick_down']

    # Micro-price bias: where is trade relative to mid?
    df['mid_price'] = (df['bid'] + df['ask']) / 2
    df['micro_bias'] = df[price_col] - df['mid_price']
    df['spread'] = df['ask'] - df['bid']

    # Tick size (absolute price change)
    df['tick_size'] = df[price_col].diff().abs()

    return df


def resample_orderflow(ticks: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Resample classified ticks -> order-flow features at given freq."""
    df = ticks.set_index('timestamp')

    agg = {
        'tick_up': 'sum',
        'tick_down': 'sum',
        'tick_zero': 'sum',
        'tick_delta': 'sum',
        'micro_bias': ['mean', 'std'],
        'spread': ['mean', 'max', 'std'],
        'tick_size': 'mean',
        'bid': 'count',  # total tick count per bar
    }

    # Add mid_price volatility if available
    if 'mid_price' in df.columns:
        agg['mid_price'] = 'std'

    # Some columns might not exist if ticks were tiny, handle gracefully
    available = {k: v for k, v in agg.items() if k in df.columns}
    resampled = df.resample(freq).agg(available)

    # Flatten multi-level columns
    if isinstance(resampled.columns, pd.MultiIndex):
        resampled.columns = [f"{col[0]}_{col[1]}" if col[1] else col[0]
                             for col in resampled.columns]
    else:
        # Single level -- rename to avoid clashes
        resampled = resampled.add_suffix('_bar')

    # Derivative features
    total_ticks = (resampled.get('tick_up_sum', 0)
                   + resampled.get('tick_down_sum', 0)
                   + resampled.get('tick_zero_sum', 0))
    total_ticks = total_ticks.replace(0, np.nan)

    # ── Order-flow proxy ──
    resampled['tick_imbalance'] = (
        resampled.get('tick_up_sum', 0) - resampled.get('tick_down_sum', 0)
    ) / total_ticks
    resampled['tick_direction_ratio'] = (
        resampled.get('tick_up_sum', 0) / total_ticks
    )
    resampled['cumulative_delta'] = resampled.get('tick_delta_sum', 0)

    # ── Micro-price / microstructure ──
    resampled['micro_bias_mean'] = resampled.get('micro_bias_mean', 0)
    resampled['micro_bias_volatility'] = resampled.get('micro_bias_std', 0)

    # ── Spread features ──
    resampled['spread_mean'] = resampled.get('spread_mean', 0)
    resampled['spread_max'] = resampled.get('spread_max', 0)
    resampled['spread_volatility'] = resampled.get('spread_std', 0)

    # ── Volume profile proxy ──
    resampled['tick_concentration'] = (
        resampled.get('bid_count', 0) /
        (resampled.get('spread_std', 1e-10) + 1e-10)
    )
    resampled['avg_tick_size'] = resampled.get('tick_size_mean', 0)

    # Mid-price volatility (microstructure noise proxy)
    if 'mid_price_std' in resampled.columns:
        resampled['micro_price_volatility'] = resampled['mid_price_std']

    # Clean up -- drop raw intermediate columns
    drop_cols = [c for c in resampled.columns
                 if c.endswith(('_sum', '_std', '_mean', '_max'))
                 and c not in ('spread_mean', 'spread_max', 'spread_volatility',
                               'micro_bias_mean', 'micro_bias_volatility',
                               'avg_tick_size')]
    for c in drop_cols:
        if c not in ('tick_delta_sum',):  # keep cumulative_delta via this
            resampled = resampled.drop(columns=[c], errors='ignore')

    return resampled.dropna()


# ──────────────────────────────────────────────
# 2. MULTI-TIMEFRAME CONFLUENCE
# ──────────────────────────────────────────────

def load_feature_file(symbol: str, freq: str) -> pd.DataFrame:
    """Load existing feature parquet with timestamp index."""
    path = os.path.join(FEAT_DIR, f"features_{symbol}_{freq}.parquet")
    if not os.path.exists(path):
        paths = glob(os.path.join(FEAT_DIR, f"features_{symbol}*{freq}*.parquet"))
        if not paths:
            return pd.DataFrame()
        path = paths[0]
    df = pd.read_parquet(path)
    # Ensure timestamp is the index for alignment
    if 'timestamp' in df.columns:
        df = df.set_index('timestamp')
    elif not isinstance(df.index, pd.DatetimeIndex):
        return pd.DataFrame()
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def compute_multitf_confluence(symbol: str, main_tf: str, higher_tfs: list[str]) -> pd.DataFrame:
    """
    Load main-TF features and higher-TF features, compute cross-TF confluence indicators.

    For each bar in main_tf, forward-fill higher-TF indicators so every 1min bar
    "sees" the current 5min/15min bar's state.
    """
    main = load_feature_file(symbol, main_tf)
    if main.empty:
        print(f"  [ERROR] No {main_tf} features for {symbol}")
        return pd.DataFrame()

    print(f"  [OK] Main TF {main_tf}: {len(main)} bars")

    # Indicators from main that we'll compare
    confluences = pd.DataFrame(index=main.index)

    for htf in higher_tfs:
        higher = load_feature_file(symbol, htf)
        if higher.empty:
            print(f"  [SKIP] Higher TF {htf} not found")
            continue

        print(f"  [OK] Higher TF {htf}: {len(higher)} bars")

        # Forward-fill higher TF to main TF resolution
        # Every main bar sees the most recent higher-TF bar's values
        higher_ff = higher.reindex(main.index, method='ffill')

        # === Trend alignment ===
        if 'sma_ratio' in main.columns and 'sma_ratio' in higher_ff.columns:
            confluences[f'trend_align_{htf}'] = (
                (main['sma_ratio'] - 1) * (higher_ff['sma_ratio'] - 1) > 0
            ).astype(int)

        # === Volatility regime ===
        if 'volatility_15' in main.columns and 'volatility_15' in higher_ff.columns:
            confluences[f'vol_regime_{htf}'] = (
                main['volatility_15'] / (higher_ff['volatility_15'] + 1e-10)
            )

        # === RSI divergence ===
        if 'rsi_14' in main.columns and 'rsi_14' in higher_ff.columns:
            confluences[f'rsi_divergence_{htf}'] = (
                main['rsi_14'] - higher_ff['rsi_14']
            )

        # === MACD trend alignment ===
        if 'macd_hist' in main.columns and 'macd_hist' in higher_ff.columns:
            confluences[f'macd_trend_align_{htf}'] = (
                (main['macd_hist'] * higher_ff['macd_hist']) > 0
            ).astype(int)

        # === BB zone (relative to higher TF) ===
        if 'bb_mid' in higher_ff.columns and 'bb_width' in higher_ff.columns and 'close' in main.columns:
            confluences[f'bb_zone_{htf}'] = (
                main['close'] - higher_ff['bb_mid']
            ) / (higher_ff['bb_mid'] * higher_ff['bb_width'] + 1e-10)

        # === Volatility expansion (short vol / long vol) ===
        if 'volatility_5' in main.columns and 'volatility_5' in higher_ff.columns:
            confluences[f'vol_expansion_{htf}'] = (
                main['volatility_5'] / (higher_ff['volatility_5'] + 1e-10)
            )

        # === ATR ratio ===
        if 'atr_5' in main.columns and 'atr_5' in higher_ff.columns:
            confluences[f'atr_ratio_{htf}'] = (
                main['atr_5'] / (higher_ff['atr_5'] + 1e-10)
            )

        # === Close relative to higher-TF Bollinger ===
        if all(c in higher_ff.columns for c in ['bb_upper', 'bb_lower']):
            bb_range = higher_ff['bb_upper'] - higher_ff['bb_lower']
            confluences[f'bb_squeeze_{htf}'] = (
                bb_range / (higher_ff['bb_mid'] + 1e-10)
            )

    if len(confluences.columns) == 0:
        print("  [WARN] No confluence features computed -- check TF indicator availability")
        # Return at least the empty structure
        confluences['_no_confluence'] = 0

    print(f"  [OK] Confluence features: {len(confluences.columns)}")
    for c in confluences.columns:
        non_null = confluences[c].notna().sum()
        print(f"    {c}: {non_null} non-null")

    return confluences


# ──────────────────────────────────────────────
# 3. MASTER: ADD ORDER-FLOW FEATURES TO EXISTING FEATURES
# ──────────────────────────────────────────────

def merge_orderflow_to_features(symbol: str, freq: str, of_df: pd.DataFrame) -> pd.DataFrame:
    """Load existing feature file, merge order-flow features, save to v2."""
    feats = load_feature_file(symbol, freq)
    if feats.empty:
        return pd.DataFrame()

    # Align on index, keep only common timestamps
    common_idx = feats.index.intersection(of_df.index)
    feats = feats.loc[common_idx]
    of_aligned = of_df.loc[common_idx]

    # Join -- order-flow columns get suffix to distinguish from existing
    of_cols = [c for c in of_df.columns
               if c not in ('timestamp',) and c not in feats.columns]
    for c in of_cols:
        feats[c] = of_aligned[c]

    print(f"  [OK] Added {len(of_cols)} order-flow features")
    return feats


def merge_confluence_to_features(feats: pd.DataFrame, confluence: pd.DataFrame) -> pd.DataFrame:
    """Merge confluence features into feature DataFrame."""
    common_idx = feats.index.intersection(confluence.index)
    result = feats.loc[common_idx].copy()
    for c in confluence.columns:
        if c not in result.columns:
            result[c] = confluence.loc[common_idx, c]
    print(f"  [OK] Added {len(confluence.columns)} multi-TF confluence features")
    return result


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Advanced feature engineering")
    parser.add_argument("--mode", choices=["orderflow", "multitf", "all"],
                        default="all", help="Feature mode")
    parser.add_argument("--symbols", type=str, default="XAUUSD,EURUSD,GBPUSD",
                        help="Comma-separated symbols (for orderflow)")
    parser.add_argument("--symbol", type=str, default="XAUUSD",
                        help="Single symbol (for multitf)")
    parser.add_argument("--freqs", type=str, default="1min,5min,15min",
                        help="Comma-separated freqs (for orderflow)")
    parser.add_argument("--main-tf", type=str, default="1min",
                        help="Main timeframe (for multitf)")
    parser.add_argument("--higher-tfs", type=str, default="5min,15min",
                        help="Higher timeframes (for multitf)")
    parser.add_argument("--tick-dir", type=str, default=TICK_DIR)
    parser.add_argument("--feat-dir", type=str, default=FEAT_DIR)
    parser.add_argument("--output", type=str, default=OUT_DIR)
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    mode = args.mode
    symbols = [s.strip() for s in args.symbols.split(",")]
    freqs = [f.strip() for f in args.freqs.split(",")]

    print(f"{'='*60}")
    print("ADVANCED FEATURE ENGINEERING")
    print(f"  Mode: {mode}")
    print(f"  Output: {args.output}")
    print(f"{'='*60}")

    # ── Mode: Order-flow proxy ──
    orderflow_features = {}  # key: {symbol}_{freq} -> DataFrame
    if mode in ("orderflow", "all"):
        print("\n=== Phase 1: Order-flow proxy + Volume profile ===")
        for sym in symbols:
            ticks = load_ticks(sym)
            if ticks.empty:
                continue
            classified = classify_ticks(ticks)
            for freq in freqs:
                of = resample_orderflow(classified, freq)
                if of.empty:
                    print(f"  [SKIP] {sym} @ {freq}: no order-flow data")
                    continue
                key = f"{sym}_{freq}"
                orderflow_features[key] = of
                print(f"  [OK] {key}: {len(of)} bars, {len(of.columns)} features")

    # ── Mode: Multi-TF confluence ──
    confluence_features = None  # DataFrame with combined confluences for main_tf
    if mode in ("multitf", "all"):
        print(f"\n=== Phase 2: Multi-TF confluence ===")
        higher_tfs = [t.strip() for t in args.higher_tfs.split(",")]
        # Process all symbols, but for "all" mode use the first symbol
        target_symbol = args.symbol
        if mode == "all" and symbols:
            target_symbol = symbols[0]
        confluence_features = compute_multitf_confluence(
            target_symbol, args.main_tf, higher_tfs
        )

    # ── Merge and save ──
        print(f"\n=== Phase 3: Merge + Save ===")
    v2_files = []

    for sym in symbols:
        for freq in freqs:
            key = f"{sym}_{freq}"

            # Load existing v2 file if it exists (preserves previously-added features)
            v2_path = os.path.join(args.output, f"features_v2_{key}.parquet")
            if os.path.exists(v2_path):
                base_feats = pd.read_parquet(v2_path)
                if 'timestamp' not in base_feats.columns:
                    base_feats = base_feats.reset_index()
                if 'timestamp' in base_feats.columns:
                    base_feats = base_feats.set_index('timestamp')
                    base_feats.index = pd.to_datetime(base_feats.index, utc=True)
                print(f"\n--- {key} (loading v2: {len(base_feats)} rows) ---")
            else:
                base_feats = load_feature_file(sym, freq)
                if base_feats.empty:
                    continue
                print(f"\n--- {key} ---")

            merged = base_feats.copy()

            # Merge order-flow
            if key in orderflow_features:
                of_idx = merged.index.intersection(orderflow_features[key].index)
                of_cols = [c for c in orderflow_features[key].columns
                           if c not in merged.columns]
                for c in of_cols:
                    merged[c] = orderflow_features[key][c]
                print(f"  Order-flow: +{len(of_cols)} cols ({len(of_idx)} rows)")

            # Merge confluence (only for matching symbol and main_tf)
            if confluence_features is not None and freq == args.main_tf and sym == args.symbol:
                cf_idx = merged.index.intersection(confluence_features.index)
                for c in confluence_features.columns:
                    if c not in merged.columns:
                        merged[c] = confluence_features[c]
                print(f"  Confluence: +{len(confluence_features.columns)} cols ({len(cf_idx)} rows)")

            # Save
            out_path = os.path.join(args.output, f"features_v2_{key}.parquet")
            merged.to_parquet(out_path)
            v2_files.append(out_path)
            feat_count = len([c for c in merged.columns
                              if c not in ('symbol', 'freq', 'target', 'target_return')])
            print(f"  Saved: {len(merged)} rows x {feat_count} features -> {out_path}")

    # Summary
    print(f"\n{'='*60}")
    print("ADVANCED FEATURE ENGINEERING COMPLETE")
    print(f"  V2 files: {len(v2_files)}")

    if v2_files:
        # Quick counts
        for p in v2_files:
            df = pd.read_parquet(p)
            feat = [c for c in df.columns if c not in ('symbol', 'freq', 'target', 'target_return')]
            print(f"  {os.path.basename(p)}: {len(df)} rows, {len(feat)} features")

    # Run record
    record = {
        "run_time_utc": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "symbols": symbols,
        "freqs": freqs if mode in ("orderflow", "all") else None,
        "main_tf": args.main_tf if mode in ("multitf", "all") else None,
        "higher_tfs": args.higher_tfs if mode in ("multitf", "all") else None,
        "output_files": v2_files,
        "orderflow_keys": list(orderflow_features.keys()),
        "has_confluence": confluence_features is not None,
    }
    with open(os.path.join(args.output, "advanced_features_run.json"), 'w') as f:
        json.dump(record, f, indent=2)
    print(f"  Run record: {os.path.join(args.output, 'advanced_features_run.json')}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
