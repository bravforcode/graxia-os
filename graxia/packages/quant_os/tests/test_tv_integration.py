"""Tests for TradingView + PixelRAG integration.

Covers TradingViewClient, TradingViewCDP, VisualChartSearch, and TradingOrchestrator
using mocked HTTP/CDP/CLI calls to avoid external dependencies.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysis.visual_search import IndexStats, SearchResult, VisualChartSearch
from api.tv_cdp import PineCompileResult, TradingViewCDP
from api.tv_client import (
    BacktestResult,
    FullAnalysis,
    MarketSnapshot,
    PriceData,
    ScreenResult,
    SentimentData,
    TradingViewClient,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_price(symbol: str = "AAPL", price: float = 150.0) -> PriceData:
    return PriceData(
        symbol=symbol,
        price=price,
        change=1.5,
        change_pct=1.01,
        volume=1_000_000,
        timestamp=datetime.now(tz=UTC),
    )


def _make_sentiment(symbol: str = "AAPL") -> SentimentData:
    return SentimentData(
        symbol=symbol,
        reddit_score=0.3,
        news_score=0.5,
        overall=0.4,
        sources=["reddit", "news"],
    )


def _make_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        sp500=_make_price("SPX", 5000.0),
        btc=_make_price("BTC", 60000.0),
        vix=_make_price("VIX", 15.0),
        gold=_make_price("XAUUSD", 2300.0),
        dxy=_make_price("DXY", 104.0),
        timestamp=datetime.now(tz=UTC),
    )


def _make_screen_result(symbol: str = "AAPL") -> ScreenResult:
    return ScreenResult(
        symbol=symbol,
        name="Apple Inc.",
        price=150.0,
        change_pct=2.5,
        signal="oversold",
        score=0.85,
    )


def _make_backtest(symbol: str = "AAPL", strategy: str = "rsi") -> BacktestResult:
    return BacktestResult(
        symbol=symbol,
        strategy=strategy,
        total_trades=50,
        win_rate=0.6,
        profit_factor=1.8,
        max_drawdown=12.5,
        net_profit=5000.0,
        sharpe_ratio=1.5,
    )


def _make_full_analysis(symbol: str = "AAPL") -> FullAnalysis:
    return FullAnalysis(
        symbol=symbol,
        price=_make_price(symbol),
        sentiment=_make_sentiment(symbol),
        technical={"rsi": 35.0, "macd": 0.5},
        recommendation="buy",
        confidence=0.75,
    )


def _make_search_result() -> SearchResult:
    return SearchResult(
        id="test-001",
        score=0.92,
        image_path=Path("data/visual_tiles/test.png"),
        metadata={"symbol": "AAPL", "type": "chart"},
        snippet="Head and shoulders pattern",
    )


def _make_pine_compile(success: bool = True) -> PineCompileResult:
    return PineCompileResult(
        success=success,
        errors=[] if success else ["Syntax error on line 5"],
        warnings=[],
        script_id="pine-001" if success else "",
    )


def _import_orchestrator():
    """Import TradingOrchestrator using importlib to bypass sys.path conflicts."""
    import importlib
    import importlib.util
    import sys

    # If already importable, use it
    if "core.tv_integration" in sys.modules:
        mod = sys.modules["core.tv_integration"]
        return mod.TradingOrchestrator

    # Find the file directly
    tv_int_path = Path(__file__).resolve().parent.parent / "core" / "tv_integration.py"
    if not tv_int_path.exists():
        raise FileNotFoundError(f"Cannot find {tv_int_path}")

    # Ensure parent package is importable without triggering __init__ chain
    core_pkg_path = tv_int_path.parent

    spec = importlib.util.spec_from_file_location(
        "core.tv_integration",
        str(tv_int_path),
        submodule_search_locations=[str(core_pkg_path)],
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["core.tv_integration"] = mod
    spec.loader.exec_module(mod)
    return mod.TradingOrchestrator


# ===========================================================================
# TestTradingViewClient
# ===========================================================================


class TestTradingViewClient:
    """Test TradingView MCP client."""

    @pytest.mark.asyncio
    async def test_get_price(self):
        """Test get_price returns PriceData."""
        client = TradingViewClient()
        mock_response = {
            "symbol": "AAPL",
            "price": 150.0,
            "change": 1.5,
            "change_pct": 1.01,
            "volume": 1_000_000,
            "timestamp": 1700000000,
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=mock_response):
            result = await client.get_price("AAPL")

        assert isinstance(result, PriceData)
        assert result.symbol == "AAPL"
        assert result.price == 150.0

    @pytest.mark.asyncio
    async def test_get_market_snapshot(self):
        """Test get_market_snapshot returns MarketSnapshot."""
        client = TradingViewClient()
        mock_data = {
            "sp500": {
                "symbol": "SPX",
                "price": 5000,
                "change": 10,
                "change_pct": 0.2,
                "volume": 0,
                "timestamp": 1700000000,
            },
            "btc": {
                "symbol": "BTC",
                "price": 60000,
                "change": 500,
                "change_pct": 0.84,
                "volume": 0,
                "timestamp": 1700000000,
            },
            "vix": {
                "symbol": "VIX",
                "price": 15,
                "change": -0.5,
                "change_pct": -3.2,
                "volume": 0,
                "timestamp": 1700000000,
            },
            "gold": {
                "symbol": "XAUUSD",
                "price": 2300,
                "change": 5,
                "change_pct": 0.22,
                "volume": 0,
                "timestamp": 1700000000,
            },
            "dxy": {
                "symbol": "DXY",
                "price": 104,
                "change": 0.1,
                "change_pct": 0.1,
                "volume": 0,
                "timestamp": 1700000000,
            },
            "timestamp": 1700000000,
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=mock_data):
            result = await client.get_market_snapshot()

        assert isinstance(result, MarketSnapshot)
        assert result.sp500.price == 5000

    @pytest.mark.asyncio
    async def test_screen_stocks(self):
        """Test screen_stocks returns list of ScreenResult."""
        client = TradingViewClient()
        mock_data = {
            "result": [
                {
                    "symbol": "AAPL",
                    "name": "Apple",
                    "price": 150,
                    "change_pct": 2.5,
                    "signal": "oversold",
                    "score": 0.85,
                },
            ]
        }
        with patch.object(client, "_post", new_callable=AsyncMock, return_value=mock_data):
            result = await client.screen_stocks()

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], ScreenResult)
        assert result[0].symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_backtest_strategy(self):
        """Test backtest_strategy returns BacktestResult."""
        client = TradingViewClient()
        mock_data = {
            "symbol": "AAPL",
            "strategy": "rsi",
            "total_trades": 50,
            "win_rate": 0.6,
            "profit_factor": 1.8,
            "max_drawdown": 12.5,
            "net_profit": 5000,
            "sharpe_ratio": 1.5,
            "trades": [],
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=mock_data):
            result = await client.backtest_strategy("AAPL")

        assert isinstance(result, BacktestResult)
        assert result.symbol == "AAPL"
        assert result.win_rate == 0.6

    @pytest.mark.asyncio
    async def test_get_sentiment(self):
        """Test get_sentiment returns SentimentData."""
        client = TradingViewClient()
        mock_data = {
            "symbol": "AAPL",
            "reddit_score": 0.3,
            "news_score": 0.5,
            "overall": 0.4,
            "sources": ["reddit", "news"],
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=mock_data):
            result = await client.get_sentiment("AAPL")

        assert isinstance(result, SentimentData)
        assert result.symbol == "AAPL"
        assert result.overall == 0.4


# ===========================================================================
# TestTradingViewCDP
# ===========================================================================


class TestTradingViewCDP:
    """Test TradingView CDP bridge."""

    @pytest.mark.asyncio
    async def test_connect(self):
        """Test CDP connection."""
        cdp = TradingViewCDP()
        mock_page = AsyncMock()
        mock_browser = AsyncMock()
        mock_browser.new_page.return_value = mock_page
        mock_browser.pages = [mock_page]
        mock_pw_instance = AsyncMock()
        mock_pw_instance.chromium.connect_over_cdp.return_value = mock_browser

        mock_pw_obj = MagicMock()
        mock_pw_obj.start = AsyncMock(return_value=mock_pw_instance)

        with patch("playwright.async_api.async_playwright", return_value=mock_pw_obj):
            result = await cdp.connect()

        assert result is True

    @pytest.mark.asyncio
    async def test_change_symbol(self):
        """Test symbol change."""
        cdp = TradingViewCDP()
        cdp._page = AsyncMock()
        cdp._page.locator.return_value.fill = AsyncMock()
        cdp._page.locator.return_value.press = AsyncMock()
        cdp._page.keyboard = AsyncMock()

        result = await cdp.change_symbol("XAUUSD")
        assert result is True

    @pytest.mark.asyncio
    async def test_draw_support_line(self):
        """Test drawing support line."""
        cdp = TradingViewCDP()
        cdp._page = AsyncMock()
        cdp._page.evaluate = AsyncMock(return_value={"ok": True})

        result = await cdp.draw_support_line(2300.0, color="green")
        assert result is True

    @pytest.mark.asyncio
    async def test_write_pine_script(self):
        """Test Pine Script writing."""
        cdp = TradingViewCDP()
        cdp._page = AsyncMock()
        cdp._page.locator.return_value.click = AsyncMock()
        cdp._page.keyboard = AsyncMock()

        result = await cdp.write_pine_script("//@version=5\nstrategy('test')")
        assert result is True

    @pytest.mark.asyncio
    async def test_compile_pine_script(self):
        """Test Pine Script compilation."""
        cdp = TradingViewCDP()
        cdp._page = AsyncMock()
        cdp._page.locator.return_value.click = AsyncMock()
        cdp._page.evaluate = AsyncMock(return_value=True)
        # Mock the error/warning text extraction
        cdp._page.locator.return_value.inner_text = AsyncMock(return_value="")

        result = await cdp.compile_pine_script()
        assert isinstance(result, PineCompileResult)


# ===========================================================================
# TestVisualChartSearch
# ===========================================================================


class TestVisualChartSearch:
    """Test PixelRAG visual search."""

    @pytest.mark.asyncio
    async def test_search_by_text(self):
        """Test text search."""
        search = VisualChartSearch()
        mock_response_data = {
            "results": [{"id": "001", "score": 0.92, "image_path": "test.png", "metadata": {}, "snippet": "double top"}]
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False

        search._client = mock_client
        results = await search.search_by_text("double top pattern")

        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].score == 0.92

    @pytest.mark.asyncio
    async def test_search_by_image(self):
        """Test image search."""
        search = VisualChartSearch()
        mock_response_data = {
            "results": [{"id": "002", "score": 0.88, "image_path": "chart.png", "metadata": {}, "snippet": ""}]
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False

        search._client = mock_client

        # Create a temp file for the image query
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake image")
            tmp_path = Path(f.name)

        try:
            results = await search.search_by_image(tmp_path)
            assert isinstance(results, list)
            assert len(results) == 1
        finally:
            tmp_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_index_chart(self):
        """Test chart indexing."""
        import tempfile

        search = VisualChartSearch()
        # Create a temp image file
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake image data")
            tmp_path = Path(f.name)

        try:
            result = await search.index_chart(tmp_path, metadata={"symbol": "AAPL"})
            assert result is True
        finally:
            tmp_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_build_index(self):
        """Test index building."""
        search = VisualChartSearch()
        with patch.object(search, "_run_cli", new_callable=AsyncMock, return_value=MagicMock(returncode=0)):
            result = await search.build_index()

        assert result is True

    def test_get_index_stats(self):
        """Test index stats retrieval."""
        search = VisualChartSearch()
        stats = search.get_index_stats()
        assert isinstance(stats, IndexStats)
        assert stats.total_documents >= 0


# ===========================================================================
# TestTradingOrchestrator
# ===========================================================================


class TestTradingOrchestrator:
    """Test integration orchestrator."""

    @pytest.mark.asyncio
    async def test_full_analysis(self):
        """Test full analysis workflow."""
        orchestrator_cls = _import_orchestrator()
        orch = orchestrator_cls()

        mock_analysis = _make_full_analysis("AAPL")
        mock_search_results = [_make_search_result()]
        mock_screen_results = [_make_screen_result("AAPL")]

        orch._tv_client = AsyncMock(
            analyze_symbol=AsyncMock(return_value=mock_analysis),
            screen_stocks=AsyncMock(return_value=mock_screen_results),
        )
        orch._visual_search = AsyncMock(
            search_by_text=AsyncMock(return_value=mock_search_results),
        )

        result = await orch.full_analysis("AAPL")

        assert result.symbol == "AAPL"
        assert result.recommendation == "buy"
        assert result.confidence == 0.75
        assert "tradingview_mcp" in result.sources
        assert len(result.visual_matches) == 1

    @pytest.mark.asyncio
    async def test_auto_backtest_workflow(self):
        """Test auto backtest workflow."""
        orchestrator_cls = _import_orchestrator()
        orch = orchestrator_cls()

        mock_bt = _make_backtest("AAPL", "rsi")

        orch._tv_client = AsyncMock(
            backtest_strategy=AsyncMock(return_value=mock_bt),
        )
        orch._tv_cdp = AsyncMock(
            connect=AsyncMock(return_value=True),
            change_symbol=AsyncMock(return_value=True),
            screenshot_chart=AsyncMock(return_value=Path("test_screenshot.png")),
        )
        orch._visual_search = AsyncMock(
            index_chart=AsyncMock(return_value=True),
        )

        with patch("core.tv_integration.Path.exists", return_value=True):
            result = await orch.auto_backtest_workflow("AAPL", strategy="rsi")

        assert result.symbol == "AAPL"
        assert result.strategy == "rsi"
        assert result.tv_result["win_rate"] == 0.6

    @pytest.mark.asyncio
    async def test_screen_and_analyze(self):
        """Test screen and analyze workflow."""
        orchestrator_cls = _import_orchestrator()
        orch = orchestrator_cls()

        mock_screen = [_make_screen_result("AAPL"), _make_screen_result("MSFT")]
        mock_analysis = _make_full_analysis("AAPL")

        orch._tv_client = AsyncMock(
            screen_stocks=AsyncMock(return_value=mock_screen),
            analyze_symbol=AsyncMock(return_value=mock_analysis),
        )
        orch._visual_search = AsyncMock(
            search_by_text=AsyncMock(return_value=[]),
        )

        results = await orch.screen_and_analyze(exchange="NASDAQ", screener="oversold", top_n=2)

        assert isinstance(results, list)
        assert len(results) == 2
        assert results[0].symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_chart_pattern_search(self):
        """Test chart pattern search."""
        orchestrator_cls = _import_orchestrator()
        orch = orchestrator_cls()
        orch._visual_search = AsyncMock(
            search_by_text=AsyncMock(return_value=[_make_search_result()]),
        )

        results = await orch.chart_pattern_search("head and shoulders")

        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0]["score"] == 0.92

    @pytest.mark.asyncio
    async def test_auto_pine_workflow(self):
        """Test auto Pine Script workflow."""
        orchestrator_cls = _import_orchestrator()
        orch = orchestrator_cls()

        mock_compile = _make_pine_compile(True)
        mock_bt = _make_backtest("AAPL", "custom")

        orch._tv_cdp = AsyncMock(
            connect=AsyncMock(return_value=True),
            change_symbol=AsyncMock(return_value=True),
            write_pine_script=AsyncMock(return_value=True),
            compile_pine_script=AsyncMock(return_value=mock_compile),
            screenshot_chart=AsyncMock(return_value=Path("pine_screenshot.png")),
        )
        orch._tv_client = AsyncMock(
            backtest_strategy=AsyncMock(return_value=mock_bt),
        )
        orch._visual_search = AsyncMock(
            index_chart=AsyncMock(return_value=True),
        )

        with patch("core.tv_integration.Path.exists", return_value=True):
            result = await orch.auto_pine_workflow("AAPL", {"name": "TestRSI", "length": 14})

        assert result.compile_result.success is True
        assert "TestRSI" in result.script
        assert result.indexed is True

    @pytest.mark.asyncio
    async def test_close(self):
        """Test resource cleanup."""
        orchestrator_cls = _import_orchestrator()
        orch = orchestrator_cls()
        orch._tv_client = AsyncMock(close=AsyncMock())
        orch._tv_cdp = AsyncMock(disconnect=AsyncMock())
        orch._visual_search = AsyncMock(close=AsyncMock())

        await orch.close()

        orch._tv_client.close.assert_awaited_once()
        orch._tv_cdp.disconnect.assert_awaited_once()
        orch._visual_search.close.assert_awaited_once()

    def test_generate_pine_script(self):
        """Test Pine Script generation."""
        orchestrator_cls = _import_orchestrator()
        script = orchestrator_cls._generate_pine_script(
            "AAPL", {"name": "MyStrat", "length": 21, "overbought": 80, "oversold": 20}
        )

        assert "MyStrat" in script
        assert "//@version=5" in script
        assert "input.int(21" in script

    def test_compute_divergence(self):
        """Test divergence computation."""
        orchestrator_cls = _import_orchestrator()
        quant = {"win_rate": 0.6, "profit_factor": 1.8, "max_drawdown": 12.0, "sharpe_ratio": 1.5}
        tv = {"win_rate": 0.55, "profit_factor": 1.6, "max_drawdown": 15.0, "sharpe_ratio": 1.3}

        div = orchestrator_cls._compute_divergence(quant, tv)

        assert "win_rate" in div
        assert div["win_rate"]["diff"] == pytest.approx(0.05, abs=0.01)
