"""
Multi-Source Data Pipeline

Aggregates data from multiple sources:
- CCXT (crypto OHLCV from 100+ exchanges)
- CoinGecko (crypto market data)
- Yahoo Finance (stocks, forex, gold)
- FRED (macro economic data)

Priority chain with fallback:
    CCXT → CoinGecko → Yahoo Finance
"""

import asyncio
import os
import time
import warnings
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass
class DataSource:
    """Data source configuration"""

    name: str
    priority: int
    enabled: bool = True
    rate_limit: int = 100  # requests per minute
    _request_times: list[float] = field(default_factory=list, repr=False)

    async def wait_if_needed(self):
        """Sliding-window rate limiter. Blocks until a slot opens."""
        now = time.monotonic()
        window = 60.0
        self._request_times = [t for t in self._request_times if now - t < window]
        if len(self._request_times) >= self.rate_limit:
            wait_for = 60.0 - (now - self._request_times[0])
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._request_times = self._request_times[1:]
        self._request_times.append(time.monotonic())


class DataPipeline:
    """
    Multi-source data pipeline with fallback chain.

    Usage:
        pipeline = DataPipeline()
        data = await pipeline.fetch_ohlcv("BTC/USDT", "1h", 100)
        macro = await pipeline.fetch_macro("DFF")  # Fed rate
    """

    def __init__(self):
        self.sources = {
            "ccxt": DataSource(name="CCXT", priority=1, rate_limit=20),
            "coingecko": DataSource(name="CoinGecko", priority=2, rate_limit=30),
            "yahoo": DataSource(name="Yahoo Finance", priority=3, rate_limit=60),
            "fred": DataSource(name="FRED", priority=4, rate_limit=100),
        }

        self._cache: dict[str, dict] = {}
        self._cache_ttl = timedelta(minutes=5)

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
        exchange: str = "binance",
        require_real_ohlcv: bool = False,
    ) -> dict[str, list] | None:
        """
        Fetch OHLCV data with fallback chain.

        Args:
            symbol: Trading symbol (e.g., "BTC/USDT", "EURUSD", "GC=F")
            timeframe: Timeframe (1m, 5m, 15m, 1h, 4h, 1d)
            limit: Number of bars
            exchange: Exchange for CCXT
            require_real_ohlcv: If True, raise ValueError when only synthetic OHLCV is available

        Returns:
            Dict with 'open', 'high', 'low', 'close', 'volume', 'timestamps', 'synthetic_ohlcv'
        """
        # Check cache
        cache_key = f"ohlcv:{symbol}:{timeframe}:{limit}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        # Try CCXT first (crypto)
        if "/" in symbol:  # Crypto pair
            await self.sources["ccxt"].wait_if_needed()
            data = await self._fetch_ccxt(symbol, timeframe, limit, exchange)
            if data:
                self._set_cache(cache_key, data)
                return data

            # Fallback to CoinGecko
            await self.sources["coingecko"].wait_if_needed()
            data = await self._fetch_coingecko(symbol, timeframe, limit)
            if data:
                self._set_cache(cache_key, data)
                if require_real_ohlcv and data.get("synthetic_ohlcv"):
                    raise ValueError(
                        f"Only synthetic OHLCV available for {symbol} from CoinGecko; "
                        "require_real_ohlcv=True requires a source with real candle data"
                    )
                return data

        # Try Yahoo Finance (stocks, forex, gold)
        await self.sources["yahoo"].wait_if_needed()
        data = await self._fetch_yahoo(symbol, timeframe, limit)
        if data:
            self._set_cache(cache_key, data)
            return data

        return None

    async def fetch_macro(self, series_id: str, limit: int = 100) -> dict | None:
        """
        Fetch macro economic data from FRED.

        Common series:
        - DFF: Fed Funds Rate
        - CPIAUCSL: CPI
        - UNRATE: Unemployment Rate
        - GDP: GDP
        - T10Y2Y: Yield Curve
        """
        await self.sources["fred"].wait_if_needed()
        return await self._fetch_fred(series_id, limit)

    async def _fetch_ccxt(self, symbol: str, timeframe: str, limit: int, exchange: str) -> dict | None:
        """Fetch from CCXT"""
        try:
            import ccxt.async_support as ccxt

            exchange_class = getattr(ccxt, exchange, None)
            if not exchange_class:
                return None

            ex = exchange_class({"enableRateLimit": True})

            # Map timeframe
            tf_map = {
                "1m": "1m",
                "5m": "5m",
                "15m": "15m",
                "30m": "30m",
                "1h": "1h",
                "4h": "4h",
                "1d": "1d",
            }
            ccxt_tf = tf_map.get(timeframe, "1h")

            ohlcv = await ex.fetch_ohlcv(symbol, ccxt_tf, limit=limit)
            await ex.close()

            if not ohlcv:
                return None

            return {
                "open": [c[1] for c in ohlcv],
                "high": [c[2] for c in ohlcv],
                "low": [c[3] for c in ohlcv],
                "close": [c[4] for c in ohlcv],
                "volume": [c[5] for c in ohlcv],
                "timestamps": [datetime.fromtimestamp(c[0] / 1000) for c in ohlcv],
                "source": "ccxt",
                "synthetic_ohlcv": False,
            }

        except Exception as e:
            print(f"CCXT error: {e}")
            return None

    async def _fetch_coingecko(self, symbol: str, timeframe: str, limit: int) -> dict | None:
        """Fetch from CoinGecko"""
        try:
            import aiohttp

            # Extract coin id from symbol
            coin_id = symbol.split("/")[0].lower()

            # Map timeframe
            tf_map = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
            days = max(1, (limit * tf_map.get(timeframe, 60)) // (24 * 60))

            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
            params = {"vs_currency": "usd", "days": days}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        return None

                    data = await resp.json()
                    prices = data.get("prices", [])

                    if not prices:
                        return None

                    # Convert to OHLCV (CoinGecko returns price points)
                    warnings.warn(
                        "CoinGecko /market_chart returns price points, not real candles. "
                        "High/low are synthetic (±0.1%) and will corrupt ATR/ADX/BB calculations.",
                        stacklevel=2,
                    )
                    closes = [p[1] for p in prices[-limit:]]
                    opens = closes[:-1] + [closes[-1]]
                    highs = [max(o, c) * 1.001 for o, c in zip(opens, closes, strict=False)]
                    lows = [min(o, c) * 0.999 for o, c in zip(opens, closes, strict=False)]
                    volumes = [0] * len(closes)  # CoinGecko doesn't provide volume in this endpoint

                    return {
                        "open": opens,
                        "high": highs,
                        "low": lows,
                        "close": closes,
                        "volume": volumes,
                        "timestamps": [datetime.fromtimestamp(p[0] / 1000) for p in prices[-limit:]],
                        "source": "coingecko",
                        "synthetic_ohlcv": True,
                    }

        except Exception as e:
            print(f"CoinGecko error: {e}")
            return None

    async def _fetch_yahoo(self, symbol: str, timeframe: str, limit: int) -> dict | None:
        """Fetch from Yahoo Finance"""
        try:
            import yfinance as yf

            # Map symbol for Yahoo
            yahoo_symbol = symbol
            if symbol == "XAUUSD" or symbol == "XAU/USD":
                yahoo_symbol = "GC=F"  # Gold futures
            elif symbol == "EURUSD" or symbol == "EUR/USD":
                yahoo_symbol = "EURUSD=X"
            elif "/" in symbol:
                yahoo_symbol = symbol.replace("/", "") + "=X"

            # Map timeframe
            tf_map = {
                "1m": "1m",
                "5m": "5m",
                "15m": "15m",
                "1h": "1h",
                "4h": "1h",
                "1d": "1d",
            }
            yf_interval = tf_map.get(timeframe, "15m")

            # Period
            if yf_interval in ["1m"]:
                period = "7d"
            elif yf_interval in ["5m", "15m"]:
                period = "60d"
            else:
                period = "1y"

            ticker = yf.Ticker(yahoo_symbol)
            df = ticker.history(period=period, interval=yf_interval)

            if df.empty:
                return None

            df = df.tail(limit)

            return {
                "open": df["Open"].tolist(),
                "high": df["High"].tolist(),
                "low": df["Low"].tolist(),
                "close": df["Close"].tolist(),
                "volume": df["Volume"].tolist(),
                "timestamps": [idx.to_pydatetime() for idx in df.index],
                "source": "yahoo",
                "synthetic_ohlcv": False,
            }

        except Exception as e:
            print(f"Yahoo error: {e}")
            return None

    async def _fetch_fred(self, series_id: str, limit: int) -> dict | None:
        """Fetch from FRED API"""
        try:
            import aiohttp

            api_key = os.getenv("FRED_API_KEY", "")
            if not api_key:
                return None

            url = "https://api.stlouisfed.org/fred/series/observations"
            params = {
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "limit": limit,
                "sort_order": "desc",
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        return None

                    data = await resp.json()
                    observations = data.get("observations", [])

                    return {
                        "dates": [o["date"] for o in observations],
                        "values": [float(o["value"]) for o in observations if o["value"] != "."],
                        "series_id": series_id,
                        "source": "fred",
                    }

        except Exception as e:
            print(f"FRED error: {e}")
            return None

    def _get_cached(self, key: str) -> dict | None:
        """Get cached data if valid"""
        if key in self._cache:
            entry = self._cache[key]
            if datetime.now(UTC) - entry["time"] < self._cache_ttl:
                return entry["data"]
        return None

    def _set_cache(self, key: str, data: dict) -> None:
        """Set cache"""
        self._cache[key] = {
            "data": data,
            "time": datetime.now(UTC),
        }


class SentimentPipeline:
    """
    Sentiment data from multiple sources.
    """

    async def fetch_google_trends(self, keywords: list[str]) -> dict | None:
        """Fetch Google Trends data"""
        try:
            from pytrends.request import TrendReq

            pytrends = TrendReq(hl="en-US", tz=360)
            pytrends.build_payload(keywords, cat=0, timeframe="today 12-m")
            data = pytrends.interest_over_time()

            if data.empty:
                return None

            return {
                "keywords": keywords,
                "data": data.to_dict(),
                "source": "google_trends",
            }

        except Exception as e:
            print(f"Google Trends error: {e}")
            return None

    async def fetch_fear_greed(self) -> dict | None:
        """Fetch Fear & Greed Index"""
        try:
            import aiohttp

            url = "https://api.alternative.me/fng/"

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None

                    data = await resp.json()
                    entry = data.get("data", [{}])[0]

                    return {
                        "value": int(entry.get("value", 50)),
                        "classification": entry.get("value_classification", "Neutral"),
                        "source": "fear_greed",
                    }

        except Exception as e:
            print(f"Fear & Greed error: {e}")
            return None
