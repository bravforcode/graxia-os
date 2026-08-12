"""
TradingView API Routes — market data, screening, backtest, sentiment.

Provides REST endpoints that proxy to TradingView's MCP server via
the TradingViewClient, enabling the trading system to fetch real-time
prices, OHLCV data, stock screening, backtesting, and sentiment analysis.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query

from .tv_client import TradingViewClient

logger = structlog.get_logger(__name__)

tv_router = APIRouter(prefix="/tradingview", tags=["tradingview"])


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _get_client() -> TradingViewClient:
    """Create a new TradingViewClient instance.

    Returns a lazily-connected client. Callers should use it as a
    context manager or call ``close()`` when done.
    """
    return TradingViewClient()


# ---------------------------------------------------------------------------
# Market data endpoints
# ---------------------------------------------------------------------------


@tv_router.get("/snapshot")
async def get_market_snapshot() -> dict[str, Any]:
    """Get market snapshot (S&P500, BTC, VIX, Gold, DXY).

    Returns:
        Dict with price data for major indices, crypto, volatility,
        commodities, and the dollar index.
    """
    try:
        async with TradingViewClient() as client:
            snapshot = await client.get_market_snapshot()
            return {
                "sp500": {
                    "symbol": snapshot.sp500.symbol,
                    "price": snapshot.sp500.price,
                    "change": snapshot.sp500.change,
                    "change_pct": snapshot.sp500.change_pct,
                },
                "btc": {
                    "symbol": snapshot.btc.symbol,
                    "price": snapshot.btc.price,
                    "change": snapshot.btc.change,
                    "change_pct": snapshot.btc.change_pct,
                },
                "vix": {
                    "symbol": snapshot.vix.symbol,
                    "price": snapshot.vix.price,
                    "change": snapshot.vix.change,
                    "change_pct": snapshot.vix.change_pct,
                },
                "gold": {
                    "symbol": snapshot.gold.symbol,
                    "price": snapshot.gold.price,
                    "change": snapshot.gold.change,
                    "change_pct": snapshot.gold.change_pct,
                },
                "dxy": {
                    "symbol": snapshot.dxy.symbol,
                    "price": snapshot.dxy.price,
                    "change": snapshot.dxy.change,
                    "change_pct": snapshot.dxy.change_pct,
                },
                "timestamp": snapshot.timestamp.isoformat(),
            }
    except Exception as e:
        logger.error("tv_snapshot_error", error=str(e))
        raise HTTPException(status_code=502, detail=f"TradingView MCP error: {e}")


@tv_router.get("/price/{symbol}")
async def get_price(symbol: str) -> dict[str, Any]:
    """Get real-time price for a symbol.

    Args:
        symbol: Trading symbol (e.g. "AAPL", "BTCUSD", "XAUUSD").

    Returns:
        Dict with price, change, volume, and timestamp.
    """
    try:
        async with TradingViewClient() as client:
            price = await client.get_price(symbol)
            return {
                "symbol": price.symbol,
                "price": price.price,
                "change": price.change,
                "change_pct": price.change_pct,
                "volume": price.volume,
                "timestamp": price.timestamp.isoformat(),
            }
    except Exception as e:
        logger.error("tv_price_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=502, detail=f"TradingView MCP error: {e}")


@tv_router.get("/ohlcv/{symbol}")
async def get_ohlcv(
    symbol: str,
    timeframe: str = Query("1D", description="Candle timeframe (1, 5, 15, 60, 1D, 1W)"),
    limit: int = Query(100, ge=1, le=5000, description="Number of bars"),
) -> dict[str, Any]:
    """Get OHLCV data for a symbol.

    Args:
        symbol: Trading symbol.
        timeframe: Candle timeframe.
        limit: Number of bars to return.

    Returns:
        Dict with list of OHLCV bars.
    """
    try:
        async with TradingViewClient() as client:
            bars = await client.get_ohlcv(symbol, timeframe=timeframe, limit=limit)
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "count": len(bars),
                "bars": [
                    {
                        "timestamp": bar.timestamp.isoformat(),
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                    }
                    for bar in bars
                ],
            }
    except Exception as e:
        logger.error("tv_ohlcv_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=502, detail=f"TradingView MCP error: {e}")


# ---------------------------------------------------------------------------
# Screening endpoints
# ---------------------------------------------------------------------------


@tv_router.get("/screen/{exchange}")
async def screen_stocks(
    exchange: str = "NASDAQ",
    screener: str = Query("oversold", description="Signal type: oversold, breakout, trending"),
) -> dict[str, Any]:
    """Screen stocks or crypto by signal type.

    Args:
        exchange: Exchange to screen (e.g. "NASDAQ", "NYSE", "CRYPTO").
        screener: Signal type — "oversold", "breakout", or "trending".

    Returns:
        Dict with list of screening results.
    """
    try:
        async with TradingViewClient() as client:
            results = await client.screen_stocks(exchange=exchange, screener=screener)
            return {
                "exchange": exchange,
                "screener": screener,
                "count": len(results),
                "results": [
                    {
                        "symbol": r.symbol,
                        "name": r.name,
                        "price": r.price,
                        "change_pct": r.change_pct,
                        "signal": r.signal,
                        "score": r.score,
                    }
                    for r in results
                ],
            }
    except Exception as e:
        logger.error("tv_screen_error", exchange=exchange, error=str(e))
        raise HTTPException(status_code=502, detail=f"TradingView MCP error: {e}")


# ---------------------------------------------------------------------------
# Backtest endpoints
# ---------------------------------------------------------------------------


@tv_router.post("/backtest/{symbol}")
async def backtest_strategy(
    symbol: str,
    strategy: str = Query("rsi", description="Strategy: rsi, bollinger, macd, ema_cross, supertrend, donchian"),
    timeframe: str = Query("1D", description="Candle timeframe"),
    period: str = Query("1Y", description="Look-back period: 1M, 3M, 6M, 1Y, 2Y"),
) -> dict[str, Any]:
    """Run backtest with TradingView's built-in strategies.

    Args:
        symbol: Trading symbol.
        strategy: Strategy name.
        timeframe: Candle timeframe.
        period: Look-back period.

    Returns:
        Dict with backtest performance metrics.
    """
    try:
        async with TradingViewClient() as client:
            result = await client.backtest_strategy(
                symbol=symbol,
                strategy=strategy,
                timeframe=timeframe,
                period=period,
            )
            return {
                "symbol": result.symbol,
                "strategy": result.strategy,
                "total_trades": result.total_trades,
                "win_rate": result.win_rate,
                "profit_factor": result.profit_factor,
                "max_drawdown": result.max_drawdown,
                "net_profit": result.net_profit,
                "sharpe_ratio": result.sharpe_ratio,
                "trades_count": len(result.trades),
            }
    except Exception as e:
        logger.error("tv_backtest_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=502, detail=f"TradingView MCP error: {e}")


# ---------------------------------------------------------------------------
# Sentiment endpoints
# ---------------------------------------------------------------------------


@tv_router.get("/sentiment/{symbol}")
async def get_sentiment(symbol: str) -> dict[str, Any]:
    """Get Reddit + news sentiment for a symbol.

    Args:
        symbol: Trading symbol.

    Returns:
        Dict with reddit, news, and overall sentiment scores (-1 to 1).
    """
    try:
        async with TradingViewClient() as client:
            sentiment = await client.get_sentiment(symbol)
            return {
                "symbol": sentiment.symbol,
                "reddit_score": sentiment.reddit_score,
                "news_score": sentiment.news_score,
                "overall": sentiment.overall,
                "sources": sentiment.sources,
            }
    except Exception as e:
        logger.error("tv_sentiment_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=502, detail=f"TradingView MCP error: {e}")


# ---------------------------------------------------------------------------
# Full analysis endpoint
# ---------------------------------------------------------------------------


@tv_router.get("/analyze/{symbol}")
async def analyze_symbol(symbol: str) -> dict[str, Any]:
    """Full analysis: price + technical + sentiment + recommendation.

    Combines real-time price, technical indicators, and sentiment data
    to produce a buy/sell/hold recommendation with confidence score.

    Args:
        symbol: Trading symbol.

    Returns:
        Dict with price, sentiment, technical data, and recommendation.
    """
    try:
        async with TradingViewClient() as client:
            analysis = await client.analyze_symbol(symbol)
            return {
                "symbol": analysis.symbol,
                "price": {
                    "price": analysis.price.price,
                    "change": analysis.price.change,
                    "change_pct": analysis.price.change_pct,
                    "volume": analysis.price.volume,
                },
                "sentiment": {
                    "reddit_score": analysis.sentiment.reddit_score,
                    "news_score": analysis.sentiment.news_score,
                    "overall": analysis.sentiment.overall,
                },
                "technical": analysis.technical,
                "recommendation": analysis.recommendation,
                "confidence": analysis.confidence,
            }
    except Exception as e:
        logger.error("tv_analyze_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=502, detail=f"TradingView MCP error: {e}")
