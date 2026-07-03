"""
TradingView MCP Client — market data, screening, backtest, sentiment.

Provides async access to TradingView's MCP server for:
  - Real-time prices and OHLCV data
  - Stock/crypto screening (oversold, breakout, trending)
  - Strategy backtesting (RSI, Bollinger, MACD, EMA Cross, Supertrend, Donchian)
  - Sentiment analysis (Reddit + news)
  - Full symbol analysis combining price + technical + sentiment

Usage:
    async with TradingViewClient() as client:
        price = await client.get_price("AAPL")
        snapshot = await client.get_market_snapshot()
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

try:
    from ..config.tv_config import (
        TV_DEFAULT_TIMEFRAME,
        TV_MAX_RETRIES,
        TV_MCP_URL,
        TV_REQUEST_TIMEOUT,
        TV_RETRY_BACKOFF,
        TV_SCREEN_EXCHANGE,
    )
except ImportError:
    from config.tv_config import (
        TV_DEFAULT_TIMEFRAME,
        TV_MAX_RETRIES,
        TV_MCP_URL,
        TV_REQUEST_TIMEOUT,
        TV_RETRY_BACKOFF,
        TV_SCREEN_EXCHANGE,
    )

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PriceData:
    """Real-time price snapshot for a symbol."""

    symbol: str
    price: float
    change: float
    change_pct: float
    volume: int
    timestamp: datetime


@dataclass(frozen=True)
class OHLCVBar:
    """Single OHLCV candle."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class ScreenResult:
    """Single screening result."""

    symbol: str
    name: str
    price: float
    change_pct: float
    signal: str  # "oversold", "breakout", "trending"
    score: float


@dataclass(frozen=True)
class BacktestResult:
    """Backtest output for a strategy on a symbol."""

    symbol: str
    strategy: str
    total_trades: int
    win_rate: float
    profit_factor: float
    max_drawdown: float
    net_profit: float
    sharpe_ratio: float
    trades: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class SentimentData:
    """Aggregated sentiment from Reddit and news sources."""

    symbol: str
    reddit_score: float  # -1 to 1
    news_score: float  # -1 to 1
    overall: float  # -1 to 1
    sources: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MarketSnapshot:
    """Major index/crypto/volatility snapshot."""

    sp500: PriceData
    btc: PriceData
    vix: PriceData
    gold: PriceData
    dxy: PriceData
    timestamp: datetime


@dataclass(frozen=True)
class FullAnalysis:
    """Complete symbol analysis: price + technical + sentiment."""

    symbol: str
    price: PriceData
    sentiment: SentimentData
    technical: dict[str, Any]
    recommendation: str  # "buy", "sell", "hold"
    confidence: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_timestamp(raw: Any) -> datetime:
    """Parse epoch seconds or ISO string into timezone-aware UTC datetime."""
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw, tz=UTC)
    if isinstance(raw, str):
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    return datetime.now(tz=UTC)


def _parse_price(data: dict[str, Any]) -> PriceData:
    """Build PriceData from MCP response dict."""
    return PriceData(
        symbol=str(data.get("symbol", "")),
        price=float(data.get("price", 0.0)),
        change=float(data.get("change", 0.0)),
        change_pct=float(data.get("change_pct", 0.0)),
        volume=int(data.get("volume", 0)),
        timestamp=_parse_timestamp(data.get("timestamp")),
    )


def _parse_ohlcv(data: dict[str, Any]) -> OHLCVBar:
    """Build OHLCVBar from MCP response dict."""
    return OHLCVBar(
        timestamp=_parse_timestamp(data.get("timestamp")),
        open=float(data.get("open", 0.0)),
        high=float(data.get("high", 0.0)),
        low=float(data.get("low", 0.0)),
        close=float(data.get("close", 0.0)),
        volume=int(data.get("volume", 0)),
    )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class TradingViewClient:
    """TradingView MCP client for market data, screening, backtest, sentiment.

    Supports async context manager usage:

        async with TradingViewClient() as client:
            price = await client.get_price("AAPL")
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self._base_url = (base_url or TV_MCP_URL).rstrip("/")
        self._timeout = timeout or TV_REQUEST_TIMEOUT
        self._max_retries = max_retries if max_retries is not None else TV_MAX_RETRIES
        self._client: httpx.AsyncClient | None = None

    # -- lifecycle -----------------------------------------------------------

    async def __aenter__(self) -> TradingViewClient:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(self._timeout),
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Lazily create the HTTP client if not using context manager."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout),
            )
        return self._client

    # -- http helpers --------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request with retry logic.

        Retries on 5xx and transport errors with exponential backoff.
        Raises ``httpx.HTTPStatusError`` on 4xx after first attempt.
        """
        client = await self._ensure_client()
        last_exc: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                resp = await client.request(method, path, json=json, params=params)
                resp.raise_for_status()
                return resp.json()  # type: ignore[no-any-return]
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                is_retryable = isinstance(exc, httpx.TransportError) or (
                    isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500
                )
                if not is_retryable or attempt == self._max_retries:
                    logger.error(
                        "tv_mcp_request_failed",
                        method=method,
                        path=path,
                        attempt=attempt,
                        error=str(exc),
                    )
                    raise
                backoff = TV_RETRY_BACKOFF * (2 ** (attempt - 1))
                logger.warning(
                    "tv_mcp_retry",
                    method=method,
                    path=path,
                    attempt=attempt,
                    backoff=backoff,
                )
                await asyncio.sleep(backoff)

        raise last_exc  # type: ignore[misc]

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("GET", path, params=params)

    async def _post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._request("POST", path, json=json)

    # -- public api ----------------------------------------------------------

    async def get_market_snapshot(self) -> MarketSnapshot:
        """Get S&P500, BTC, VIX, Gold, DXY snapshot.

        Returns:
            MarketSnapshot with PriceData for each major instrument.
        """
        data = await self._post(
            "/mcp",
            json={
                "tool": "get_market_snapshot",
                "arguments": {},
            },
        )
        result = data.get("result", data)
        return MarketSnapshot(
            sp500=_parse_price(result.get("sp500", {})),
            btc=_parse_price(result.get("btc", {})),
            vix=_parse_price(result.get("vix", {})),
            gold=_parse_price(result.get("gold", {})),
            dxy=_parse_price(result.get("dxy", {})),
            timestamp=_parse_timestamp(result.get("timestamp")),
        )

    async def get_price(self, symbol: str) -> PriceData:
        """Get real-time price for *symbol*.

        Args:
            symbol: Trading symbol (e.g. "AAPL", "BTCUSD", "XAUUSD").

        Returns:
            PriceData with current price, change, volume, and timestamp.
        """
        data = await self._post(
            "/mcp",
            json={
                "tool": "get_price",
                "arguments": {"symbol": symbol},
            },
        )
        return _parse_price(data.get("result", data))

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1D",
        limit: int = 100,
    ) -> list[OHLCVBar]:
        """Get OHLCV candle data for *symbol*.

        Args:
            symbol: Trading symbol.
            timeframe: Candle timeframe (e.g. "1", "5", "15", "60", "1D", "1W").
            limit: Number of bars to return (max depends on server).

        Returns:
            List of OHLCVBar, oldest first.
        """
        data = await self._post(
            "/mcp",
            json={
                "tool": "get_ohlcv",
                "arguments": {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "limit": limit,
                },
            },
        )
        bars_raw = data.get("result", data)
        if isinstance(bars_raw, dict):
            bars_raw = bars_raw.get("bars", bars_raw.get("data", []))
        return [_parse_ohlcv(bar) for bar in bars_raw]

    async def screen_stocks(
        self,
        exchange: str | None = None,
        screener: str = "oversold",
    ) -> list[ScreenResult]:
        """Screen stocks or crypto by signal type.

        Args:
            exchange: Exchange to screen (default: ``TV_SCREEN_EXCHANGE``).
            screener: Signal type — "oversold", "breakout", or "trending".

        Returns:
            List of ScreenResult sorted by score descending.
        """
        data = await self._post(
            "/mcp",
            json={
                "tool": "screen_stocks",
                "arguments": {
                    "exchange": exchange or TV_SCREEN_EXCHANGE,
                    "screener": screener,
                },
            },
        )
        results_raw = data.get("result", data)
        if isinstance(results_raw, dict):
            results_raw = results_raw.get("results", results_raw.get("data", []))
        return [
            ScreenResult(
                symbol=str(r.get("symbol", "")),
                name=str(r.get("name", "")),
                price=float(r.get("price", 0.0)),
                change_pct=float(r.get("change_pct", 0.0)),
                signal=str(r.get("signal", screener)),
                score=float(r.get("score", 0.0)),
            )
            for r in results_raw
        ]

    async def backtest_strategy(
        self,
        symbol: str,
        strategy: str = "rsi",
        timeframe: str | None = None,
        period: str = "1Y",
    ) -> BacktestResult:
        """Run a TradingView built-in strategy backtest.

        Args:
            symbol: Trading symbol.
            strategy: Strategy name — "rsi", "bollinger", "macd", "ema_cross",
                      "supertrend", or "donchian".
            timeframe: Candle timeframe (default: ``TV_DEFAULT_TIMEFRAME``).
            period: Look-back period (e.g. "1M", "3M", "6M", "1Y", "2Y").

        Returns:
            BacktestResult with performance metrics and trade list.
        """
        data = await self._post(
            "/mcp",
            json={
                "tool": "backtest_strategy",
                "arguments": {
                    "symbol": symbol,
                    "strategy": strategy,
                    "timeframe": timeframe or TV_DEFAULT_TIMEFRAME,
                    "period": period,
                },
            },
        )
        result = data.get("result", data)
        return BacktestResult(
            symbol=str(result.get("symbol", symbol)),
            strategy=str(result.get("strategy", strategy)),
            total_trades=int(result.get("total_trades", 0)),
            win_rate=float(result.get("win_rate", 0.0)),
            profit_factor=float(result.get("profit_factor", 0.0)),
            max_drawdown=float(result.get("max_drawdown", 0.0)),
            net_profit=float(result.get("net_profit", 0.0)),
            sharpe_ratio=float(result.get("sharpe_ratio", 0.0)),
            trades=list(result.get("trades", [])),
        )

    async def get_sentiment(self, symbol: str) -> SentimentData:
        """Get Reddit + news sentiment for *symbol*.

        Args:
            symbol: Trading symbol.

        Returns:
            SentimentData with reddit, news, and overall scores (-1 to 1).
        """
        data = await self._post(
            "/mcp",
            json={
                "tool": "get_sentiment",
                "arguments": {"symbol": symbol},
            },
        )
        result = data.get("result", data)
        return SentimentData(
            symbol=str(result.get("symbol", symbol)),
            reddit_score=float(result.get("reddit_score", 0.0)),
            news_score=float(result.get("news_score", 0.0)),
            overall=float(result.get("overall", 0.0)),
            sources=list(result.get("sources", [])),
        )

    async def analyze_symbol(self, symbol: str) -> FullAnalysis:
        """Full analysis: price + technical + sentiment + recommendation.

        Args:
            symbol: Trading symbol.

        Returns:
            FullAnalysis combining price, sentiment, technicals, and a
            buy/sell/hold recommendation with confidence score.
        """
        # Fetch price, sentiment, and technical data concurrently
        price_task = asyncio.create_task(self.get_price(symbol))
        sentiment_task = asyncio.create_task(self.get_sentiment(symbol))
        technical_task = asyncio.create_task(self._get_technical(symbol))

        price, sentiment, technical = await asyncio.gather(price_task, sentiment_task, technical_task)

        # Derive recommendation from sentiment + technical signals
        recommendation, confidence = self._derive_recommendation(sentiment, technical)

        return FullAnalysis(
            symbol=symbol,
            price=price,
            sentiment=sentiment,
            technical=technical,
            recommendation=recommendation,
            confidence=confidence,
        )

    # -- internal helpers ----------------------------------------------------

    async def _get_technical(self, symbol: str) -> dict[str, Any]:
        """Fetch technical indicators for *symbol* from MCP server."""
        data = await self._post(
            "/mcp",
            json={
                "tool": "get_technical",
                "arguments": {"symbol": symbol},
            },
        )
        result = data.get("result", data)
        if isinstance(result, dict):
            return result
        return {}

    @staticmethod
    def _derive_recommendation(
        sentiment: SentimentData,
        technical: dict[str, Any],
    ) -> tuple[str, float]:
        """Derive buy/sell/hold recommendation from sentiment and technicals.

        Scoring:
          - Sentiment overall > 0.3 → bullish signal
          - Sentiment overall < -0.3 → bearish signal
          - Technical RSI < 30 → oversold (bullish)
          - Technical RSI > 70 → overbought (bearish)
          - MACD crossover → directional bias

        Returns:
            Tuple of (recommendation, confidence).
        """
        score = 0.0
        factors = 0

        # Sentiment contribution
        if sentiment.overall > 0.3:
            score += 1.0
        elif sentiment.overall < -0.3:
            score -= 1.0
        factors += 1

        # RSI contribution
        rsi = technical.get("rsi")
        if rsi is not None:
            if rsi < 30:
                score += 1.0
            elif rsi > 70:
                score -= 1.0
            factors += 1

        # MACD contribution
        macd_signal = technical.get("macd_signal")
        if macd_signal == "bullish":
            score += 0.5
        elif macd_signal == "bearish":
            score -= 0.5
        factors += 1

        if factors == 0:
            return "hold", 0.0

        avg = score / factors
        if avg > 0.3:
            rec = "buy"
        elif avg < -0.3:
            rec = "sell"
        else:
            rec = "hold"

        confidence = min(abs(avg), 1.0)
        return rec, round(confidence, 2)
