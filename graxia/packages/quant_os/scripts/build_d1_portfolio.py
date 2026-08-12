"""
Build D1/H4 multi-asset portfolio dataset.

Aggregates M15 OHLCV to D1/H4, joins with:
- yfinance cross-asset (DXY, TLT, VIX, oil, silver)
- FRED macro (real yields, treasury spreads)
- COT weekly positioning
- Swap rates from broker (if available)

Output: artifacts/portfolio/d1_multi_asset.parquet

Usage:
    python scripts/build_d1_portfolio.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
ARTIFACTS = BASE / "artifacts"
DATA_DIR = BASE / "data" / "market_data"
OUT_DIR = ARTIFACTS / "portfolio"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── M15 sources ──────────────────────────────────────────────────────────────

M15_SOURCES = {
    "XAUUSD": ARTIFACTS / "features_v3" / "features_v3_mega_XAUUSD_15min.parquet",
    "EURUSD": ARTIFACTS / "features_v3" / "features_v3_EURUSD_M15.parquet",
    "GBPUSD": ARTIFACTS / "features_v2" / "features_v2_GBPUSD_15min.parquet",
    "BTCUSD": ARTIFACTS / "features_v3" / "features_v3_BTCUSD_M15.parquet",
    "ETHUSD": ARTIFACTS / "features_v3" / "features_v3_ETHUSD_M15.parquet",
}


def load_m15_ohlcv(symbol: str, path: Path) -> pd.DataFrame:
    """Load M15 OHLCV from parquet, normalize index."""
    if not path.exists():
        print(f"  SKIP {symbol}: {path.name} not found")
        return pd.DataFrame()

    df = pd.read_parquet(path)

    # Normalize datetime index
    if "datetime" in df.columns:
        df = df.set_index("datetime")
    df.index = pd.to_datetime(df.index, utc=True, errors="coerce")
    df = df[~df.index.isna()]
    df = df.sort_index()

    # Validate: skip if dates are before 2000 (broken index)
    if df.empty or df.index.min().year < 2000:
        print(f"  SKIP {symbol}: broken datetime index")
        return pd.DataFrame()

    # Keep only OHLCV
    keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[keep].copy()

    print(f"  {symbol}: {len(df)} M15 bars, {df.index.min()} to {df.index.max()}")
    return df


def aggregate_ohlcv(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Aggregate OHLCV from M15 to D1 or H4."""
    if df.empty:
        return df
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }
    if "volume" in df.columns:
        agg["volume"] = "sum"

    available_agg = {k: v for k, v in agg.items() if k in df.columns}
    resampled = df.resample(freq).agg(available_agg).dropna(subset=["open"])
    return resampled


def load_yfinance_daily(symbol: str, filename: str) -> pd.DataFrame:
    """Load daily data from yfinance CSV."""
    path = DATA_DIR / "yfinance" / filename
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.sort_index()
    # Standardize column names
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]
    if "adj_close" in df.columns:
        df = df.rename(columns={"adj_close": "close"})
    return df


def load_fred(filename: str) -> pd.DataFrame:
    """Load FRED CSV data."""
    path = DATA_DIR / "fred" / filename
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True, errors="coerce")
    df = df[~df.index.isna()]
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]
    # FRED sometimes uses "." for missing values
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def load_cot(filename: str) -> pd.DataFrame:
    """Load COT weekly parquet."""
    path = DATA_DIR / "cot" / filename
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    if "report_date" in df.columns:
        df = df.set_index("report_date")
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def build_d1_dataset() -> pd.DataFrame:
    """Build unified D1 multi-asset dataset."""
    print("=== Building D1 Multi-Asset Dataset ===\n")

    # 1. Aggregate M15 to D1 for each symbol
    print("--- M15 to D1 Aggregation ---")
    d1_frames = {}
    for sym, path in M15_SOURCES.items():
        m15 = load_m15_ohlcv(sym, path)
        if not m15.empty:
            d1 = aggregate_ohlcv(m15, "D")
            d1 = d1.rename(columns={c: f"{sym}_{c}" for c in d1.columns})
            d1_frames[sym] = d1
            print(f"  {sym}: {len(d1)} D1 bars")

    # 2. Load yfinance daily data for missing symbols + cross-asset
    print("\n--- yfinance Daily Data ---")
    yf_symbols = {
        "EURUSD_YF": "EURUSD_X.csv",
        "GBPUSD_YF": "GBPUSD_X.csv",
        "USDJPY": "USDJPY_X.csv",
        "DXY": "DX-Y.NYB.csv",
        "VIX": "_VIX.csv",
        "TLT": "TLT.csv",
        "BTC_YF": "BTC-USD.csv",
        "ETH_YF": "ETH-USD.csv",
        "SILVER": "SI_F.csv",
        "OIL": "CL_F.csv",
        "GOLD_FUT": "GC_F.csv",
    }

    for label, filename in yf_symbols.items():
        df = load_yfinance_daily(label, filename)
        if not df.empty:
            # Only keep close for cross-asset
            if "close" in df.columns:
                series = df[["close"]].rename(columns={"close": f"{label}_close"})
                d1_frames[label] = series
                print(f"  {label}: {len(series)} daily bars")

    # 3. Load FRED macro data
    print("\n--- FRED Macro Data ---")
    fred_files = {
        "DFII10": "DFII10.csv",  # 10Y real yield
        "DGS10": "DGS10.csv",  # 10Y nominal yield
        "DGS2": "DGS2.csv",  # 2Y yield
        "BAA10Y": "BAA10Y.csv",  # Credit spread
    }

    for label, filename in fred_files.items():
        df = load_fred(filename)
        if not df.empty:
            col = df.columns[0] if len(df.columns) > 0 else "value"
            series = df[[col]].rename(columns={col: f"FRED_{label}"})
            d1_frames[label] = series
            print(f"  {label}: {len(series)} daily bars")

    # 4. Load COT data (weekly to forward-fill to daily)
    print("\n--- COT Weekly Data ---")
    cot = load_cot("gold_cot_weekly.parquet")
    if not cot.empty:
        # Keep key columns
        keep_cols = [
            c for c in cot.columns if any(k in c.lower() for k in ["net", "long", "short", "open_interest", "pct"])
        ]
        if keep_cols:
            cot_daily = cot[keep_cols[:10]].resample("D").ffill()
            cot_daily = cot_daily.rename(columns={c: f"COT_{c}" for c in cot_daily.columns})
            d1_frames["COT"] = cot_daily
            print(f"  COT gold: {len(cot_daily)} daily (forward-filled)")

    # 5. Merge all on datetime index
    print("\n--- Merging ---")
    if not d1_frames:
        print("ERROR: No data to merge")
        return pd.DataFrame()

    result = None
    for label, df in d1_frames.items():
        if result is None:
            result = df
        else:
            result = result.join(df, how="outer")

    if result is not None:
        result = result.sort_index()
        # Drop rows where all are NaN
        result = result.dropna(how="all")
        print(f"\nFinal dataset: {len(result)} rows, {len(result.columns)} columns")
        print(f"Date range: {result.index.min()} to {result.index.max()}")

    return result


def build_h4_dataset() -> pd.DataFrame:
    """Build H4 multi-asset dataset from M15 data."""
    print("\n=== Building H4 Multi-Asset Dataset ===")

    h4_frames = {}
    for sym, path in M15_SOURCES.items():
        m15 = load_m15_ohlcv(sym, path)
        if not m15.empty:
            h4 = aggregate_ohlcv(m15, "4h")
            h4 = h4.rename(columns={c: f"{sym}_{c}" for c in h4.columns})
            h4_frames[sym] = h4
            print(f"  {sym}: {len(h4)} H4 bars")

    if not h4_frames:
        return pd.DataFrame()

    result = None
    for label, df in h4_frames.items():
        if result is None:
            result = df
        else:
            result = result.join(df, how="outer")

    if result is not None:
        result = result.sort_index().dropna(how="all")
        print(f"\nH4 dataset: {len(result)} rows, {len(result.columns)} columns")

    return result


def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add TSM-relevant derived features."""
    if df.empty:
        return df

    # For each symbol with close data, add returns and momentum
    close_cols = [c for c in df.columns if c.endswith("_close")]
    for col in close_cols:
        prefix = col.replace("_close", "")
        # Returns
        df[f"{prefix}_ret_1d"] = df[col].pct_change(1)
        df[f"{prefix}_ret_5d"] = df[col].pct_change(5)
        df[f"{prefix}_ret_10d"] = df[col].pct_change(10)
        df[f"{prefix}_ret_20d"] = df[col].pct_change(20)
        df[f"{prefix}_ret_60d"] = df[col].pct_change(60)

        # Realized volatility (20-day)
        df[f"{prefix}_rvol_20d"] = df[f"{prefix}_ret_1d"].rolling(20).std() * np.sqrt(252)

        # Momentum signal: sign of 20d return
        df[f"{prefix}_tsm_signal"] = np.sign(df[f"{prefix}_ret_20d"])

    return df


def main():
    # Build D1
    d1 = build_d1_dataset()
    if not d1.empty:
        d1 = add_derived_features(d1)
        out_path = OUT_DIR / "d1_multi_asset.parquet"
        d1.to_parquet(out_path)
        print(f"\nSaved D1 dataset: {out_path}")
        print(f"  Rows: {len(d1)}, Columns: {len(d1.columns)}")
        print(f"  Date range: {d1.index.min()} to {d1.index.max()}")

    # Build H4
    h4 = build_h4_dataset()
    if not h4.empty:
        h4 = add_derived_features(h4)
        out_path = OUT_DIR / "h4_multi_asset.parquet"
        h4.to_parquet(out_path)
        print(f"\nSaved H4 dataset: {out_path}")
        print(f"  Rows: {len(h4)}, Columns: {len(h4.columns)}")


if __name__ == "__main__":
    main()
