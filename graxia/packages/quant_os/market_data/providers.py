"""Unified Data Provider Manager — QuantConnect, Oanda, Polygon, AlphaVantage.

Provides a single interface for:
- QuantConnect Cloud backtesting + live data
- Oanda REST API (Forex CFD, metals)
- Polygon.io (US equities, options, crypto)
- Alpha Vantage (forex, crypto, equities — free tier)

Usage:
    from market_data.providers import DataProviders
    providers = DataProviders.from_env()
    bars = providers.get_forex_bars("EURUSD", "1h", "2024-01-01", "2025-01-01")
"""
from __future__ import annotations

import os
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class OHLCVBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class ProviderConfig:
    """Base config — provider-specific subclasses add fields."""
    enabled: bool = False
    timeout: float = 30.0


# ---------------------------------------------------------------------------
# Provider ABC
# ---------------------------------------------------------------------------

class DataProvider(ABC):
    """Base class for all data providers."""

    name: str = "base"

    def __init__(self, config: ProviderConfig, client: Optional[httpx.Client] = None):
        self.config = config
        self._client = client or httpx.Client(timeout=config.timeout)

    @abstractmethod
    def get_forex_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        ...

    @abstractmethod
    def get_equity_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        ...

    @abstractmethod
    def get_crypto_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        ...

    @abstractmethod
    def health_check(self) -> dict:
        ...

    def close(self):
        self._client.close()


# ---------------------------------------------------------------------------
# QuantConnect Cloud
# ---------------------------------------------------------------------------

@dataclass
class QuantConnectConfig(ProviderConfig):
    user_id: str = ""
    api_token: str = ""
    project_id: int = 0
    organization_id: str = os.getenv("QUANTCONNECT_ORG_ID", "")


class QuantConnectProvider(DataProvider):
    """QuantConnect Cloud — backtesting, live data, cloud algorithms.

    Uses LEAN CLI for backtests and QC REST API for data.
    """

    name = "quantconnect"

    def __init__(self, config: QuantConnectConfig, **kwargs):
        super().__init__(config, **kwargs)
        self.config: QuantConnectConfig = config
        self._base_url = "https://www.quantconnect.com/api/v2"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.config.api_token}",
            "Content-Type": "application/json",
        }

    def get_forex_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        return self._get_bars("forex", symbol, timeframe, start, end)

    def get_equity_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        return self._get_bars("equity", symbol, timeframe, start, end)

    def get_crypto_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        return self._get_bars("crypto", symbol, timeframe, start, end)

    def _get_bars(
        self, asset_class: str, symbol: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        """Fetch historical data from QC cloud via REST API."""
        url = f"{self._base_url}/libraries/read"
        payload = {
            "projectId": self.config.project_id,
            "organizationId": self.config.organization_id,
            "name": f"{asset_class}/{symbol}/{timeframe}",
            "start": start,
            "end": end,
        }
        try:
            resp = self._client.post(url, json=payload, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            return [
                OHLCVBar(
                    timestamp=datetime.fromisoformat(d["time"]),
                    open=d["open"],
                    high=d["high"],
                    low=d["low"],
                    close=d["close"],
                    volume=d.get("volume", 0),
                )
                for d in data.get("data", [])
            ]
        except Exception as e:
            logger.error("QuantConnect data fetch failed: %s", e)
            return []

    def health_check(self) -> dict:
        try:
            resp = self._client.get(
                f"{self._base_url}/auth/check",
                headers=self._headers(),
            )
            ok = resp.status_code == 200
            return {"provider": self.name, "ok": ok, "status": resp.status_code}
        except Exception as e:
            return {"provider": self.name, "ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Oanda
# ---------------------------------------------------------------------------

@dataclass
class OandaConfig(ProviderConfig):
    access_token: str = ""
    account_id: str = ""
    environment: str = "Practice"  # Practice | Live


class OandaProvider(DataProvider):
    """Oanda v20 REST API — Forex, CFD, metals.

    Free practice account: https://www.oanda.com/account/practice/
    Live account: https://www.oanda.com/account/live/
    """

    name = "oanda"

    def __init__(self, config: OandaConfig, **kwargs):
        super().__init__(config, **kwargs)
        self.config: OandaConfig = config
        env = "api-fxpractice" if config.environment == "Practice" else "api-fxtrade"
        self._base_url = f"https://{env}.oanda.com/v3"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.config.access_token}",
            "Content-Type": "application/json",
        }

    def get_forex_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        instrument = symbol.upper().replace("USD", "_USD").replace("EUR", "_EUR")
        # Oanda uses format: "EUR_USD" — convert from "EURUSD"
        if len(symbol) == 6:
            instrument = f"{symbol[:3]}_{symbol[3:]}"
        else:
            instrument = symbol

        granularity = _timeframe_to_oanda_granularity(timeframe)
        url = f"{self._base_url}/instruments/{instrument}/candles"
        params = {
            "granularity": granularity,
            "from": f"{start}T00:00:00Z",
            "to": f"{end}T23:59:59Z",
            "price": "MBA",  # Mid, Bid, Ask
        }
        try:
            resp = self._client.get(url, params=params, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            bars = []
            for c in data.get("candles", []):
                mid = c.get("mid", {})
                if mid:
                    bars.append(OHLCVBar(
                        timestamp=datetime.fromisoformat(c["time"].replace("Z", "+00:00")),
                        open=float(mid["o"]),
                        high=float(mid["h"]),
                        low=float(mid["l"]),
                        close=float(mid["c"]),
                        volume=float(c.get("volume", 0)),
                    ))
            return bars
        except Exception as e:
            logger.error("Oanda data fetch failed for %s: %s", symbol, e)
            return []

    def get_equity_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        """Oanda CFD — trade equity CFDs like US30, NAS100, etc."""
        # Map common symbols to Oanda CFD instruments
        cfd_map = {
            "SPX500": "US500_USD", "US30": "US30_USD", "NAS100": "NAS100_USD",
            "SPY": "US500_USD", "QQQ": "NAS100_USD",
        }
        instrument = cfd_map.get(symbol.upper(), symbol)
        return self._fetch_cfd(instrument, timeframe, start, end)

    def get_crypto_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        """Oanda crypto CFDs."""
        return self._fetch_cfd(symbol, timeframe, start, end)

    def _fetch_cfd(
        self, instrument: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        granularity = _timeframe_to_oanda_granularity(timeframe)
        url = f"{self._base_url}/instruments/{instrument}/candles"
        params = {
            "granularity": granularity,
            "from": f"{start}T00:00:00Z",
            "to": f"{end}T23:59:59Z",
            "price": "MBA",
        }
        try:
            resp = self._client.get(url, params=params, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            bars = []
            for c in data.get("candles", []):
                mid = c.get("mid", {})
                if mid:
                    bars.append(OHLCVBar(
                        timestamp=datetime.fromisoformat(c["time"].replace("Z", "+00:00")),
                        open=float(mid["o"]),
                        high=float(mid["h"]),
                        low=float(mid["l"]),
                        close=float(mid["c"]),
                        volume=float(c.get("volume", 0)),
                    ))
            return bars
        except Exception as e:
            logger.error("Oanda CFD fetch failed for %s: %s", instrument, e)
            return []

    def health_check(self) -> dict:
        try:
            url = f"{self._base_url}/accounts/{self.config.account_id}"
            resp = self._client.get(url, headers=self._headers())
            ok = resp.status_code == 200
            account_info = resp.json().get("account", {}) if ok else {}
            return {
                "provider": self.name,
                "ok": ok,
                "account_id": self.config.account_id,
                "balance": account_info.get("balance"),
                "NAV": account_info.get("NAV"),
            }
        except Exception as e:
            return {"provider": self.name, "ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Polygon.io
# ---------------------------------------------------------------------------

@dataclass
class PolygonConfig(ProviderConfig):
    api_key: str = ""
    tier: str = "free"  # free | starter | developer | pro


class PolygonProvider(DataProvider):
    """Polygon.io REST API — US equities, options, crypto, forex.

    Free tier: 5 API calls/min, delayed data.
    https://polygon.io/
    """

    name = "polygon"

    def __init__(self, config: PolygonConfig, **kwargs):
        super().__init__(config, **kwargs)
        self.config: PolygonConfig = config
        self._base_url = "https://api.polygon.io"

    def _params(self) -> dict:
        return {"apiKey": self.config.api_key}

    def get_forex_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        # Polygon uses "C:EURUSD" format
        ticker = f"C:{symbol.upper()}"
        return self._fetch_bars(ticker, timeframe, start, end)

    def get_equity_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        return self._fetch_bars(symbol.upper(), timeframe, start, end)

    def get_crypto_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        # Polygon uses "X:BTCUSD" format
        ticker = f"X:{symbol.upper()}"
        return self._fetch_bars(ticker, timeframe, start, end)

    def _fetch_bars(
        self, ticker: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        multiplier, timespan = _timeframe_to_polygon_params(timeframe)
        url = f"{self._base_url}/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{start}/{end}"
        params = {**self._params(), "adjusted": "true", "limit": "50000"}
        try:
            resp = self._client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            return [
                OHLCVBar(
                    timestamp=datetime.fromtimestamp(r["t"] / 1000),
                    open=r["o"],
                    high=r["h"],
                    low=r["l"],
                    close=r["c"],
                    volume=r.get("v", 0),
                )
                for r in results
            ]
        except Exception as e:
            logger.error("Polygon fetch failed for %s: %s", ticker, e)
            return []

    def health_check(self) -> dict:
        try:
            url = f"{self._base_url}/v2/aggs/ticker/AAPL/range/1/day/2025-01-01/2025-01-02"
            resp = self._client.get(url, params=self._params())
            ok = resp.status_code == 200
            return {"provider": self.name, "ok": ok, "status": resp.status_code}
        except Exception as e:
            return {"provider": self.name, "ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Alpha Vantage
# ---------------------------------------------------------------------------

@dataclass
class AlphaVantageConfig(ProviderConfig):
    api_key: str = ""
    tier: str = "free"  # free | premium


class AlphaVantageProvider(DataProvider):
    """Alpha Vantage REST API — forex, crypto, equities (free tier).

    Free tier: 25 requests/day, 5/min.
    https://www.alphavantage.co/support/#api-key
    """

    name = "alphavantage"

    def __init__(self, config: AlphaVantageConfig, **kwargs):
        super().__init__(config, **kwargs)
        self.config: AlphaVantageConfig = config
        self._base_url = "https://www.alphavantage.co/query"

    def get_forex_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        from_currency = symbol[:3]
        to_currency = symbol[3:]
        interval = _timeframe_to_av_interval(timeframe)

        # Free tier: FX_DAILY only. Premium: FX_INTRADAY.
        if self.config.tier == "free" or interval in ("daily", "weekly", "monthly"):
            params = {
                "function": "FX_DAILY",
                "from_symbol": from_currency,
                "to_symbol": to_currency,
                "apikey": self.config.api_key,
                "outputsize": "full",
            }
        else:
            params = {
                "function": "FX_INTRADAY",
                "from_symbol": from_currency,
                "to_symbol": to_currency,
                "interval": interval,
                "apikey": self.config.api_key,
                "outputsize": "full",
            }
        return self._fetch_and_parse(params, "Time Series FX")

    def get_equity_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        interval = _timeframe_to_av_interval(timeframe)

        # Free tier: TIME_SERIES_DAILY only. Premium: TIME_SERIES_INTRADAY.
        if self.config.tier == "free" or interval in ("daily", "weekly", "monthly"):
            params = {
                "function": "TIME_SERIES_DAILY",
                "symbol": symbol.upper(),
                "apikey": self.config.api_key,
                "outputsize": "full",
            }
        else:
            params = {
                "function": "TIME_SERIES_INTRADAY",
                "symbol": symbol.upper(),
                "interval": interval,
                "apikey": self.config.api_key,
                "outputsize": "full",
            }
        return self._fetch_and_parse(params, "Time Series")

    def get_crypto_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        interval = _timeframe_to_av_interval(timeframe)

        # Free tier: DIGITAL_CURRENCY_DAILY only. Premium: CRYPTO_INTRADAY.
        if self.config.tier == "free" or interval in ("daily", "weekly", "monthly"):
            params = {
                "function": "DIGITAL_CURRENCY_DAILY",
                "symbol": symbol[:3].upper(),
                "market": "USD",
                "apikey": self.config.api_key,
                "outputsize": "full",
            }
        else:
            params = {
                "function": "CRYPTO_INTRADAY",
                "symbol": symbol[:3].upper(),
                "market": "USD",
                "interval": interval,
                "apikey": self.config.api_key,
                "outputsize": "full",
            }
        return self._fetch_and_parse(params, "Time Series")

    def _fetch_and_parse(self, params: dict, series_key_prefix: str) -> list[OHLCVBar]:
        try:
            resp = self._client.get(self._base_url, params=params)
            resp.raise_for_status()
            data = resp.json()

            # Alpha Vantage uses different keys depending on function
            time_series = None
            for key in data:
                if key.startswith(series_key_prefix):
                    time_series = data[key]
                    break

            if not time_series:
                logger.warning("Alpha Vantage: no time series found (keys: %s)", list(data.keys()))
                return []

            bars = []
            for timestamp_str, values in time_series.items():
                try:
                    bars.append(OHLCVBar(
                        timestamp=datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S"),
                        open=float(values.get("1. open", values.get("1a. open (USD)", 0))),
                        high=float(values.get("2. high", values.get("2a. high (USD)", 0))),
                        low=float(values.get("3. low", values.get("3a. low (USD)", 0))),
                        close=float(values.get("4. close", values.get("4a. close (USD)", 0))),
                        volume=float(values.get("5. volume", values.get("5. volume", 0))),
                    ))
                except (ValueError, KeyError):
                    continue
            return sorted(bars, key=lambda b: b.timestamp)
        except Exception as e:
            logger.error("Alpha Vantage fetch failed: %s", e)
            return []

    def health_check(self) -> dict:
        try:
            params = {
                "function": "CURRENCY_EXCHANGE_RATE",
                "from_currency": "EUR",
                "to_currency": "USD",
                "apikey": self.config.api_key,
            }
            resp = self._client.get(self._base_url, params=params)
            data = resp.json()
            ok = "Realtime Currency Exchange Rate" in data
            return {"provider": self.name, "ok": ok, "keys_remaining": "N/A"}
        except Exception as e:
            return {"provider": self.name, "ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# yfinance (Free — no API key needed)
# ---------------------------------------------------------------------------

@dataclass
class YFinanceConfig(ProviderConfig):
    """yfinance config — always enabled, no API key needed."""
    enabled: bool = True


class YFinanceProvider(DataProvider):
    """Yahoo Finance via yfinance — free, no API key.

    Covers: US equities, ETFs, forex (EURUSD=X), crypto (BTC-USD).
    Limitations: hourly data only 730 days, daily unlimited.
    """

    name = "yfinance"

    def __init__(self, config: Optional[YFinanceConfig] = None, **kwargs):
        super().__init__(config or YFinanceConfig(enabled=True), **kwargs)
        import yfinance as yf
        self._yf = yf

    def _interval_map(self, tf: str) -> str:
        mapping = {
            "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "1h", "1d": "1d", "1w": "1wk", "1M": "1mo",
        }
        return mapping.get(tf, "1d")

    def _to_yf_symbol(self, symbol: str, asset_class: str) -> str:
        """Convert symbol to yfinance format."""
        s = symbol.upper()
        if asset_class == "forex":
            return f"{s}=X"
        elif asset_class == "crypto":
            return f"{s}-USD"
        return s

    def _fetch(self, yf_symbol: str, interval: str, start: str, end: str) -> list[OHLCVBar]:
        try:
            ticker = self._yf.Ticker(yf_symbol)
            df = ticker.history(start=start, end=end, interval=interval)
            if df.empty:
                return []
            bars = []
            for idx, row in df.iterrows():
                bars.append(OHLCVBar(
                    timestamp=idx.to_pydatetime().replace(tzinfo=None),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row.get("Volume", 0)),
                ))
            return bars
        except Exception as e:
            logger.error("yfinance fetch failed for %s: %s", yf_symbol, e)
            return []

    def get_forex_bars(self, symbol: str, timeframe: str, start: str, end: str) -> list[OHLCVBar]:
        return self._fetch(self._to_yf_symbol(symbol, "forex"), self._interval_map(timeframe), start, end)

    def get_equity_bars(self, symbol: str, timeframe: str, start: str, end: str) -> list[OHLCVBar]:
        return self._fetch(self._to_yf_symbol(symbol, "equity"), self._interval_map(timeframe), start, end)

    def get_crypto_bars(self, symbol: str, timeframe: str, start: str, end: str) -> list[OHLCVBar]:
        return self._fetch(self._to_yf_symbol(symbol, "crypto"), self._interval_map(timeframe), start, end)

    def health_check(self) -> dict:
        try:
            ticker = self._yf.Ticker("SPY")
            info = ticker.info
            ok = "regularMarketPrice" in info or "currentPrice" in info
            return {"provider": self.name, "ok": ok, "price": info.get("regularMarketPrice", "?")}
        except Exception as e:
            return {"provider": self.name, "ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Unified Manager
# ---------------------------------------------------------------------------

class DataProviders:
    """Unified data provider manager — tries providers in priority order.

    Priority: Polygon (best equities) → Oanda (best forex) → AlphaVantage (fallback) → QC Cloud
    """

    def __init__(self, providers: Optional[list[DataProvider]] = None):
        self._providers = providers or []

    @classmethod
    def from_env(cls) -> "DataProviders":
        """Create provider instances from environment variables.

        Priority: yfinance (free, always) → Polygon → Oanda → AlphaVantage → QC Cloud
        """
        providers: list[DataProvider] = []

        # yfinance — always available, no API key needed
        providers.append(YFinanceProvider(YFinanceConfig(enabled=True)))

        # QuantConnect Cloud
        qc_user = os.getenv("QUANTCONNECT_USER_ID", "")
        qc_token = os.getenv("QUANTCONNECT_API_TOKEN", "")
        qc_project = int(os.getenv("QUANTCONNECT_PROJECT_ID", "0"))
        if qc_token:
            providers.append(QuantConnectProvider(QuantConnectConfig(
                enabled=True,
                user_id=qc_user,
                api_token=qc_token,
                project_id=qc_project,
            )))

        # Oanda
        oanda_token = os.getenv("OANDA_ACCESS_TOKEN", "")
        oanda_account = os.getenv("OANDA_ACCOUNT_ID", "")
        oanda_env = os.getenv("OANDA_ENVIRONMENT", "Practice")
        if oanda_token:
            providers.append(OandaProvider(OandaConfig(
                enabled=True,
                access_token=oanda_token,
                account_id=oanda_account,
                environment=oanda_env,
            )))

        # Polygon
        polygon_key = os.getenv("POLYGON_API_KEY", "")
        if polygon_key:
            providers.append(PolygonProvider(PolygonConfig(
                enabled=True,
                api_key=polygon_key,
            )))

        # Alpha Vantage
        av_key = os.getenv("ALPHAVANTAGE_API_KEY", "")
        if av_key:
            providers.append(AlphaVantageProvider(AlphaVantageConfig(
                enabled=True,
                api_key=av_key,
            )))

        if not providers:
            logger.warning("No data providers configured — set API keys in .env")

        return cls(providers)

    def get_forex_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        """Fetch forex bars — tries providers in priority order."""
        for p in self._providers:
            try:
                bars = p.get_forex_bars(symbol, timeframe, start, end)
                if bars:
                    logger.info("Got %d forex bars from %s for %s", len(bars), p.name, symbol)
                    return bars
            except Exception as e:
                logger.warning("Provider %s failed for forex %s: %s", p.name, symbol, e)
        return []

    def get_equity_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        """Fetch equity bars — tries providers in priority order."""
        for p in self._providers:
            try:
                bars = p.get_equity_bars(symbol, timeframe, start, end)
                if bars:
                    logger.info("Got %d equity bars from %s for %s", len(bars), p.name, symbol)
                    return bars
            except Exception as e:
                logger.warning("Provider %s failed for equity %s: %s", p.name, symbol, e)
        return []

    def get_crypto_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> list[OHLCVBar]:
        """Fetch crypto bars — tries providers in priority order."""
        for p in self._providers:
            try:
                bars = p.get_crypto_bars(symbol, timeframe, start, end)
                if bars:
                    logger.info("Got %d crypto bars from %s for %s", len(bars), p.name, symbol)
                    return bars
            except Exception as e:
                logger.warning("Provider %s failed for crypto %s: %s", p.name, symbol, e)
        return []

    def health_check(self) -> list[dict]:
        """Check health of all configured providers."""
        return [p.health_check() for p in self._providers]

    def close(self):
        for p in self._providers:
            p.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _timeframe_to_oanda_granularity(tf: str) -> str:
    """Convert '1h', '15m', '1D' etc. to Oanda granularity (M1, H1, D)."""
    mapping = {
        "1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30",
        "1h": "H1", "4h": "H4",
        "1D": "D", "1d": "D", "daily": "D",
        "1W": "W", "1w": "W", "weekly": "W",
        "1M": "M", "monthly": "M",
    }
    return mapping.get(tf, "H1")


def _timeframe_to_polygon_params(tf: str) -> tuple[int, str]:
    """Convert '1h', '15m', '1D' to (multiplier, timespan)."""
    mapping = {
        "1m": (1, "minute"), "5m": (5, "minute"), "15m": (15, "minute"),
        "30m": (30, "minute"), "1h": (1, "hour"), "4h": (4, "hour"),
        "1D": (1, "day"), "1d": (1, "day"), "daily": (1, "day"),
        "1W": (1, "week"), "1w": (1, "week"),
        "1M": (1, "month"), "monthly": (1, "month"),
    }
    return mapping.get(tf, (1, "hour"))


def _timeframe_to_av_interval(tf: str) -> str:
    """Convert '1h', '15m', '1D' to Alpha Vantage interval."""
    mapping = {
        "1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
        "1h": "60min", "4h": "daily",
        "1D": "daily", "1d": "daily", "daily": "daily",
    }
    return mapping.get(tf, "60min")
