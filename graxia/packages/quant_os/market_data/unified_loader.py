"""
Unified Market Data Loader — connects MT5 CSV, yfinance CSV, Polygon.

Single entry point for all backtesting and strategy data needs.
MT5 data: M15/H1/H4/D1 from Pepperstone (primary source for live symbols)
yfinance data: Equity/Crypto daily (supplementary)
Polygon data: US equities intraday (supplementary)

Usage:
    from market_data.unified_loader import MarketDataLoader

    loader = MarketDataLoader()
    df = loader.load("XAUUSD", "M15")           # MT5 M15, 2yr
    df = loader.load("EURUSD", "H1")            # MT5 H1, 10yr
    df = loader.load("AAPL", "1D")              # yfinance daily
    df = loader.load("BTCUSD", "M15")           # MT5 M15, 2yr
    dfs = loader.load_all(["XAUUSD", "EURUSD"], ["M15", "H1"])
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MT5_DIR = PROJECT_ROOT / "data" / "market" / "mt5"
YFINANCE_DIR = PROJECT_ROOT / "data" / "market"

# Symbol name mappings (MT5 name -> common name -> yfinance name)
MT5_TO_YFINANCE = {
    "XAUUSD": "GC=F",  # Gold futures
    "XAGUSD": "SI=F",  # Silver futures
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "US500": "SPY",
    "US30": "DIA",
    "NAS100": "QQQ",
    "GER40": "^GDAXI",
}

# Valid MT5 timeframes
MT5_TIMEFRAMES = {"M15", "H1", "H4", "D1"}


class MarketDataLoader:
    """Unified market data loader.

    Source priority:
    1. MT5 CSV (M15/H1/H4/D1) — from Pepperstone broker
    2. yfinance CSV (daily) — for equities/crypto not on MT5
    """

    def __init__(self, mt5_dir: Path | None = None, yf_dir: Path | None = None):
        self._mt5_dir = mt5_dir or MT5_DIR
        self._yf_dir = yf_dir or YFINANCE_DIR
        self._cache: dict[str, pd.DataFrame] = {}

    def load(
        self,
        symbol: str,
        timeframe: str,
        start: str | None = None,
        end: str | None = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Load OHLCV data for a symbol and timeframe.

        Args:
            symbol: Trading symbol (e.g., "XAUUSD", "EURUSD", "AAPL")
            timeframe: "M15", "H1", "H4", "D1" (MT5) or "1D" (yfinance)
            start: Optional start date filter "YYYY-MM-DD"
            end: Optional end date filter "YYYY-MM-DD"
            use_cache: Whether to use in-memory cache

        Returns:
            DataFrame with DatetimeIndex and columns: open, high, low, close, volume

        Raises:
            FileNotFoundError: If no data found for symbol/timeframe
        """
        cache_key = f"{symbol}_{timeframe}"

        if use_cache and cache_key in self._cache:
            df = self._cache[cache_key].copy()
        elif timeframe in MT5_TIMEFRAMES:
            df = self._load_mt5(symbol, timeframe)
        elif timeframe in ("1D", "daily"):
            df = self._load_yfinance_daily(symbol)
        else:
            raise ValueError(
                f"Unknown timeframe '{timeframe}'. "
                f"Use MT5 timeframes ({MT5_TIMEFRAMES}) or '1D' for yfinance daily."
            )

        if use_cache:
            self._cache[cache_key] = df.copy()

        # Apply date filters
        if start:
            df = df[df.index >= pd.Timestamp(start)]
        if end:
            df = df[df.index <= pd.Timestamp(end)]

        return df

    def load_all(
        self,
        symbols: list[str],
        timeframes: list[str],
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, dict[str, pd.DataFrame]]:
        """Load data for multiple symbols × timeframes.

        Returns:
            Nested dict: {symbol: {timeframe: DataFrame}}
        """
        result: dict[str, dict[str, Any]] = {}
        for sym in symbols:
            result[sym] = {}
            for tf in timeframes:
                try:
                    result[sym][tf] = self.load(sym, tf, start, end)
                except (FileNotFoundError, ValueError) as e:
                    logger.warning("No data for %s/%s: %s", sym, tf, e)
                    result[sym][tf] = pd.DataFrame()
        return result

    def load_for_strategy(
        self,
        symbols: list[str] | None = None,
        primary_tf: str = "M15",
        higher_tfs: list[str] | None = None,
    ) -> dict[str, dict[str, pd.DataFrame]]:
        """Load data formatted for strategy consumption.

        Returns data organized as {symbol: {timeframe: DataFrame}} for all
        configured symbols and timeframes.

        Args:
            symbols: List of symbols (default: EURUSD, GBPUSD, USDJPY, AUDUSD,
                     USDCAD, USDCHF, NZDUSD, XAUUSD)
            primary_tf: Primary timeframe (default: M15)
            higher_tfs: Higher timeframes (default: [H1, H4])
        """
        if symbols is None:
            symbols = [
                "EURUSD",
                "GBPUSD",
                "USDJPY",
                "AUDUSD",
                "USDCAD",
                "USDCHF",
                "NZDUSD",
                "XAUUSD",
            ]
        if higher_tfs is None:
            higher_tfs = ["H1", "H4"]

        all_tfs = [primary_tf] + higher_tfs
        return self.load_all(symbols, all_tfs)

    def list_available(self) -> dict[str, dict[str, dict]]:
        """List all available data.

        Returns:
            Dict: {timeframe: {symbol: {bars, start, end, size_kb}}}
        """
        result: dict[str, dict[str, dict]] = {}

        # MT5 data
        if self._mt5_dir.exists():
            for tf_dir in sorted(self._mt5_dir.iterdir()):
                if not tf_dir.is_dir():
                    continue
                tf = tf_dir.name
                result[tf] = {}
                for csv_file in sorted(tf_dir.glob("*.csv")):
                    sym = csv_file.stem
                    df = pd.read_csv(csv_file, usecols=["datetime"])
                    result[tf][sym] = {
                        "bars": len(df),
                        "start": df["datetime"].iloc[0],
                        "end": df["datetime"].iloc[-1],
                        "size_kb": csv_file.stat().st_size // 1024,
                    }

        # yfinance daily data
        for category in ["forex", "equity", "crypto"]:
            daily_dir = self._yf_dir / category / "1d"
            if daily_dir.exists():
                tf_key = f"yf_{category}_1D"
                result[tf_key] = {}
                for csv_file in sorted(daily_dir.glob("*.csv")):
                    sym = csv_file.stem
                    df = pd.read_csv(csv_file, usecols=["timestamp"])
                    result[tf_key][sym] = {
                        "bars": len(df),
                        "start": df["timestamp"].iloc[0],
                        "end": df["timestamp"].iloc[-1],
                        "size_kb": csv_file.stat().st_size // 1024,
                    }

        return result

    def _load_mt5(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Load from MT5 CSV files."""
        csv_path = self._mt5_dir / timeframe / f"{symbol}.csv"
        if not csv_path.exists():
            raise FileNotFoundError(
                f"MT5 data not found: {csv_path}. "
                f"Run: python scripts/download_mt5_all.py --symbols {symbol} --timeframes {timeframe}"
            )

        df = pd.read_csv(csv_path)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df.set_index("datetime", inplace=True)
        df = df[["open", "high", "low", "close", "volume"]]
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="first")]

        # Validate OHLCV
        df = df[(df["open"] > 0) & (df["high"] > 0) & (df["low"] > 0) & (df["close"] > 0)]
        df = df[df["high"] >= df["low"]]

        return df

    def _load_yfinance_daily(self, symbol: str) -> pd.DataFrame:
        """Load from yfinance CSV (daily data)."""
        # Try each category — check both {category}/1d/ and {category}/ paths
        for category in ["equity", "forex", "crypto"]:
            for subpath in [
                self._yf_dir / category / "1d" / f"{symbol}.csv",
                self._yf_dir / category / f"{symbol}.csv",
            ]:
                if subpath.exists():
                    df = pd.read_csv(subpath)
                    # Handle both 'timestamp' and 'Date' column names
                    time_col = "timestamp" if "timestamp" in df.columns else "Date"
                    df[time_col] = pd.to_datetime(df[time_col])
                    df.set_index(time_col, inplace=True)
                    df = df[["open", "high", "low", "close", "volume"]]
                    df = df.sort_index()
                    return df

        raise FileNotFoundError(
            f"yfinance daily data not found for {symbol}. " f"Run: python scripts/download_all_data.py --type equity"
        )

    def get_info(self, symbol: str, timeframe: str) -> dict:
        """Get metadata about available data without loading full DataFrame."""
        try:
            df = self.load(symbol, timeframe, use_cache=False)
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "bars": len(df),
                "start": str(df.index[0]),
                "end": str(df.index[-1]),
                "last_close": float(df["close"].iloc[-1]),
                "source": "mt5" if timeframe in MT5_TIMEFRAMES else "yfinance",
            }
        except FileNotFoundError:
            return {"symbol": symbol, "timeframe": timeframe, "bars": 0, "source": "not found"}

    def summary(self) -> str:
        """Print human-readable summary of all available data."""
        lines = ["=== Market Data Summary ===", ""]

        # MT5
        lines.append("--- MT5 (Pepperstone) ---")
        if self._mt5_dir.exists():
            for tf_dir in sorted(self._mt5_dir.iterdir()):
                if not tf_dir.is_dir():
                    continue
                csvs = list(tf_dir.glob("*.csv"))
                total_bars = sum(sum(1 for _ in open(f)) - 1 for f in csvs)
                syms = [f.stem for f in sorted(csvs)]
                lines.append(f"  {tf_dir.name}: {len(csvs)} symbols, {total_bars:,} bars")
                lines.append(f"    {', '.join(syms[:20])}")
        lines.append("")

        # yfinance
        lines.append("--- yfinance (Daily) ---")
        for category in ["forex", "equity", "crypto"]:
            daily_dir = self._yf_dir / category / "1d"
            if daily_dir.exists():
                csvs = list(daily_dir.glob("*.csv"))
                lines.append(f"  {category}: {len(csvs)} symbols")
        lines.append("")

        return "\n".join(lines)
