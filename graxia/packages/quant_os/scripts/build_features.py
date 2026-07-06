"""
Feature Generation Script — Build features from CSV data for walk-forward validation.

Generates technical indicators and creates target labels for ML models.
Saves to parquet format in artifacts/features_v2/.

Usage:
    python scripts/build_features.py --symbol XAUUSD --freq 1min
    python scripts/build_features.py --symbol XAUUSD --freq H1
    python scripts/build_features.py --all  # Process all instruments
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.features import build_features as canonical_build_features  # noqa: E402

# ── Constants ───────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "data"
OUT_DIR = Path(__file__).parent.parent / "artifacts" / "features_v2"

# Frequency mapping
FREQ_MAP = {
    "1min": "M1",
    "M1": "M1",
    "5min": "M5",
    "M5": "M5",
    "15min": "M15",
    "M15": "M15",
    "30min": "M30",
    "M30": "M30",
    "1h": "H1",
    "H1": "H1",
    "4h": "H4",
    "H4": "H4",
    "1d": "D1",
    "D1": "D1",
}

# Target parameters
TARGET_FORWARD_BARS = 5  # Bars to look forward for target
TARGET_THRESHOLD = 0.001  # 0.1% threshold for binary classification


def load_csv(symbol: str, freq: str) -> pd.DataFrame:
    """Load CSV data file."""
    csv_freq = FREQ_MAP.get(freq, freq)
    filepath = DATA_DIR / f"{symbol}_{csv_freq}.csv"

    if not filepath.exists():
        raise FileNotFoundError(f"Data file not found: {filepath}")

    df = pd.read_csv(filepath)

    # Standardize column names
    df.columns = [c.lower() for c in df.columns]

    # Parse timestamp
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")
    elif "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
        df = df.set_index("time")

    # Ensure OHLCV columns exist
    required = ["open", "high", "low", "close"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing column: {col}")

    # Add volume if missing
    if "volume" not in df.columns:
        df["volume"] = 0.0

    print(f"  Loaded {len(df)} bars from {filepath.name}")
    return df


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """DEPRECATED: Use core.features.build_features instead."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """DEPRECATED: Use core.features.build_features instead."""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram


def compute_bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    """DEPRECATED: Use core.features.build_features instead."""
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return upper, sma, lower


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """DEPRECATED: Use core.features.build_features instead."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute technical features using canonical FeatureEngineer.

    ponytail: delegates to core.features.build_features — single source of truth.
    """
    return canonical_build_features(df)


def create_target(
    df: pd.DataFrame, forward_bars: int = 5, threshold: float = 0.001, freq: str = "H1", symbol: str = ""
) -> pd.DataFrame:
    """Create target labels for ML training."""
    result = df.copy()

    # Adjust threshold based on instrument and frequency
    if freq == "M1":
        if symbol in ["XAUUSD", "XAGUSD"]:
            threshold = 0.0001  # 0.01% for metals
        elif symbol in ["NAS100", "US30"]:
            threshold = 0.00005  # 0.005% for indices
        else:
            threshold = 0.0001  # 0.01% for forex
    elif freq == "H1":
        threshold = 0.0005  # 0.05% for H1
    else:
        threshold = 0.001  # 0.1% for D1

    # Forward return
    result["target_return"] = df["close"].pct_change(forward_bars).shift(-forward_bars)

    # Binary target: 1 = up, 0 = down/flat
    result["target"] = (result["target_return"] > threshold).astype(int)

    # Three-class target: 1 = up, 0 = flat, -1 = down
    result["target_3class"] = np.where(
        result["target_return"] > threshold, 1, np.where(result["target_return"] < -threshold, -1, 0)
    )

    return result


def build_features(symbol: str, freq: str, output_dir: Path | None = None) -> Path:
    """Build features for a single symbol/freq combination."""
    if output_dir is None:
        output_dir = OUT_DIR

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"Building features: {symbol} @ {freq}")
    print(f"{'='*60}")

    # Load data
    df = load_csv(symbol, freq)

    # Compute features
    features = compute_features(df)

    # Create target
    features = create_target(features, freq=freq, symbol=symbol)

    # Add metadata
    features["symbol"] = symbol
    features["freq"] = freq

    # Drop rows with NaN (from rolling calculations)
    initial_len = len(features)
    features = features.dropna()
    print(f"  Dropped {initial_len - len(features)} rows with NaN values")

    # Save to parquet
    csv_freq = FREQ_MAP.get(freq, freq)
    output_path = output_dir / f"features_{symbol}_{csv_freq}.parquet"
    features.to_parquet(output_path)

    print(f"  Saved: {output_path}")
    print(f"  Shape: {features.shape}")
    print(f"  Date range: {features.index[0]} to {features.index[-1]}")

    return output_path


def main():
    parser = argparse.ArgumentParser(description="Build features for walk-forward validation")
    parser.add_argument("--symbol", type=str, help="Symbol to process (e.g., XAUUSD)")
    parser.add_argument("--freq", type=str, default="1min", help="Frequency (1min, H1, D1)")
    parser.add_argument("--all", action="store_true", help="Process all instruments")
    parser.add_argument("--output", type=str, help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output) if args.output else OUT_DIR

    if args.all:
        # Process all instruments
        instruments = [
            "AUDUSD",
            "BTCUSD",
            "ETHUSD",
            "EURUSD",
            "GBPUSD",
            "NAS100",
            "NZDUSD",
            "US30",
            "USDCAD",
            "USDCHF",
            "USDJPY",
            "XAGUSD",
            "XAUUSD",
            "XPDUSD",
            "XPTUSD",
        ]
        freqs = ["M1", "H1", "D1"]  # Now we have M1 data from MT5

        print("=" * 60)
        print("Building features for ALL instruments")
        print("=" * 60)

        results = []
        for sym in instruments:
            for freq in freqs:
                try:
                    path = build_features(sym, freq, output_dir)
                    results.append({"symbol": sym, "freq": freq, "status": "OK", "path": str(path)})
                except Exception as e:
                    print(f"  ERROR: {e}")
                    results.append({"symbol": sym, "freq": freq, "status": "ERROR", "error": str(e)})

        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        ok_count = sum(1 for r in results if r["status"] == "OK")
        error_count = sum(1 for r in results if r["status"] == "ERROR")
        print(f"Success: {ok_count}")
        print(f"Errors: {error_count}")

    elif args.symbol:
        # Process single symbol
        build_features(args.symbol, args.freq, output_dir)

    else:
        print("Error: Specify --symbol or --all")
        sys.exit(1)


if __name__ == "__main__":
    main()
