"""
sources/market_data.py — Market Data Sources (yfinance, ccxt, alpha_vantage)
"""
import pandas as pd
import yfinance as yf
from datetime import datetime
from pathlib import Path
import json
import time
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import SYMBOLS, STORAGE_DIR, RETRY_MAX, RETRY_DELAY

CACHE_FILE = STORAGE_DIR / "market_cache.json"


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_cache(data: dict):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data, indent=2))


def fetch_yfinance(symbols: list[str], period: str = "5d") -> pd.DataFrame:
    """Fetch OHLCV from Yahoo Finance, fallback to cache if nan"""
    cache = _load_cache()
    results = []
    for symbol in symbols:
        for attempt in range(RETRY_MAX):
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period=period)
                if len(df) > 0:
                    last_close = df["Close"].iloc[-1]
                    if pd.isna(last_close) and symbol in cache:
                        c = cache[symbol]
                        print(f"  {symbol}: nan -> cache {c['close']:.2f}")
                        for col in ["Close", "Open", "High", "Low"]:
                            df[col] = df[col].fillna(c[col.lower()])
                    elif pd.isna(last_close):
                        print(f"  {symbol}: nan (no cache)")
                    else:
                        cache[symbol] = {
                            "close": float(df["Close"].iloc[-1]),
                            "open": float(df["Open"].iloc[-1]),
                            "high": float(df["High"].iloc[-1]),
                            "low": float(df["Low"].iloc[-1]),
                            "updated": datetime.now().isoformat(),
                        }
                    df["symbol"] = symbol
                    df["source"] = "yfinance"
                    df["timestamp"] = datetime.now()
                    results.append(df)
                break
            except Exception as e:
                if attempt < RETRY_MAX - 1:
                    time.sleep(RETRY_DELAY)
                else:
                    print(f"  yfinance error {symbol}: {e}")
    _save_cache(cache)
    if results:
        return pd.concat(results)
    return pd.DataFrame()


def fetch_crypto_ccxt(symbols: list[str], timeframe: str = "1d") -> pd.DataFrame:
    """Fetch crypto data from ccxt (Binance)"""
    import ccxt
    results = []
    for symbol in symbols:
        for attempt in range(RETRY_MAX):
            try:
                exchange = ccxt.binance({"timeout": 30000})
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
                df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                df["symbol"] = symbol
                df["source"] = "ccxt"
                results.append(df)
                break
            except Exception as e:
                if attempt < RETRY_MAX - 1:
                    time.sleep(RETRY_DELAY)
                else:
                    print(f"  ccxt error {symbol}: {e}")
    if results:
        return pd.concat(results)
    return pd.DataFrame()


def fetch_all_market_data() -> dict[str, pd.DataFrame]:
    print("=== Fetching Market Data ===")
    all_forex = SYMBOLS["forex"]
    all_commodities = SYMBOLS["commodities"]
    all_crypto = SYMBOLS["crypto"]
    all_indices = SYMBOLS["indices"]

    results = {}
    print("  yfinance: forex + commodities + indices")
    results["yfinance"] = fetch_yfinance(all_forex + all_commodities + all_indices)

    print("  ccxt: crypto")
    results["ccxt"] = fetch_crypto_ccxt(all_crypto)

    print(f"  Total: {sum(len(v) for v in results.values())} rows")
    return results
