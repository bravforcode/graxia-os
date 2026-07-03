"""
TradingView + PixelRAG Integration Layer.

Wires TradingView MCP, CDP, and PixelRAG into quant_os workflow for:
  - Full symbol analysis (price + sentiment + visual matches)
  - Auto backtest with cross-validation and screenshot indexing
  - Chart pattern search via visual RAG
  - Screen-then-analyze workflow
  - Auto Pine Script generation → compile → backtest → screenshot → index

Usage::

    orchestrator = TradingOrchestrator()
    insight = await orchestrator.full_analysis("XAUUSD")
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from analysis.visual_search import VisualChartSearch
from api.tv_cdp import PineCompileResult, TradingViewCDP
from api.tv_client import (
    FullAnalysis,
    TradingViewClient,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TradingInsight:
    """Combined insight from all data sources."""

    symbol: str
    price_data: dict[str, Any]
    sentiment: dict[str, Any]
    screening: list[dict[str, Any]]
    visual_matches: list[dict[str, Any]]
    recommendation: str
    confidence: float
    sources: list[str]


@dataclass(frozen=True)
class BacktestComparison:
    """Side-by-side backtest comparison between quant_os and TradingView."""

    symbol: str
    strategy: str
    quant_os_result: dict[str, Any]
    tv_result: dict[str, Any]
    divergence: dict[str, Any]
    screenshot_path: Path | None = None


@dataclass(frozen=True)
class PineWorkflowResult:
    """Result of the auto Pine Script workflow."""

    script: str
    compile_result: PineCompileResult
    backtest_result: dict[str, Any]
    screenshot_path: Path | None = None
    indexed: bool = False


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class TradingOrchestrator:
    """Orchestrates TradingView MCP, CDP, and PixelRAG for complete trading workflow.

    Lifecycle:
        1. Instantiate (clients are lazy-created).
        2. Call async methods — each creates and tears down clients as needed.
        3. Optionally call ``close()`` to release resources early.

    All public async methods are safe to call from an async event loop.
    """

    def __init__(self) -> None:
        self._tv_client: TradingViewClient | None = None
        self._tv_cdp: TradingViewCDP | None = None
        self._visual_search: VisualChartSearch | None = None

    # -- lazy accessors -----------------------------------------------------

    @property
    def tv_client(self) -> TradingViewClient:
        if self._tv_client is None:
            self._tv_client = TradingViewClient()
        return self._tv_client

    @property
    def tv_cdp(self) -> TradingViewCDP:
        if self._tv_cdp is None:
            self._tv_cdp = TradingViewCDP()
        return self._tv_cdp

    @property
    def visual_search(self) -> VisualChartSearch:
        if self._visual_search is None:
            self._visual_search = VisualChartSearch()
        return self._visual_search

    async def close(self) -> None:
        """Release all underlying client resources."""
        if self._tv_client is not None:
            await self._tv_client.close()
        if self._tv_cdp is not None:
            await self._tv_cdp.disconnect()
        if self._visual_search is not None:
            await self._visual_search.close()

    # -- core workflows -----------------------------------------------------

    async def full_analysis(self, symbol: str) -> TradingInsight:
        """Run full analysis using all available data sources.

        Steps:
            1. Get price + sentiment from TradingView MCP.
            2. Get visual matches from PixelRAG.
            3. Combine into TradingInsight.
        """
        logger.info("full_analysis.start", symbol=symbol)
        sources: list[str] = []

        # 1. Price + sentiment from TradingView MCP
        try:
            analysis: FullAnalysis = await self.tv_client.analyze_symbol(symbol)
            price_dict = {
                "price": analysis.price.price,
                "change": analysis.price.change,
                "change_pct": analysis.price.change_pct,
                "volume": analysis.price.volume,
            }
            sentiment_dict = {
                "reddit_score": analysis.sentiment.reddit_score,
                "news_score": analysis.sentiment.news_score,
                "overall": analysis.sentiment.overall,
                "sources": analysis.sentiment.sources,
            }
            recommendation = analysis.recommendation
            confidence = analysis.confidence
            sources.append("tradingview_mcp")
        except Exception as exc:
            logger.warning("full_analysis.tv_failed", symbol=symbol, error=str(exc))
            price_dict = {}
            sentiment_dict = {}
            recommendation = "unknown"
            confidence = 0.0

        # 2. Visual matches from PixelRAG
        visual_matches: list[dict[str, Any]] = []
        try:
            results = await self.visual_search.search_by_text(f"{symbol} chart pattern", n_docs=5)
            visual_matches = [
                {
                    "id": r.id,
                    "score": r.score,
                    "image_path": str(r.image_path),
                    "snippet": r.snippet,
                }
                for r in results
            ]
            if visual_matches:
                sources.append("pixelrag")
        except Exception as exc:
            logger.warning("full_analysis.pixelrag_failed", symbol=symbol, error=str(exc))

        # 3. Screening context (best-effort)
        screening: list[dict[str, Any]] = []
        try:
            screen_results = await self.tv_client.screen_stocks()
            screening = [
                {
                    "symbol": s.symbol,
                    "name": s.name,
                    "price": s.price,
                    "change_pct": s.change_pct,
                    "signal": s.signal,
                    "score": s.score,
                }
                for s in screen_results[:5]
            ]
            if screening:
                sources.append("tradingview_screen")
        except Exception as exc:
            logger.debug("full_analysis.screen_skipped", error=str(exc))

        insight = TradingInsight(
            symbol=symbol,
            price_data=price_dict,
            sentiment=sentiment_dict,
            screening=screening,
            visual_matches=visual_matches,
            recommendation=recommendation,
            confidence=confidence,
            sources=sources,
        )
        logger.info(
            "full_analysis.done",
            symbol=symbol,
            recommendation=recommendation,
            confidence=confidence,
            sources=sources,
        )
        return insight

    async def auto_backtest_workflow(self, symbol: str, strategy: str = "rsi") -> BacktestComparison:
        """Auto backtest: quant_os engine + TradingView cross-validation.

        Steps:
            1. Run TradingView backtest via MCP.
            2. Screenshot chart with results via CDP.
            3. Index screenshot into PixelRAG.
            4. Return comparison.
        """
        logger.info("auto_backtest.start", symbol=symbol, strategy=strategy)

        # 1. TradingView backtest
        try:
            tv_bt = await self.tv_client.backtest_strategy(symbol, strategy=strategy)
            tv_result = {
                "total_trades": tv_bt.total_trades,
                "win_rate": tv_bt.win_rate,
                "profit_factor": tv_bt.profit_factor,
                "max_drawdown": tv_bt.max_drawdown,
                "net_profit": tv_bt.net_profit,
                "sharpe_ratio": tv_bt.sharpe_ratio,
            }
        except Exception as exc:
            logger.error("auto_backtest.tv_failed", error=str(exc))
            tv_result = {"error": str(exc)}

        # 2. Screenshot chart
        screenshot_path: Path | None = None
        try:
            await self.tv_cdp.connect()
            await self.tv_cdp.change_symbol(symbol)
            screenshot_path = await self.tv_cdp.screenshot_chart()
        except Exception as exc:
            logger.warning("auto_backtest.screenshot_failed", error=str(exc))

        # 3. Index screenshot
        if screenshot_path and screenshot_path.exists():
            try:
                await self.visual_search.index_chart(
                    screenshot_path,
                    metadata={"symbol": symbol, "strategy": strategy, "type": "backtest"},
                )
            except Exception as exc:
                logger.warning("auto_backtest.index_failed", error=str(exc))

        # 4. Comparison (quant_os backtest placeholder — requires engine integration)
        quant_os_result: dict[str, Any] = {"note": "quant_os engine backtest requires backtest.engine integration"}

        divergence = self._compute_divergence(quant_os_result, tv_result)

        comparison = BacktestComparison(
            symbol=symbol,
            strategy=strategy,
            quant_os_result=quant_os_result,
            tv_result=tv_result,
            divergence=divergence,
            screenshot_path=screenshot_path,
        )
        logger.info("auto_backtest.done", symbol=symbol, strategy=strategy)
        return comparison

    async def chart_pattern_search(self, pattern_description: str, n_docs: int = 5) -> list[dict[str, Any]]:
        """Search for charts matching a pattern description.

        Steps:
            1. Search PixelRAG by text.
            2. Return matching charts with metadata.
        """
        logger.info("chart_pattern_search", query=pattern_description)
        results = await self.visual_search.search_by_text(pattern_description, n_docs=n_docs)
        return [
            {
                "id": r.id,
                "score": r.score,
                "image_path": str(r.image_path),
                "snippet": r.snippet,
                "metadata": r.metadata,
            }
            for r in results
        ]

    async def screen_and_analyze(
        self,
        exchange: str = "NASDAQ",
        screener: str = "oversold",
        top_n: int = 5,
    ) -> list[TradingInsight]:
        """Screen stocks then analyze top results.

        Steps:
            1. Screen via TradingView MCP.
            2. For top N results, run full_analysis.
            3. Return sorted by confidence (descending).
        """
        logger.info("screen_and_analyze.start", exchange=exchange, screener=screener)

        try:
            screen_results = await self.tv_client.screen_stocks(exchange=exchange, screener=screener)
        except Exception as exc:
            logger.error("screen_and_analyze.screen_failed", error=str(exc))
            return []

        symbols = [s.symbol for s in screen_results[:top_n]]
        insights: list[TradingInsight] = []

        # Run analyses concurrently (bounded by top_n)
        tasks = [self.full_analysis(sym) for sym in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for sym, result in zip(symbols, results, strict=False):
            if isinstance(result, Exception):
                logger.warning("screen_and_analyze.analysis_failed", symbol=sym, error=str(result))
                continue
            insights.append(result)

        # Sort by confidence descending
        insights.sort(key=lambda i: i.confidence, reverse=True)
        logger.info(
            "screen_and_analyze.done",
            exchange=exchange,
            screener=screener,
            analyzed=len(insights),
        )
        return insights

    async def auto_pine_workflow(
        self,
        symbol: str,
        strategy_params: dict[str, Any],
    ) -> PineWorkflowResult:
        """Auto generate Pine Script, compile, backtest, screenshot.

        Steps:
            1. Generate Pine Script from strategy params.
            2. Write to TradingView via CDP.
            3. Compile.
            4. Screenshot result.
            5. Index screenshot into PixelRAG.
        """
        logger.info("auto_pine_workflow.start", symbol=symbol)

        # 1. Generate Pine Script
        script = self._generate_pine_script(symbol, strategy_params)

        # 2. Write + compile via CDP
        compile_result: PineCompileResult
        try:
            await self.tv_cdp.connect()
            await self.tv_cdp.change_symbol(symbol)
            await self.tv_cdp.write_pine_script(script)
            compile_result = await self.tv_cdp.compile_pine_script()
        except Exception as exc:
            logger.error("auto_pine_workflow.cdp_failed", error=str(exc))
            compile_result = PineCompileResult(success=False, errors=[str(exc)])

        # 3. Screenshot
        screenshot_path: Path | None = None
        if compile_result.success:
            try:
                screenshot_path = await self.tv_cdp.screenshot_chart()
            except Exception as exc:
                logger.warning("auto_pine_workflow.screenshot_failed", error=str(exc))

        # 4. Index
        indexed = False
        if screenshot_path and screenshot_path.exists():
            try:
                await self.visual_search.index_chart(
                    screenshot_path,
                    metadata={
                        "symbol": symbol,
                        "strategy_params": strategy_params,
                        "type": "pine_backtest",
                    },
                )
                indexed = True
            except Exception as exc:
                logger.warning("auto_pine_workflow.index_failed", error=str(exc))

        # 5. Backtest result (from TradingView MCP if available)
        backtest_result: dict[str, Any] = {}
        if compile_result.success:
            try:
                bt = await self.tv_client.backtest_strategy(symbol, strategy=strategy_params.get("name", "custom"))
                backtest_result = {
                    "total_trades": bt.total_trades,
                    "win_rate": bt.win_rate,
                    "profit_factor": bt.profit_factor,
                    "max_drawdown": bt.max_drawdown,
                    "net_profit": bt.net_profit,
                    "sharpe_ratio": bt.sharpe_ratio,
                }
            except Exception as exc:
                logger.warning("auto_pine_workflow.backtest_failed", error=str(exc))
                backtest_result = {"error": str(exc)}

        result = PineWorkflowResult(
            script=script,
            compile_result=compile_result,
            backtest_result=backtest_result,
            screenshot_path=screenshot_path,
            indexed=indexed,
        )
        logger.info(
            "auto_pine_workflow.done",
            symbol=symbol,
            compiled=compile_result.success,
            indexed=indexed,
        )
        return result

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _compute_divergence(quant_os: dict[str, Any], tv: dict[str, Any]) -> dict[str, Any]:
        """Compute divergence between two backtest results."""
        if "error" in tv or "note" in quant_os:
            return {"status": "incomplete", "reason": "one or both results unavailable"}

        divergences: dict[str, Any] = {}
        comparable_keys = ["win_rate", "profit_factor", "max_drawdown", "sharpe_ratio"]
        for key in comparable_keys:
            q_val = quant_os.get(key)
            t_val = tv.get(key)
            if q_val is not None and t_val is not None:
                divergences[key] = {
                    "quant_os": q_val,
                    "tradingview": t_val,
                    "diff": round(abs(q_val - t_val), 4),
                }
        return divergences

    @staticmethod
    def _generate_pine_script(symbol: str, strategy_params: dict[str, Any]) -> str:
        """Generate a Pine Script v5 strategy from parameters.

        ponytail: minimal template — upgrade path is a proper Pine codegen.
        """
        name = strategy_params.get("name", "QuantOS_Strategy")
        length = strategy_params.get("length", 14)
        overbought = strategy_params.get("overbought", 70)
        oversold = strategy_params.get("oversold", 30)
        source = strategy_params.get("source", "close")

        return f"""//@version=5
strategy("{name}", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=10)

// Parameters
length = input.int({length}, "RSI Length", minval=1)
overbought = input.int({overbought}, "Overbought", minval=50, maxval=100)
oversold = input.int({oversold}, "Oversold", minval=0, maxval=50)
source = input.{source}("{source.title()}", "Source")

// RSI
rsi = ta.rsi(source, length)

// Entry
if ta.crossover(rsi, oversold)
    strategy.entry("Long", strategy.long)

if ta.crossunder(rsi, overbought)
    strategy.close("Long")

// Plot
plot(rsi, "RSI", color=color.new(color.purple, 0))
hline(overbought, "Overbought", color=color.red)
hline(oversold, "Oversold", color=color.green)
"""
