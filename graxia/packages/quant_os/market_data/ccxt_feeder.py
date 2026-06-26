"""
CCXT Async Feeder — Crypto OHLCV + Funding Rate + Open Interest.

Fetches data from Binance (or any ccxt-supported exchange) using
ccxt.async_support ONLY.  This module is intentionally isolated from
the XAUUSD/Forex pipeline to prevent cross-asset hallucination.

Usage:
    async with BinanceFeeder() as feeder:
        ohlcv = await feeder.fetch_ohlcv("BTC/USDT", "1h", limit=500)
        funding = await feeder.fetch_funding_rate("BTC/USDT")
        oi = await feeder.fetch_open_interest("BTC/USDT")

CRITICAL SAFETY:
    - ccxt.async_support is used exclusively (never sync ccxt)
    - Data from this feeder must NOT be joined into XAUUSD training tables
    - Each symbol's data is stored independently
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Lazy import — ccxt.async_support only
_ccxt_async = None


def _get_ccxt():
    global _ccxt_async
    if _ccxt_async is None:
        import ccxt.async_support as ccxt

        _ccxt_async = ccxt
    return _ccxt_async


# ── Data Classes ───────────────────────────────────────────────────


@dataclass
class OHLCVBar:
    """Single OHLCV bar from exchange."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class FundingRateSnapshot:
    """Current funding rate for a perpetual symbol."""

    symbol: str
    funding_rate: float  # annualized rate (e.g. 0.0001 = 10% APR)
    timestamp: datetime
    next_funding_time: datetime | None = None


@dataclass
class OpenInterestSnapshot:
    """Current open interest for a perpetual symbol."""

    symbol: str
    open_interest: float
    open_interest_value: float  # in quote currency (USDT)
    timestamp: datetime


@dataclass
class ExchangeConfig:
    """Configuration for exchange connection."""

    exchange_id: str = "binance"
    api_key: str = ""
    secret: str = ""
    sandbox: bool = False
    rate_limit_ms: int = 1200  # ms between requests (Binance = 1200)


# ── Feeder ─────────────────────────────────────────────────────────


class BinanceFeeder:
    """
    Async feeder for Binance crypto data.

    Uses ccxt.async_support exclusively.
    Each instance creates its own exchange connection.

    Usage:
        async with BinanceFeeder() as feeder:
            bars = await feeder.fetch_ohlcv("ETH/USDT", "1h", limit=500)
    """

    def __init__(self, config: ExchangeConfig | None = None):
        self._config = config or ExchangeConfig()
        self._exchange = None

    async def __aenter__(self):
        ccxt = _get_ccxt()
        exchange_class = getattr(ccxt, self._config.exchange_id)
        self._exchange = exchange_class(
            {
                "apiKey": self._config.api_key or None,
                "secret": self._config.secret or None,
                "enableRateLimit": True,
                "rateLimit": self._config.rate_limit_ms,
            }
        )
        if self._config.sandbox:
            self._exchange.set_sandbox_mode(True)
        return self

    async def __aexit__(self, *args):
        if self._exchange:
            await self._exchange.close()

    # ── OHLCV ─────────────────────────────────────────────────────

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 500,
        since_ms: int | None = None,
    ) -> list[OHLCVBar]:
        """
        Fetch OHLCV candles from exchange.

        Args:
            symbol: Trading pair (e.g. "BTC/USDT", "ETH/USDT")
            timeframe: Candle timeframe ("1m", "5m", "15m", "1h", "4h", "1d")
            limit: Number of candles to fetch (max 1000 for Binance)
            since_ms: Start timestamp in milliseconds (optional)

        Returns:
            List of OHLCVBar, oldest first
        """
        raw = await self._exchange.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=limit)
        bars = []
        for row in raw:
            bars.append(
                OHLCVBar(
                    timestamp=datetime.fromtimestamp(row[0] / 1000, tz=UTC),
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                )
            )
        logger.info("ccxt_feeder.ohlcv_fetched", symbol=symbol, timeframe=timeframe, count=len(bars))
        return bars

    async def fetch_ohlcv_batch(
        self,
        symbols: list[str],
        timeframe: str = "1h",
        limit: int = 500,
    ) -> dict[str, list[OHLCVBar]]:
        """
        Fetch OHLCV for multiple symbols concurrently.

        Returns dict mapping symbol -> list of bars.
        """
        tasks = {sym: self.fetch_ohlcv(sym, timeframe, limit) for sym in symbols}
        results = {}
        for sym, task in tasks.items():
            try:
                results[sym] = await task
            except Exception as exc:
                logger.warning("ccxt_feeder.fetch_failed", symbol=sym, error=str(exc))
                results[sym] = []
        return results

    # ── Funding Rate (Perpetuals) ─────────────────────────────────

    async def fetch_funding_rate(self, symbol: str) -> FundingRateSnapshot | None:
        """
        Fetch current funding rate for a perpetual swap.

        Binance returns funding every 8 hours.
        Positive rate = Longs pay Shorts (market is bullish/overleveraged).
        Negative rate = Shorts pay Longs (market is bearish/overleveraged).
        """
        try:
            fr = await self._exchange.fetch_funding_rate(symbol)
            return FundingRateSnapshot(
                symbol=symbol,
                funding_rate=float(fr.get("fundingRate", 0)),
                timestamp=datetime.now(UTC),
                next_funding_time=datetime.fromtimestamp(fr["fundingTimestamp"] / 1000, tz=UTC)
                if fr.get("fundingTimestamp")
                else None,
            )
        except Exception as exc:
            logger.warning("ccxt_feeder.funding_failed", symbol=symbol, error=str(exc))
            return None

    async def fetch_funding_batch(self, symbols: list[str]) -> dict[str, FundingRateSnapshot | None]:
        """Fetch funding rates for multiple symbols concurrently."""
        tasks = {sym: self.fetch_funding_rate(sym) for sym in symbols}
        return {sym: await task for sym, task in tasks.items()}

    # ── Open Interest (Perpetuals) ────────────────────────────────

    async def fetch_open_interest(self, symbol: str) -> OpenInterestSnapshot | None:
        """
        Fetch current open interest for a perpetual swap.

        Rising OI + Rising Price = new longs entering (trend continuation).
        Rising OI + Falling Price = new shorts entering (trend continuation).
        Falling OI + Rising Price = shorts closing (squeeze).
        Falling OI + Falling Price = longs closing (capitulation).
        """
        try:
            oi = await self._exchange.fetch_open_interest(symbol)
            return OpenInterestSnapshot(
                symbol=symbol,
                open_interest=float(oi.get("openInterestAmount", 0)),
                open_interest_value=float(oi.get("openInterestValue", 0)),
                timestamp=datetime.now(UTC),
            )
        except Exception as exc:
            logger.warning("ccxt_feeder.oi_failed", symbol=symbol, error=str(exc))
            return None

    async def fetch_oi_batch(self, symbols: list[str]) -> dict[str, OpenInterestSnapshot | None]:
        """Fetch open interest for multiple symbols concurrently."""
        tasks = {sym: self.fetch_open_interest(sym) for sym in symbols}
        return {sym: await task for sym, task in tasks.items()}

    # ── Top Altcoins Scanner ──────────────────────────────────────

    async def scan_top_altcoins(
        self,
        quote: str = "USDT",
        min_volume_usdt: float = 1_000_000,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Scan Binance for top altcoins by 24h volume.

        Returns list of dicts with symbol, price, volume, change_24h.
        Filters out stablecoins and wrapped tokens.
        """
        tickers = await self._exchange.fetch_tickers()
        results = []
        skip_bases = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "BIDR", "EUR"}

        for symbol, ticker in tickers.items():
            if not symbol.endswith(f"/{quote}"):
                continue
            base = symbol.split("/")[0]
            if base in skip_bases or base.startswith("WB") or base.startswith("C"):
                continue

            vol_usdt = float(ticker.get("quoteVolume", 0))
            if vol_usdt < min_volume_usdt:
                continue

            results.append(
                {
                    "symbol": symbol,
                    "price": float(ticker.get("last", 0)),
                    "volume_24h_usdt": vol_usdt,
                    "change_24h_pct": float(ticker.get("percentage", 0)),
                }
            )

        results.sort(key=lambda x: x["volume_24h_usdt"], reverse=True)
        return results[:limit]
