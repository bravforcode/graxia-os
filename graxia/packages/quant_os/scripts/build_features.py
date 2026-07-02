"""
FEATURE ENGINEERING — Build ML training features from warehouse data.

Reads OHLCV data from warehouse (DuckDB or Parquet) or legacy CSV tick files,
computes technical indicators and advanced feature families, and outputs a
feature matrix ready for strategy model training.

Feature families:
  v1              — Price-based, moving averages, volatility, momentum (31 cols)
  session         — Session-aware features (Asian/European/US)
  regime          — Market regime features (volatility regime, ADX, ROC)
  microstructure  — Micro-price, tick intensity, spread efficiency (needs ticks)
  cross_asset     — Cross-asset correlations (needs multiple symbols)
  all             — All of the above

Usage:
    # Warehouse parquet input
    python scripts/build_features.py
      --input data/warehouse/ohlcv/symbol=EURUSD/
      --features session,regime,microstructure,cross_asset,all
      --output data/warehouse/features/EURUSD/
      --db-path data/warehouse/quantos.duckdb
      --validate

    # Legacy CSV tick input
    python scripts/build_features.py --symbols XAUUSD,EURUSD --freqs 1min,5min
"""
import argparse
import json
import os
import sys
from datetime import datetime, time as dtime, UTC
from glob import glob
from typing import Optional

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT, "artifacts", "features")

# ── Forex session boundaries (UTC) ──
ASIAN_OPEN = dtime(0, 0)
ASIAN_CLOSE = dtime(9, 0)
EURO_OPEN = dtime(7, 0)
EURO_CLOSE = dtime(16, 0)
US_OPEN = dtime(12, 0)
US_CLOSE = dtime(21, 0)

# ── Data loading ──


def read_warehouse(
    input_path: str,
    symbols: list[str],
    db_path: Optional[str] = None,
) -> dict[str, pd.DataFrame]:
    """Load OHLCV data from warehouse parquet or DuckDB.

    Supports:
      - Hive-partitioned parquet:  path/symbol=XXX/year=YYYY/month=MM/
      - Flat parquet directory:    path/*.parquet
      - Single parquet file:       path/file.parquet
      - DuckDB table:              via --db-path

    Returns {symbol: DataFrame} with columns
    [timestamp, open, high, low, close, volume].
    """
    if db_path and os.path.isfile(db_path):
        return _read_from_duckdb(db_path, symbols)

    if os.path.isfile(input_path):
        return _read_single_file(input_path, symbols)

    if os.path.isdir(input_path):
        return _read_partitioned_dir(input_path, symbols)

    print(f"  [ERROR] Input not found: {input_path}")
    return {}


def _read_from_duckdb(db_path: str, symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Read OHLCV data from DuckDB database."""
    try:
        import duckdb
    except ImportError:
        print("  [ERROR] duckdb not installed. Try: pip install duckdb")
        return {}

    conn = duckdb.connect(db_path)
    result: dict[str, pd.DataFrame] = {}
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()]
        for sym in symbols:
            table_candidates = [t for t in tables if sym.lower() in t.lower()]
            if not table_candidates:
                print(f"  [SKIP] {sym}: no table in DuckDB")
                continue
            tbl = table_candidates[0]
            df = conn.execute(f"SELECT * FROM \"{tbl}\"").df()
            df = _normalize_ohlcv(df)
            if df.empty:
                continue
            df = df.sort_values('timestamp').drop_duplicates(subset='timestamp')
            result[sym] = df
            print(f"  [OK] {sym}: {len(df)} rows from DuckDB table '{tbl}'")
    finally:
        conn.close()
    return result


def _read_single_file(path: str, symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Read a single parquet or CSV file, assigning the first symbol."""
    ext = os.path.splitext(path)[1].lower()
    if ext == '.parquet':
        df = pd.read_parquet(path)
    elif ext == '.csv':
        df = pd.read_csv(path)
    else:
        print(f"  [ERROR] Unsupported format: {ext}")
        return {}

    df = _normalize_ohlcv(df)
    if df.empty:
        return {}
    df = df.sort_values('timestamp').drop_duplicates(subset='timestamp')
    sym = symbols[0] if symbols else 'UNKNOWN'
    print(f"  [OK] {sym}: {len(df)} rows from {os.path.basename(path)}")
    return {sym: df}


def _read_partitioned_dir(
    dir_path: str, symbols: list[str]
) -> dict[str, pd.DataFrame]:
    """Read hive-partitioned or flat parquet directory.

    Detects hive partitioning by looking for ``symbol=XXX`` subdirectories.
    If not found, scans for all ``*.parquet`` files.
    """
    import pathlib

    p = pathlib.Path(dir_path)
    result: dict[str, pd.DataFrame] = {}

    # Try hive-partitioned: symbol=EURUSD/year=2024/month=01/data.parquet
    sym_patterns = [f"symbol={sym}" for sym in symbols]
    found_symbols = set()
    for child in p.iterdir():
        if child.is_dir() and child.name.startswith("symbol="):
            found_symbols.add(child.name.split("=", 1)[1])

    if found_symbols:
        for sym in symbols:
            if sym not in found_symbols:
                print(f"  [SKIP] {sym}: not found in partitioned dir")
                continue
            sym_dir = p / f"symbol={sym}"
            parquet_files = sorted(sym_dir.rglob("*.parquet"))
            if not parquet_files:
                print(f"  [SKIP] {sym}: no parquet files under {sym_dir}")
                continue
            dfs = []
            for pf in parquet_files:
                dfs.append(pd.read_parquet(pf))
            combined = pd.concat(dfs, ignore_index=True)
            combined = _normalize_ohlcv(combined)
            if combined.empty:
                continue
            combined = (
                combined.sort_values('timestamp')
                .drop_duplicates(subset='timestamp')
            )
            result[sym] = combined
            print(f"  [OK] {sym}: {len(combined)} rows from {len(parquet_files)} files")
        return result

    # Flat directory: all parquet files (recursive for nested Hive partitions)
    parquet_files = sorted(p.rglob("*.parquet"))
    if not parquet_files:
        print(f"  [ERROR] No parquet files found in {dir_path}")
        return {}

    dfs = [pd.read_parquet(f) for f in parquet_files]
    combined = pd.concat(dfs, ignore_index=True)
    combined = _normalize_ohlcv(combined)
    if combined.empty:
        return {}
    combined = combined.sort_values('timestamp').drop_duplicates(subset='timestamp')
    sym = symbols[0] if symbols else 'UNKNOWN'
    result[sym] = combined
    print(f"  [OK] {sym}: {len(combined)} rows from {len(parquet_files)} flat files")
    return result


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize OHLCV columns to canonical names and types."""
    if df.empty:
        return df

    col_map = {}
    for c in df.columns:
        cl = c.lower().strip()
        if cl in ('time', 'timestamp', 'datetime', 'date', 'ts'):
            col_map[c] = 'timestamp'
        elif cl in ('open', 'o'):
            col_map[c] = 'open'
        elif cl in ('high', 'h'):
            col_map[c] = 'high'
        elif cl in ('low', 'l'):
            col_map[c] = 'low'
        elif cl in ('close', 'c', 'last', 'price'):
            col_map[c] = 'close'
        elif cl in ('volume', 'vol', 'tick_volume', 'tickvol', 'tv'):
            col_map[c] = 'volume'
        elif cl in ('bid',):
            col_map[c] = 'bid'
        elif cl in ('ask',):
            col_map[c] = 'ask'

    df = df.rename(columns=col_map)

    required = {'timestamp', 'open', 'high', 'low', 'close'}
    missing = required - set(df.columns)
    if missing:
        print(f"  [WARN] Missing columns: {missing}")
        return pd.DataFrame()

    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    for col in ('open', 'high', 'low', 'close', 'volume'):
        df[col] = pd.to_numeric(df[col], errors='coerce')

    return df


def load_ticks(tick_dir: str, symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Load tick CSVs/parquets into DataFrames. Returns {symbol: DataFrame}."""
    result: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        paths = (
            glob(os.path.join(tick_dir, f"{sym}_bulk.csv"))
            + glob(os.path.join(tick_dir, f"{sym}_ticks_*.csv"))
            + glob(os.path.join(tick_dir, f"{sym}_ticks_*.parquet"))
        )
        if not paths:
            print(f"  [SKIP] {sym}: no tick files found")
            continue
        dfs = []
        for p in paths:
            df = (
                pd.read_parquet(p)
                if p.endswith('.parquet')
                else pd.read_csv(p)
            )
            if 'time' in df.columns:
                df['timestamp'] = pd.to_datetime(df['time'], unit='s', utc=True)
            elif 'timestamp_utc' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp_utc'], utc=True)
            else:
                continue
            df = df.sort_values('timestamp').drop_duplicates(subset='timestamp')
            dfs.append(df)
        if dfs:
            combined = (
                pd.concat(dfs)
                .sort_values('timestamp')
                .drop_duplicates(subset='timestamp')
            )
            result[sym] = combined
            print(f"  [OK] {sym}: {len(combined)} ticks loaded")
    return result


def resample_ohlcv(ticks: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Resample tick data to OHLCV candles at given frequency."""
    if ticks.empty or 'timestamp' not in ticks.columns:
        return pd.DataFrame()

    df = ticks.set_index('timestamp')

    if 'bid' in df.columns:
        bid_ohlc = df['bid'].resample(freq).ohlc()
        bid_ohlc.columns = ['open', 'high', 'low', 'close']
    elif 'last' in df.columns:
        bid_ohlc = df['last'].resample(freq).ohlc()
        bid_ohlc.columns = ['open', 'high', 'low', 'close']
    elif 'ask' in df.columns:
        bid_ohlc = df['ask'].resample(freq).ohlc()
        bid_ohlc.columns = ['open', 'high', 'low', 'close']
    else:
        return pd.DataFrame()

    volume = (
        df['volume'].resample(freq).sum()
        if 'volume' in df.columns
        else pd.Series(0, index=bid_ohlc.index)
    )
    tick_count = (
        df['bid'].resample(freq).count()
        if 'bid' in df.columns
        else df['ask'].resample(freq).count()
    )
    if 'ask' in df.columns and 'bid' in df.columns:
        spread = (df['ask'] - df['bid']).resample(freq).mean()
    else:
        spread = pd.Series(0.0, index=bid_ohlc.index)

    result = pd.concat(
        [
            bid_ohlc,
            volume.rename('volume'),
            tick_count.rename('tick_count'),
            spread.rename('spread_mean'),
        ],
        axis=1,
    )
    return result.dropna()


# ── V1 Features (existing, backward compatible) ──


def compute_features(ohlc: pd.DataFrame) -> pd.DataFrame:
    """Compute V1 technical indicators from OHLCV data."""
    if ohlc.empty:
        return ohlc

    df = ohlc.copy()

    df['return_1'] = df['close'].pct_change(1)
    df['return_5'] = df['close'].pct_change(5)
    df['return_15'] = df['close'].pct_change(15)
    df['return_60'] = df['close'].pct_change(60)
    df['log_return'] = np.log(df['close'] / df['close'].shift(1))

    df['high_minus_low'] = df['high'] - df['low']
    df['close_position'] = (df['close'] - df['low']) / (
        df['high'] - df['low'] + 1e-10
    )

    df['volatility_5'] = df['return_1'].rolling(5).std()
    df['volatility_15'] = df['return_1'].rolling(15).std()

    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1)),
        ),
    )
    df['atr_7'] = df['tr'].rolling(7).mean()
    df['atr_14'] = df['tr'].rolling(14).mean()

    delta = df['close'].diff()
    gain_7 = delta.where(delta > 0, 0).rolling(7).mean()
    loss_7 = (-delta.where(delta < 0, 0)).rolling(7).mean()
    rs_7 = gain_7 / (loss_7 + 1e-10)
    df['rsi_7'] = 100 - (100 / (1 + rs_7))
    gain_14 = delta.where(delta > 0, 0).rolling(14).mean()
    loss_14 = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs_14 = gain_14 / (loss_14 + 1e-10)
    df['rsi_14'] = 100 - (100 / (1 + rs_14))

    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    df['bb_mid'] = df['close'].rolling(20).mean()
    df['bb_std'] = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_mid'] + 2 * df['bb_std']
    df['bb_lower'] = df['bb_mid'] - 2 * df['bb_std']
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid']
    df['bb_position'] = (df['close'] - df['bb_lower']) / (
        df['bb_upper'] - df['bb_lower'] + 1e-10
    )

    for period in (5, 10, 20, 50, 200):
        df[f'sma_{period}'] = df['close'].rolling(period).mean()
    df['ema_12'] = df['close'].ewm(span=12).mean()
    df['ema_26'] = df['close'].ewm(span=26).mean()
    df['sma_ratio'] = df['sma_5'] / df['sma_20']

    df['obv'] = (np.sign(df['return_1']) * df['volume']).fillna(0).cumsum()
    df['volume_ratio'] = df['volume'] / df['volume'].rolling(20).mean()

    df['spread_pips'] = df['spread_mean'] * 10000 if 'spread_mean' in df.columns else 0.0
    df['spread_zscore'] = (
        (df['spread_pips'] - df['spread_pips'].rolling(50).mean())
        / (df['spread_pips'].rolling(50).std() + 1e-10)
    )

    # Stochastic
    low_14 = df['low'].rolling(14).min()
    high_14 = df['high'].rolling(14).max()
    df['stoch_k'] = 100 * (df['close'] - low_14) / (high_14 - low_14 + 1e-10)
    df['stoch_d'] = df['stoch_k'].rolling(3).mean()

    df['target'] = (df['close'].shift(-1) > df['close']).astype(int)
    df['target_return'] = df['return_1'].shift(-1)

    return df.dropna()


# ── New Feature Families ──


def compute_session_features(
    ohlc: pd.DataFrame, symbol: str
) -> pd.DataFrame:
    """Compute session-aware features.

    Features:
      - session_asian, session_european, session_us         (binary)
      - session_overlap_ae, session_overlap_eu              (binary)
      - minutes_since_session_open                          (int)
      - atr_session_ratio                                   (float)
    """
    df = ohlc.copy()
    ts = df.index if isinstance(df.index, pd.DatetimeIndex) else df.index

    hour = ts.hour
    minute = ts.minute
    time_of_day = hour + minute / 60.0

    df['session_asian'] = (
        (time_of_day >= ASIAN_OPEN.hour)
        & (time_of_day < ASIAN_CLOSE.hour)
    ).astype(int)
    df['session_european'] = (
        (time_of_day >= EURO_OPEN.hour)
        & (time_of_day < EURO_CLOSE.hour)
    ).astype(int)
    df['session_us'] = (
        (time_of_day >= US_OPEN.hour)
        & (time_of_day < US_CLOSE.hour)
    ).astype(int)

    df['session_overlap_ae'] = (
        (time_of_day >= max(ASIAN_OPEN.hour, EURO_OPEN.hour))
        & (time_of_day < min(ASIAN_CLOSE.hour, EURO_CLOSE.hour))
    ).astype(int)
    df['session_overlap_eu'] = (
        (time_of_day >= max(EURO_OPEN.hour, US_OPEN.hour))
        & (time_of_day < min(EURO_CLOSE.hour, US_CLOSE.hour))
    ).astype(int)

    session_opens = {
        'asian': ASIAN_OPEN.hour,
        'european': EURO_OPEN.hour,
        'us': US_OPEN.hour,
    }
    for name, open_hour in session_opens.items():
        df[f'minutes_since_{name}_open'] = np.maximum(
            0, (time_of_day - open_hour) * 60
        )

    session_avg_atr = df.groupby(
        4 * df['session_asian'] + 2 * df['session_european'] + 1 * df['session_us']
    )['atr_14'].transform('mean')
    df['atr_session_ratio'] = df['atr_14'] / (session_avg_atr + 1e-10)

    return df


def compute_regime_features(ohlc: pd.DataFrame) -> pd.DataFrame:
    """Compute market regime features from OHLCV.

    Features:
      - vol_regime:       atr_14 / sma_50_close (low/med/high)
      - adx_14:           Average Directional Index
      - adx_strength:     adx_14 > 25 (trending)
      - roc_20:           20-period rate of change
      - roc_percentile:   ROC(20) percentile vs trailing 90 bars
    """
    df = ohlc.copy()

    df['sma_50_close'] = df['close'].rolling(50).mean()
    df['vol_regime_ratio'] = df['atr_14'] / (df['sma_50_close'] + 1e-10)

    vol_regime_bins = [-np.inf, 0.001, 0.003, np.inf]
    df['vol_regime'] = pd.cut(
        df['vol_regime_ratio'],
        bins=vol_regime_bins,
        labels=[0, 1, 2],
    ).cat.add_categories([-1]).fillna(-1).astype(int)

    # ADX(14)
    tr = df['tr'] if 'tr' in df.columns else (
        np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1)),
            ),
        )
    )
    up_move = df['high'].diff()
    down_move = -df['low'].diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    atr_14 = tr.rolling(14).mean()
    plus_di_14 = 100 * pd.Series(plus_dm, index=df.index).rolling(14).mean() / (
        atr_14 + 1e-10
    )
    minus_di_14 = 100 * pd.Series(minus_dm, index=df.index).rolling(14).mean() / (
        atr_14 + 1e-10
    )
    dx = 100 * abs(plus_di_14 - minus_di_14) / (plus_di_14 + minus_di_14 + 1e-10)
    df['adx_14'] = dx.rolling(14).mean()
    df['adx_strength'] = (df['adx_14'] > 25).astype(int)
    df['plus_di_14'] = plus_di_14
    df['minus_di_14'] = minus_di_14

    df['roc_20'] = df['close'].pct_change(20)
    df['roc_percentile'] = (
        df['roc_20']
        .rolling(90)
        .apply(
            lambda x: (
                (x.rank(pct=True).iloc[-1] * 100) if len(x) >= 20 else np.nan
            ),
            raw=False,
        )
    )

    return df


def compute_microstructure_features(
    ohlc: pd.DataFrame, ticks: Optional[pd.DataFrame], freq: str
) -> pd.DataFrame:
    """Compute microstructure features from tick data.

    Requires tick-level data with bid/ask columns. If ticks are not available,
    returns the OHLC DataFrame unchanged.

    Features:
      - tick_intensity:       ticks per minute, z-scored vs 1h window
      - micro_price:          (bid * ask_vol + ask * bid_vol) / (bid_vol + ask_vol)
      - spread_efficiency:    (mid - micro_price) / spread
      - tick_imbalance:       (up_ticks - down_ticks) / total_ticks
    """
    if ticks is None or ticks.empty:
        return ohlc

    has_bid_ask = 'bid' in ticks.columns and 'ask' in ticks.columns
    if not has_bid_ask:
        return ohlc

    df_ticks = ticks.copy()
    if 'timestamp' in df_ticks.columns:
        df_ticks = df_ticks.set_index('timestamp')
    ts_idx = df_ticks.index

    df_ticks['mid'] = (df_ticks['bid'] + df_ticks['ask']) / 2.0
    df_ticks['spread'] = df_ticks['ask'] - df_ticks['bid']

    price_col = (
        'last'
        if 'last' in df_ticks.columns and df_ticks['last'].notna().any()
        else 'mid'
    )
    df_ticks['price_prev'] = df_ticks[price_col].shift(1)
    df_ticks['tick_up'] = (df_ticks[price_col] > df_ticks['price_prev']).astype(int)
    df_ticks['tick_down'] = (df_ticks[price_col] < df_ticks['price_prev']).astype(int)

    # Micro-price: (bid * ask_vol + ask * bid_vol) / (bid_vol + bid_vol)
    bid_vol = df_ticks['bid_volume'] if 'bid_volume' in df_ticks.columns else df_ticks['volume'] if 'volume' in df_ticks.columns else pd.Series(1.0, index=ts_idx)
    ask_vol = df_ticks['ask_volume'] if 'ask_volume' in df_ticks.columns else df_ticks['volume'] if 'volume' in df_ticks.columns else pd.Series(1.0, index=ts_idx)
    total_vol = bid_vol + ask_vol
    df_ticks['micro_price'] = (
        df_ticks['bid'] * ask_vol + df_ticks['ask'] * bid_vol
    ) / (total_vol + 1e-10)

    # Resample to feature frequency
    resampled = pd.DataFrame(index=ohlc.index)
    tick_count = df_ticks['mid'].resample(freq).count()
    up_ticks = df_ticks['tick_up'].resample(freq).sum()
    down_ticks = df_ticks['tick_down'].resample(freq).sum()
    total_ticks = tick_count.replace(0, np.nan)

    resampled['tick_intensity'] = tick_count / (
        pd.Timedelta(freq).total_seconds() / 60.0
    )
    tick_intensity_1h = (
        resampled['tick_intensity']
        .rolling(60)
        .mean()
    )
    tick_intensity_std_1h = (
        resampled['tick_intensity']
        .rolling(60)
        .std()
    )
    resampled['tick_intensity_zscore'] = (
        resampled['tick_intensity'] - tick_intensity_1h
    ) / (tick_intensity_std_1h + 1e-10)

    resampled['tick_imbalance'] = (up_ticks - down_ticks) / total_ticks

    micro_price_bar = df_ticks['micro_price'].resample(freq).mean()
    spread_bar = df_ticks['spread'].resample(freq).mean()

    if 'close' in ohlc.columns:
        resampled['micro_price'] = micro_price_bar
        resampled['spread_efficiency'] = (
            (ohlc['close'] - micro_price_bar) / (spread_bar + 1e-10)
        )

    return resampled


def compute_cross_asset_features(
    current_ohlc: pd.DataFrame,
    all_ohlc: dict[str, pd.DataFrame],
    symbol: str,
    freq: str,
) -> pd.DataFrame:
    """Compute cross-asset correlation features.

    Features:
      - eurusd_corr_1h:      rolling 1h correlation with EURUSD
      - gbpusd_corr_1h:      rolling 1h correlation with GBPUSD
      - xauusd_corr_1h:      rolling 1h correlation with XAUUSD (risk proxy)
    """
    df = current_ohlc.copy()
    min_obs = max(int(pd.Timedelta('1h') / pd.Timedelta(freq)), 20)

    pairs = {
        'eurusd_corr_1h': 'EURUSD',
        'gbpusd_corr_1h': 'GBPUSD',
        'xauusd_corr_1h': 'XAUUSD',
    }

    for feat_name, other_sym in pairs.items():
        if other_sym == symbol.upper():
            df[feat_name] = 1.0
            continue
        if other_sym not in all_ohlc:
            continue
        other = all_ohlc[other_sym]
        if other.empty:
            continue
        common_idx = df.index.intersection(other.index)
        if len(common_idx) < min_obs:
            continue
        self_returns = df.loc[common_idx, 'return_1']
        other_returns = other.loc[common_idx, 'return_1']
        df[feat_name] = (
            self_returns
            .rolling(min_obs)
            .corr(other_returns)
        )

    return df


# ── Validation ──


def validate_features(df: pd.DataFrame, name: str) -> bool:
    """Run basic sanity checks on feature DataFrame.

    Checks:
      - No infinite values
      - Finite values for numeric columns
      - No completely empty columns
      - NaN proportions logged

    Returns True if all checks pass.
    """
    all_ok = True
    numeric_cols = df.select_dtypes(include=[np.number]).columns

    inf_count = np.isinf(df[numeric_cols].values).sum()
    if inf_count > 0:
        print(f"  [WARN] {name}: {inf_count} infinite values found")
        all_ok = False

    nan_counts = df[numeric_cols].isna().sum()
    high_nan = nan_counts[nan_counts > 0]
    if len(high_nan) > 0:
        for col, cnt in high_nan.items():
            pct = cnt / len(df) * 100
            if pct > 5:
                print(f"  [WARN] {name}: {col} has {pct:.1f}% NaN ({cnt})")
                all_ok = False

    empty_cols = [c for c in df.columns if df[c].isna().all()]
    if empty_cols:
        print(f"  [WARN] {name}: fully empty columns: {empty_cols}")
        all_ok = False

    memory_mb = df.memory_usage(deep=True).sum() / 1024 / 1024
    print(f"  [INFO] {name}: {len(df)} rows, {len(df.columns)} cols, {memory_mb:.2f} MB")

    return all_ok


# ── Main Pipeline ──


def _feature_summary(df: pd.DataFrame) -> str:
    """Return a compact feature count summary."""
    exclude = {'symbol', 'freq', 'target', 'target_return', 'timestamp'}
    names = [c for c in df.columns if c not in exclude]
    return f"{len(names)} features: {', '.join(names[:5])}{'...' if len(names) > 5 else ''}"


def _log_feature_nan(df: pd.DataFrame, prefix: str) -> None:
    """Log NaN counts for all features."""
    nan_counts = df.isna().sum()
    high = nan_counts[nan_counts > 0]
    if len(high) > 0:
        for col, cnt in high.items():
            print(f"  [NAN] {prefix}/{col}: {cnt}/{len(df)} ({cnt / len(df) * 100:.1f}%)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Feature engineering from warehouse or tick data"
    )

    # Input options
    parser.add_argument(
        "--input", type=str, default=None,
        help=(
            "Path to warehouse data (parquet dir, single parquet, or CSV). "
            "Overrides --tick-dir when provided."
        ),
    )
    parser.add_argument(
        "--db-path", type=str, default=None,
        help="Path to DuckDB database file",
    )
    parser.add_argument(
        "--tick-dir", type=str,
        default=os.path.join("artifacts", "tick_data"),
        help="Directory with tick CSVs (legacy mode)",
    )

    # Symbol / frequency
    parser.add_argument(
        "--symbols", type=str, default="XAUUSD,EURUSD,GBPUSD",
        help="Comma-separated symbols",
    )
    parser.add_argument(
        "--freqs", type=str, default="1min,5min,15min",
        help="Comma-separated resample frequencies",
    )

    # Feature selection
    FEATURE_FAMILIES = ['v1', 'session', 'regime', 'microstructure', 'cross_asset', 'all']
    parser.add_argument(
        "--features", type=str, default="all",
        help=(
            "Comma-separated feature families. "
            f"Available: {', '.join(FEATURE_FAMILIES)}"
        ),
    )

    # Output
    parser.add_argument(
        "--output", type=str, default=OUTPUT_DIR,
        help="Output directory for feature files",
    )

    # Validation
    parser.add_argument(
        "--validate", action='store_true',
        help="Run sanity checks on output features",
    )

    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")]
    freqs = [f.strip() for f in args.freqs.split(",")]
    feature_families = [
        f.strip() for f in args.features.split(",")
    ]
    if 'all' in feature_families:
        feature_families = [f for f in FEATURE_FAMILIES if f != 'all']
    # Auto-include v1 as prerequisite for advanced features that depend on it
    advanced = {'session', 'regime', 'microstructure', 'cross_asset'}
    if set(feature_families) & advanced:
        feature_families.insert(0, 'v1')
    # Deduplicate while preserving order
    seen = set()
    feature_families = [f for f in feature_families if not (f in seen or seen.add(f))]

    os.makedirs(args.output, exist_ok=True)

    print(f"{'='*60}")
    print("FEATURE ENGINEERING PIPELINE")
    print(f"  Symbols:    {symbols}")
    print(f"  Frequencies: {freqs}")
    print(f"  Features:   {feature_families}")
    print(f"  Input:      {args.input or args.tick_dir}")
    print(f"  DB path:    {args.db_path or '(none)'}")
    print(f"  Output:     {args.output}")
    print(f"{'='*60}")

    needs_ticks = 'microstructure' in feature_families

    # ── Phase 1: Load data ──
    print("\n--- Loading data ---")

    ohlcv_data: dict[str, pd.DataFrame] = {}
    tick_data: dict[str, pd.DataFrame] = {}

    if args.input:
        ohlcv_data = read_warehouse(args.input, symbols, args.db_path)
    else:
        # Legacy mode: read ticks and resample
        tick_data = load_ticks(args.tick_dir, symbols)
        for sym, ticks_df in tick_data.items():
            print(f"\n--- Resampling {sym} ---")
            for freq in freqs:
                ohlc = resample_ohlcv(ticks_df, freq)
                if ohlc.empty:
                    print(f"  [SKIP] {freq}: no OHLCV data")
                    continue
                ohlcv_data[f"{sym}_{freq}"] = ohlc
                ohlcv_data[f"{sym}_{freq}_ticks"] = ticks_df

    if not ohlcv_data:
        print("No data loaded. Aborting.")
        sys.exit(1)

    # If we got raw OHLCV per symbol (warehouse path), build per-frequency variants
    pure_ohlcv: dict[str, pd.DataFrame] = {}
    for key, df in ohlcv_data.items():
        if key.endswith('_ticks'):
            continue
        pure_ohlcv[key] = df

    # Organize: {symbol: {freq: DataFrame}} for warehouse input
    warehouse_mode = not bool(tick_data) and args.input is not None
    if warehouse_mode:
        # Flatten: each symbol has one base OHLCV; resample if needed
        ohlcv_per_sym: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            for key, df in ohlcv_data.items():
                if sym in key and not key.endswith('_ticks'):
                    ohlcv_per_sym[sym] = df
                    break

        by_sym_freq: dict[str, dict[str, pd.DataFrame]] = {}
        for sym, df in ohlcv_per_sym.items():
            by_sym_freq[sym] = {}
            df_ts = (
                df.set_index('timestamp')
                if 'timestamp' in df.columns
                and not isinstance(df.index, pd.DatetimeIndex)
                else df
            )
            df_ts = df_ts.sort_index()
            # Only aggregate columns that actually exist in the dataframe
            agg_map = {}
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    agg_map[col] = 'first' if col == 'open' else ('max' if col == 'high' else ('min' if col == 'low' else ('last' if col == 'close' else 'sum')))
            # Set proper aggregation for OHLCV
            agg_map = {}
            if 'open' in df.columns:   agg_map['open'] = 'first'
            if 'high' in df.columns:   agg_map['high'] = 'max'
            if 'low' in df.columns:    agg_map['low'] = 'min'
            if 'close' in df.columns:  agg_map['close'] = 'last'
            if 'volume' in df.columns: agg_map['volume'] = 'sum'
            if 'tick_count' in df.columns:   agg_map['tick_count'] = 'sum'
            if 'spread_mean' in df.columns:  agg_map['spread_mean'] = 'mean'
            for freq in freqs:
                resampled = df_ts.resample(freq).agg(agg_map) if agg_map else df_ts.resample(freq).first()
                # Drop rows with missing OHLC
                resampled = resampled.dropna(subset=['open', 'high', 'low', 'close'])
                if not resampled.empty:
                    by_sym_freq[sym][freq] = resampled
                    print(f"  [OK] {sym} @ {freq}: {len(resampled)} bars")
    else:
        by_sym_freq: dict[str, dict[str, pd.DataFrame]] = {}
        for key, df in ohlcv_data.items():
            if key.endswith('_ticks'):
                continue
            parts = key.rsplit('_', 1)
            if len(parts) == 2:
                sym, freq = parts
                if sym in symbols:
                    if sym not in by_sym_freq:
                        by_sym_freq[sym] = {}
                    by_sym_freq[sym][freq] = df

    if not by_sym_freq:
        print("No OHLCV data available. Aborting.")
        sys.exit(1)

    # ── Phase 2: Compute features ──
    print("\n--- Computing features ---")
    all_features: dict[str, pd.DataFrame] = {}

    for sym in symbols:
        if sym not in by_sym_freq:
            continue

        for freq in freqs:
            if freq not in by_sym_freq.get(sym, {}):
                continue

            ohlc = by_sym_freq[sym][freq].copy()
            key = f"{sym}_{freq}"
            print(f"\n--- {key} ---")

            features = pd.DataFrame(index=ohlc.index)

            # V1 features (always computed, merged into ohlc for downstream use)
            if 'v1' in feature_families:
                v1 = compute_features(ohlc)
                for col in v1.columns:
                    features[col] = v1[col]
                    ohlc[col] = v1[col]  # also add to ohlc for downstream functions
                print(f"  [V1] {_feature_summary(v1)}")

            # Session features
            if 'session' in feature_families:
                session_feats = compute_session_features(ohlc, sym)
                for col in session_feats.columns:
                    if col not in features.columns:
                        features[col] = session_feats[col]
                print(f"  [Session] {_feature_summary(session_feats)}")

            # Regime features
            if 'regime' in feature_families:
                regime_feats = compute_regime_features(ohlc)
                for col in regime_feats.columns:
                    if col not in features.columns:
                        features[col] = regime_feats[col]
                print(f"  [Regime] {_feature_summary(regime_feats)}")

            # Microstructure features
            if 'microstructure' in feature_families:
                sym_ticks = (
                    tick_data.get(sym)
                    if tick_data
                    else None
                )
                if sym_ticks is not None and not sym_ticks.empty:
                    micro_feats = compute_microstructure_features(ohlc, sym_ticks, freq)
                    for col in micro_feats.columns:
                        if col not in features.columns:
                            features[col] = micro_feats[col]
                    print(f"  [Microstructure] {_feature_summary(micro_feats)}")
                else:
                    print(f"  [SKIP] Microstructure: no tick data for {sym}")

            # Cross-asset features
            if 'cross_asset' in feature_families:
                cross_feats = compute_cross_asset_features(
                    ohlc, by_sym_freq, sym, freq
                )
                for col in cross_feats.columns:
                    if col not in features.columns:
                        features[col] = cross_feats[col]
                cross_new = [c for c in cross_feats.columns if c not in ohlc.columns]
                print(f"  [Cross-asset] {_feature_summary(cross_feats)}")

            features = features.dropna(how='all')
            if features.empty:
                print(f"  [SKIP] {key}: no features after dropna")
                continue

            features['symbol'] = sym
            features['freq'] = freq

            _log_feature_nan(features, key)

            if args.validate:
                validate_features(features, key)

            all_features[key] = features
            print(f"  [OK] {key}: {len(features)} rows, {len(features.columns)} cols")

    # ── Phase 3: Save ──
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
        cols = [
            c for c in df.columns if c not in ('symbol', 'freq', 'target', 'target_return')
        ]
        print(f"  {key}: {len(df)} rows, {len(cols)} features")
    print(f"  Output: {args.output}")
    print(f"{'='*60}")

    # Save run record
    record = {
        "run_time_utc": datetime.now(UTC).isoformat(),
        "symbols": symbols,
        "frequencies": freqs,
        "feature_families": feature_families,
        "input": args.input or args.tick_dir,
        "db_path": args.db_path,
        "features_per_dataset": {
            k: len([c for c in v.columns if c not in ('symbol', 'freq', 'target', 'target_return')])
            for k, v in all_features.items()
        },
        "total_rows": sum(len(v) for v in all_features.values()),
        "output_files": feature_files,
    }
    with open(os.path.join(args.output, "feature_run_record.json"), 'w') as f:
        json.dump(record, f, indent=2)
    print(f"  Run record: {os.path.join(args.output, 'feature_run_record.json')}")


if __name__ == "__main__":
    main()
