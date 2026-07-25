"""
Data Loader - Load historical OHLCV data for backtesting

Supports:
- CSV files (Yahoo Finance format, generic OHLCV)
- Arrow/Feather format (columnar, high-performance)
- MT5 terminal (if running)
- Generated sample data for testing
"""

import csv
import logging
import os
import re
import sys
from datetime import date, datetime, timedelta

import pandas as pd

logger = logging.getLogger(__name__)


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
    import random as _random_mod

    rng = _random_mod.Random(seed)

    timestamps = []
    data = {"open": [], "high": [], "low": [], "close": [], "volume": []}

    price = base_price
    start_date = datetime(2020, 1, 1)

    for i in range(bars):
        ts = start_date + timedelta(hours=i)
        timestamps.append(ts)

        # Generate OHLCV with random walk
        open_price = price
        change = rng.gauss(trend, volatility)
        close_price = open_price * (1 + change)

        # High/low
        intrabar_vol = volatility * 0.5
        high_price = max(open_price, close_price) * (1 + abs(rng.gauss(0, intrabar_vol)))
        low_price = min(open_price, close_price) * (1 - abs(rng.gauss(0, intrabar_vol)))

        # Volume (random with some pattern)
        base_volume = 1000000
        volume = base_volume * (1 + rng.gauss(0, 0.3))

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


# ---------------------------------------------------------------------------
# Unified load_ohlcv() dispatcher — used by ml.labeling.label_from_source(),
# which dynamically file-imports this module (bypassing normal package
# import machinery, see that function's docstring) and calls
# ``_dl.load_ohlcv(symbol=..., timeframe=..., sources=[...], **loader_kwargs)``.
# ---------------------------------------------------------------------------


def _graxia_repo_root() -> str:
    """Filesystem root above the ``graxia`` namespace package.

    Computed from this file's own ``__file__`` (not from the caller's sys.path
    state) so it resolves correctly whether this module was imported normally
    (``backtest.data_loader``) or file-loaded via importlib with no parent
    package (as ``ml.labeling.label_from_source`` does).

    backtest/data_loader.py -> quant_os -> packages -> graxia -> repo root.
    """
    quant_os_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.dirname(os.path.dirname(quant_os_root))


def _normalize_timeframe_for_duckdb(timeframe: str) -> str:
    """Map 'H1'/'M15'/'D1'-style timeframes to the lowercase 'Nh'/'Nm'/'Nd'
    convention data/market_data.duckdb's flat ``ohlcv`` table actually stores
    (see scripts/bootstrap_history.py, which writes ``timeframe="1h"``).
    Falls back to a plain lowercase of the input for anything else.
    """
    m = re.match(r"^([HMD])(\d+)$", timeframe.strip(), re.IGNORECASE)
    if not m:
        return timeframe.lower()
    unit, n = m.group(1).upper(), m.group(2)
    suffix = {"H": "h", "M": "m", "D": "d"}[unit]
    return f"{n}{suffix}"


def _load_ohlcv_duckdb(symbol: str, timeframe: str, **kwargs) -> pd.DataFrame:
    """Query the flat ``ohlcv`` table in data/market_data.duckdb.

    Accepts an optional ``duckdb_path`` kwarg; otherwise resolves the path via
    core.config.get_config().duckdb_path (same source scripts/bootstrap_history.py
    uses), falling back to the DUCKDB_PATH env var / the documented default.
    """
    import duckdb

    db_path = kwargs.get("duckdb_path")
    if not db_path:
        try:
            root = _graxia_repo_root()
            if root not in sys.path:
                sys.path.insert(0, root)
            from graxia.packages.quant_os.core.config import get_config

            db_path = get_config().duckdb_path
        except Exception:
            db_path = None
    db_path = db_path or os.getenv("DUCKDB_PATH", "data/market_data.duckdb")

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"duckdb file not found: {db_path}")

    tf = _normalize_timeframe_for_duckdb(timeframe)
    con = duckdb.connect(db_path, read_only=True)
    try:
        tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
        if "ohlcv" not in tables:
            raise ValueError(f"no 'ohlcv' table in {db_path}")
        df = con.execute(
            "SELECT time, open, high, low, close, volume, symbol "
            "FROM ohlcv WHERE symbol = ? AND timeframe = ? ORDER BY time",
            [symbol, tf],
        ).fetchdf()
    finally:
        con.close()

    if df.empty:
        raise ValueError(f"no duckdb OHLCV rows for {symbol}/{timeframe} (normalized '{tf}') in {db_path}")
    return df


def _dedupe_warehouse_ohlcv(df: pd.DataFrame, *, symbol: str, timeframe: str) -> pd.DataFrame:
    """Drop exact-duplicate rows returned by a hive-partitioned warehouse read.

    Known ingestion bug (out of scope to fix at the source here, per project
    decision): the same underlying file/rows can land in more than one
    overlapping hive partition, so a single glob-registered view query can
    return byte-identical rows several times over (confirmed on real
    XAUUSD/H1 data: 300,000 rows collapsing to 50,000 unique rows, i.e. each
    row repeated exactly 6x, all columns identical). Duplicate timestamps
    straddling a purge/embargo split boundary would leak test-fold
    information into the training fold, inflating apparent OOS performance.

    This is a defensive load-time fix: drop full-row duplicates (safe --
    never discards genuinely different data), then, if any duplicate
    timestamps remain afterward (rows that share a time but disagree on some
    other column -- a different, not-yet-seen problem), keep the first
    occurrence and log loudly rather than silently feeding ambiguous rows
    into training/evaluation.
    """
    if "time" not in df.columns:
        return df

    before = len(df)
    df = df.drop_duplicates(subset=list(df.columns), keep="first")

    remaining_dupe_ts = int(df.duplicated(subset=["time"], keep=False).sum())
    if remaining_dupe_ts > 0:
        logger.warning(
            "warehouse_ohlcv_non_identical_duplicate_timestamps: symbol=%s timeframe=%s rows=%d",
            symbol,
            timeframe,
            remaining_dupe_ts,
        )
        df = df.drop_duplicates(subset=["time"], keep="first")

    df = df.reset_index(drop=True)
    dropped = before - len(df)
    if dropped > 0:
        logger.warning(
            "warehouse_ohlcv_duplicate_rows_dropped: symbol=%s timeframe=%s dropped=%d kept=%d",
            symbol,
            timeframe,
            dropped,
            len(df),
        )
    return df


def _load_ohlcv_warehouse(symbol: str, timeframe: str, **kwargs) -> pd.DataFrame:
    """Query the Parquet-backed warehouse via data.warehouse_loader.Warehouse.

    Registers the hive-partitioned glob view for symbol/timeframe, then reads
    it. Accepts optional ``warehouse_db_path``, ``start_date``, ``end_date``
    kwargs. Deduplicates exact-duplicate rows before returning (see
    ``_dedupe_warehouse_ohlcv`` docstring) -- a partition-ingestion bug can
    otherwise return the same row several times over.
    """
    root = _graxia_repo_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    from graxia.packages.quant_os.data.warehouse_loader import Warehouse

    db_path = kwargs.get("warehouse_db_path", "data/warehouse/quantos.duckdb")
    wh = Warehouse(db_path=db_path)
    try:
        wh.register_ohlcv_glob(symbol, timeframe)
        df = wh.get_ohlcv(
            symbol,
            timeframe,
            start=kwargs.get("start_date"),
            end=kwargs.get("end_date"),
        )
    finally:
        wh.close()

    if df.empty:
        raise ValueError(f"no warehouse OHLCV rows for {symbol}/{timeframe} in {db_path}")

    df = _dedupe_warehouse_ohlcv(df, symbol=symbol, timeframe=timeframe)
    return df


def _load_ohlcv_csv(symbol: str, timeframe: str, **kwargs) -> pd.DataFrame:
    """Load OHLCV from local files: Arrow/Feather first (schema-validated),
    then a raw CSV via load_csv_data(). Accepts optional ``data_dir`` and
    ``csv_path`` kwargs.
    """
    data_dir = kwargs.get("data_dir", "./data")
    for ext in (".feather", ".arrow", ".parquet"):
        path = os.path.join(data_dir, f"{symbol}_{timeframe}{ext}")
        if os.path.exists(path):
            return load_arrow(path)

    csv_path = kwargs.get("csv_path") or os.path.join(data_dir, f"{symbol}.csv")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"no CSV/Arrow OHLCV file found for {symbol}/{timeframe} under {data_dir}")

    data, timestamps = load_csv_data(csv_path)
    df = pd.DataFrame(data, index=pd.DatetimeIndex(timestamps))
    return df


def load_ohlcv(
    symbol: str,
    timeframe: str = "H1",
    sources: list[str] | None = None,
    **kwargs,
) -> pd.DataFrame:
    """Dispatch OHLCV loading across data sources, in order, returning the
    first source that yields real rows.

    This is the function ``ml.labeling.label_from_source()`` dynamically
    file-imports and calls — see that function's docstring for the "auto"
    source order (``["duckdb", "warehouse", "csv"]``).

    Args:
        symbol: Trading symbol (e.g. "XAUUSD").
        timeframe: Bar timeframe, e.g. "H1", "M15", "D1".
        sources: Ordered source names to try: "duckdb", "warehouse", "csv".
            Defaults to all three, in that order.
        **kwargs: Passed through to the per-source loader (e.g. ``duckdb_path``,
            ``warehouse_db_path``, ``data_dir``, ``csv_path``, ``start_date``,
            ``end_date``).

    Returns:
        DataFrame with at least [open, high, low, close] columns.

    Raises:
        RuntimeError: If every source in ``sources`` fails or returns empty.
    """
    if sources is None:
        sources = ["duckdb", "warehouse", "csv"]

    dispatch = {
        "duckdb": _load_ohlcv_duckdb,
        "warehouse": _load_ohlcv_warehouse,
        "csv": _load_ohlcv_csv,
    }

    errors: list[str] = []
    for src in sources:
        loader = dispatch.get(src)
        if loader is None:
            errors.append(f"{src}: unknown source")
            continue
        try:
            df = loader(symbol, timeframe, **kwargs)
        except Exception as exc:  # noqa: BLE001 — try the next source instead of aborting
            errors.append(f"{src}: {exc}")
            continue
        if df is not None and len(df) > 0:
            return df
        errors.append(f"{src}: empty result")

    raise RuntimeError(
        f"load_ohlcv: all sources failed for symbol={symbol!r} timeframe={timeframe!r}: " + "; ".join(errors)
    )
