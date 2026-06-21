"""
Data Loader - Load historical OHLCV data for backtesting

Supports:
- CSV files (Yahoo Finance format, generic OHLCV)
- MT5 terminal (if running)
- Generated sample data for testing
"""

from datetime import datetime, date
from typing import Dict, List, Optional, Tuple
import csv
import os


def load_csv_data(
    file_path: str,
    date_column: str = "Date",
    date_format: str = "%Y-%m-%d",
    timezone: str = "UTC",
) -> Tuple[Dict[str, List], List[datetime]]:
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
    
    with open(file_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            # Parse timestamp
            try:
                ts = datetime.strptime(row[date_column], date_format)
                timestamps.append(ts)
            except (KeyError, ValueError):
                continue
            
            # Parse OHLCV
            try:
                data["open"].append(float(row.get("Open", row.get("open", 0))))
                data["high"].append(float(row.get("High", row.get("high", 0))))
                data["low"].append(float(row.get("Low", row.get("low", 0))))
                data["close"].append(float(row.get("Close", row.get("close", 0))))
                data["volume"].append(float(row.get("Volume", row.get("volume", 0))))
            except (ValueError, KeyError):
                continue
    
    if not data["close"]:
        raise ValueError(f"No valid data found in {file_path}")
    
    return data, timestamps


def load_yahoo_csv(symbol: str, data_dir: str = "./data") -> Tuple[Dict[str, List], List[datetime]]:
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
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Tuple[Dict[str, List], List[datetime]]:
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
        raise ImportError("MetaTrader5 package not installed. Run: pip install MetaTrader5")
    
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
) -> Tuple[Dict[str, List], List[datetime]]:
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
        raise ImportError("yfinance package not installed. Run: pip install yfinance")
    
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start_date, end=end_date)
    
    if df.empty:
        raise ValueError(f"No data downloaded for {symbol}")
    
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{symbol.replace('=', '_')}.csv")
    df.to_csv(output_path)
    
    return output_path
