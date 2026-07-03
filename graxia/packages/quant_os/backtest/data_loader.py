"""
Data Loader - Load historical OHLCV data for backtesting

Supports:
- CSV files (Yahoo Finance format, generic OHLCV)
- Arrow/Feather format (columnar, high-performance)
- MT5 terminal (if running)
- Generated sample data for testing
"""

import csv
import os
from datetime import date, datetime

import pandas as pd


def load_csv_data(
    file_path: str,
    date_column: str = "Date",
    date_format: str = "%Y-%m-%d",
    timezone: str = "UTC",
) -> tuple[dict[str, list], list[datetime]]:
    """
    Load OHLCV data from a CSV file.

    Supports Yahoo Finance format:
        Date,Open,High,Low,Close,Volume

    Args:
        file_path: Path to CSV file
        date_column: Name of date column
        date_format: strftime format for parsing dates

    Returns:
        Tuple of (ohlcv_dict, timestamps)
    """
    timestamps = []
    data = {"open": [], "high": [], "low": [], "close": [], "volume": []}

    with open(file_path, newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            # Parse timestamp
            try:
                ts = datetime.strptime(row[date_column], date_format)
            except (KeyError, ValueError):
                continue

            # Parse OHLCV — all-or-nothing: timestamp is only appended when
            # all 5 price fields parse successfully, preventing length mismatch.
            try:
                o = float(row.get("Open", row.get("open", 0)))
                h = float(row.get("High", row.get("high", 0)))
                lo = float(row.get("Low", row.get("low", 0)))
                c = float(row.get("Close", row.get("close", 0)))
                v = float(row.get("Volume", row.get("volume", 0)))
            except (ValueError, KeyError):
                continue

            # Validate OHLCV consistency (all positive, high >= low)
            if o <= 0 or h <= 0 or lo <= 0 or c <= 0 or h < lo:
                continue

            timestamps.append(ts)
            data["open"].append(o)
            data["high"].append(h)
            data["low"].append(lo)
            data["close"].append(c)
            data["volume"].append(v)

    if not data["close"]:
        raise ValueError(f"No valid data found in {file_path}")

    return data, timestamps


def load_yahoo_csv(symbol: str, data_dir: str = "./data") -> tuple[dict[str, list], list[datetime]]:
    """
    Load Yahoo Finance CSV data.

    Expected file: {data_dir}/{symbol}.csv

    Args:
        symbol: Trading symbol (e.g., "EURUSD=X")
        data_dir: Directory containing CSV files

    Returns:
        Tuple of (ohlcv_dict, timestamps)
    """
    file_path = os.path.join(data_dir, f"{symbol}.csv")
    return load_csv_data(file_path)


def load_mt5_data(
    symbol: str,
    timeframe: str = "M15",
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[dict[str, list], list[datetime]]:
    """
    Load historical data from MetaTrader 5 terminal.

    Args:
        symbol: Trading symbol (e.g., "EURUSD")
        timeframe: Timeframe string (M1, M5, M15, H1, H4, D1)
        start_date: Start date filter
        end_date: End date filter

    Returns:
        Tuple of (ohlcv_dict, timestamps)
    """
    try:
        import MetaTrader5 as mt5
    except ImportError:
        raise ImportError("MetaTrader5 package not installed. Run: pip install MetaTrader5") from None

    if not mt5.initialize():
        raise ConnectionError("Failed to initialize MT5 terminal")

    # Map timeframe string to MT5 constant
    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
        "W1": mt5.TIMEFRAME_W1,
        "MN1": mt5.TIMEFRAME_MN1,
    }

    tf = tf_map.get(timeframe.upper(), mt5.TIMEFRAME_M15)

    # Get data
    rates = mt5.copy_rates_range(symbol, tf, start_date, end_date)

    mt5.shutdown()

    if rates is None or len(rates) == 0:
        raise ValueError(f"No data returned from MT5 for {symbol}")

    # Convert to our format
    timestamps = [datetime.fromtimestamp(r["time"]) for r in rates]
    data = {
        "open": [float(r["open"]) for r in rates],
        "high": [float(r["high"]) for r in rates],
        "low": [float(r["low"]) for r in rates],
        "close": [float(r["close"]) for r in rates],
        "volume": [float(r["tick_volume"]) for r in rates],
    }

    return data, timestamps


def generate_sample_data(
    bars: int = 10000,
    base_price: float = 1.0850,
    volatility: float = 0.001,
    trend: float = 0.0,
    seed: int = 42,
) -> tuple[dict[str, list], list[datetime]]:
    """
    Generate synthetic OHLCV data for testing.

    Args:
        bars: Number of bars to generate
        base_price: Starting price
        volatility: Price volatility (std dev per bar)
        trend: Upward/downward drift per bar
        seed: Random seed for reproducibility

    Returns:
        Tuple of (ohlcv_dict, timestamps)
    """
    import random

    random.seed(seed)

    timestamps = []
    data = {"open": [], "high": [], "low": [], "close": [], "volume": []}

    price = base_price
    start_date = datetime(2020, 1, 1)

    for i in range(bars):
        ts = start_date + __import__("datetime").timedelta(hours=i)
        timestamps.append(ts)

        # Generate OHLCV with random walk
        open_price = price
        change = random.gauss(trend, volatility)
        close_price = open_price * (1 + change)

        # High/low
        intrabar_vol = volatility * 0.5
        high_price = max(open_price, close_price) * (1 + abs(random.gauss(0, intrabar_vol)))
        low_price = min(open_price, close_price) * (1 - abs(random.gauss(0, intrabar_vol)))

        # Volume (random with some pattern)
        base_volume = 1000000
        volume = base_volume * (1 + random.gauss(0, 0.3))

        data["open"].append(round(open_price, 5))
        data["high"].append(round(high_price, 5))
        data["low"].append(round(low_price, 5))
        data["close"].append(round(close_price, 5))
        data["volume"].append(max(0, volume))

        price = close_price

    return data, timestamps


def download_and_save_yahoo(
    symbol: str,
    start_date: str,
    end_date: str,
    output_dir: str = "./data",
) -> str:
    """
    Download data from Yahoo Finance and save as CSV.

    Args:
        symbol: Yahoo Finance symbol (e.g., "EURUSD=X")
        start_date: Start date "YYYY-MM-DD"
        end_date: End date "YYYY-MM-DD"
        output_dir: Directory to save CSV

    Returns:
        Path to saved CSV file
    """
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError("yfinance package not installed. Run: pip install yfinance") from None

    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start_date, end=end_date)

    if df.empty:
        raise ValueError(f"No data downloaded for {symbol}")

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{symbol.replace('=', '_')}.csv")
    df.to_csv(output_path)

    return output_path


# ---------------------------------------------------------------------------
# Arrow / Feather support
# ---------------------------------------------------------------------------

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def _require_pyarrow():
    """Import pyarrow or raise a clear error."""
    try:
        import pyarrow  # noqa: F401

        return pyarrow
    except ImportError:
        raise ImportError(
            "pyarrow is required for Arrow/Feather support. " "Install it with: pip install pyarrow"
        ) from None


def _validate_ohlcv_schema(df: pd.DataFrame) -> None:
    """Validate that a DataFrame conforms to the expected OHLCV schema.

    Checks:
    - All required columns are present
    - Price columns are numeric (float or int)
    - Volume column is numeric
    - DatetimeIndex is present and sorted ascending
    """
    missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required OHLCV columns: {missing}")

    for col in OHLCV_COLUMNS:
        if not pd.api.types.is_numeric_dtype(df[col]):
            raise ValueError(f"Column '{col}' must be numeric, got {df[col].dtype}")

    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(f"Index must be DatetimeIndex, got {type(df.index).__name__}")

    if not df.index.is_monotonic_increasing:
        raise ValueError("Index must be sorted in ascending order")


def load_arrow(path: str) -> pd.DataFrame:
    """Load an Arrow IPC or Feather file into a DataFrame.

    Both .arrow (IPC stream/file) and .feather formats are supported.
    The returned DataFrame has a DatetimeIndex and OHLCV columns validated.

    Args:
        path: Path to .arrow or .feather file.

    Returns:
        DataFrame with DatetimeIndex and columns: open, high, low, close, volume.
    """
    _require_pyarrow()

    ext = os.path.splitext(path)[1].lower()
    if ext == ".feather" or ext == ".arrow":
        df = pd.read_feather(path)
    elif ext == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_feather(path)

    # Restore DatetimeIndex if a datetime column exists (was reset before write)
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df.set_index(col, inplace=True)
            df.index.name = None
            break

    _validate_ohlcv_schema(df)
    return df


def to_arrow(df: pd.DataFrame, path: str) -> None:
    """Export a DataFrame to Arrow IPC format (.arrow) or Feather (.feather).

    The DataFrame must have a DatetimeIndex and the standard OHLCV columns.

    Args:
        df: DataFrame with DatetimeIndex and OHLCV columns.
        path: Destination path. Extension determines format:
              .arrow  -> Feather IPC file (default if no extension)
              .feather -> Feather IPC file
    """
    _require_pyarrow()
    _validate_ohlcv_schema(df)

    ext = os.path.splitext(path)[1].lower()
    if ext == ".feather":
        df.reset_index().to_feather(path)
    else:
        # Default to .feather (Feather v2 / IPC file)
        out = path if ext else f"{path}.feather"
        df.reset_index().to_feather(out)
