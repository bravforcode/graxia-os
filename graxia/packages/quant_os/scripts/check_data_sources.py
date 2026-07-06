"""Check available data sources and their limits."""
import yfinance as yf
from datetime import datetime, timedelta

# Test yfinance M1 limits for different symbols
symbols = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "AUDUSD": "AUDUSD=X",
    "NZDUSD": "NZDUSD=X",
    "USDCAD": "USDCAD=X",
    "USDCHF": "USDCHF=X",
    "USDJPY": "JPY=X",
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
    "US30": "^DJI",
    "NAS100": "^IXIC",
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "XPDUSD": None,
    "XPTUSD": None,
}

print("=== YFINANCE M1 DATA LIMITS ===")
for name, ticker_sym in symbols.items():
    if ticker_sym is None:
        print(f"{name}: No yfinance ticker available")
        continue
    try:
        ticker = yf.Ticker(ticker_sym)
        # yfinance limits: M1 = 7 days
        df = ticker.history(period="7d", interval="1m")
        if len(df) > 0:
            first = df.index[0].strftime("%Y-%m-%d %H:%M")
            last = df.index[-1].strftime("%Y-%m-%d %H:%M")
            print(f"{name}: {len(df)} M1 bars, {first} to {last}")
        else:
            print(f"{name}: 0 bars returned")
    except Exception as e:
        print(f"{name}: ERROR - {e}")

# Test higher timeframes for longer history
print("\n=== YFINANCE H1 DATA (6 months) ===")
for name, ticker_sym in symbols.items():
    if ticker_sym is None:
        continue
    try:
        ticker = yf.Ticker(ticker_sym)
        df = ticker.history(period="6mo", interval="1h")
        if len(df) > 0:
            first = df.index[0].strftime("%Y-%m-%d")
            last = df.index[-1].strftime("%Y-%m-%d")
            print(f"{name}: {len(df)} H1 bars, {first} to {last}")
        else:
            print(f"{name}: 0 bars")
    except Exception as e:
        print(f"{name}: ERROR - {e}")

print("\n=== YFINANCE D1 DATA (2 years) ===")
for name, ticker_sym in symbols.items():
    if ticker_sym is None:
        continue
    try:
        ticker = yf.Ticker(ticker_sym)
        df = ticker.history(period="2y", interval="1d")
        if len(df) > 0:
            first = df.index[0].strftime("%Y-%m-%d")
            last = df.index[-1].strftime("%Y-%m-%d")
            print(f"{name}: {len(df)} D1 bars, {first} to {last}")
        else:
            print(f"{name}: 0 bars")
    except Exception as e:
        print(f"{name}: ERROR - {e}")
