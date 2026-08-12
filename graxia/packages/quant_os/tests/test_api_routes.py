"""Tests for TradingView + PixelRAG API routes.

Covers /tradingview, /visual, and /cdp endpoints using FastAPI TestClient
with mocked backends to avoid external dependencies.
"""

from __future__ import annotations

import os

# Set required secrets before importing app to avoid RuntimeError
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only")
os.environ.setdefault("ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("POSTGRES_PASSWORD", "test-password")

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from graxia.packages.quant_os.api.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


# ===========================================================================
# TradingView Routes — /api/v1/tradingview
# ===========================================================================


class TestTradingViewRoutes:
    """Test /tradingview endpoints."""

    def test_get_snapshot(self, client):
        """Test GET /tradingview/snapshot."""
        mock_snapshot = MagicMock(
            sp500=MagicMock(symbol="SPX", price=5000, change=10, change_pct=0.2),
            btc=MagicMock(symbol="BTC", price=60000, change=500, change_pct=0.84),
            vix=MagicMock(symbol="VIX", price=15, change=-0.5, change_pct=-3.2),
            gold=MagicMock(symbol="XAUUSD", price=2300, change=5, change_pct=0.22),
            dxy=MagicMock(symbol="DXY", price=104, change=0.1, change_pct=0.1),
            timestamp=datetime.now(tz=UTC),
        )
        with patch("graxia.packages.quant_os.api.tv_routes.TradingViewClient") as MockClient:
            instance = MockClient.return_value.__aenter__.return_value
            instance.get_market_snapshot = AsyncMock(return_value=mock_snapshot)
            resp = client.get("/api/v1/tradingview/snapshot")

        assert resp.status_code == 200
        data = resp.json()
        assert "sp500" in data
        assert "btc" in data
        assert data["sp500"]["price"] == 5000

    def test_get_price(self, client):
        """Test GET /tradingview/price/{symbol}."""
        mock_price = MagicMock(
            symbol="AAPL",
            price=150.0,
            change=1.5,
            change_pct=1.01,
            volume=1000000,
            timestamp=datetime.now(tz=UTC),
        )
        with patch("graxia.packages.quant_os.api.tv_routes.TradingViewClient") as MockClient:
            instance = MockClient.return_value.__aenter__.return_value
            instance.get_price = AsyncMock(return_value=mock_price)
            resp = client.get("/api/v1/tradingview/price/AAPL")

        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "AAPL"
        assert data["price"] == 150.0

    def test_get_ohlcv(self, client):
        """Test GET /tradingview/ohlcv/{symbol}."""
        mock_bars = [
            MagicMock(
                timestamp=datetime.now(tz=UTC),
                open=150,
                high=155,
                low=148,
                close=153,
                volume=1000000,
            ),
        ]
        with patch("graxia.packages.quant_os.api.tv_routes.TradingViewClient") as MockClient:
            instance = MockClient.return_value.__aenter__.return_value
            instance.get_ohlcv = AsyncMock(return_value=mock_bars)
            resp = client.get("/api/v1/tradingview/ohlcv/AAPL?timeframe=1D&limit=10")

        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "AAPL"
        assert data["count"] == 1

    def test_screen_stocks(self, client):
        """Test GET /tradingview/screen/{exchange}."""
        mock_results = [
            MagicMock(
                symbol="AAPL",
                name="Apple",
                price=150,
                change_pct=2.5,
                signal="oversold",
                score=0.85,
            ),
        ]
        with patch("graxia.packages.quant_os.api.tv_routes.TradingViewClient") as MockClient:
            instance = MockClient.return_value.__aenter__.return_value
            instance.screen_stocks = AsyncMock(return_value=mock_results)
            resp = client.get("/api/v1/tradingview/screen/NASDAQ?screener=oversold")

        assert resp.status_code == 200
        data = resp.json()
        assert data["exchange"] == "NASDAQ"
        assert len(data["results"]) == 1

    def test_backtest_strategy(self, client):
        """Test POST /tradingview/backtest/{symbol}."""
        mock_bt = MagicMock(
            symbol="AAPL",
            strategy="rsi",
            total_trades=50,
            win_rate=0.6,
            profit_factor=1.8,
            max_drawdown=12.5,
            net_profit=5000,
            sharpe_ratio=1.5,
            trades=[],
        )
        with patch("graxia.packages.quant_os.api.tv_routes.TradingViewClient") as MockClient:
            instance = MockClient.return_value.__aenter__.return_value
            instance.backtest_strategy = AsyncMock(return_value=mock_bt)
            resp = client.post("/api/v1/tradingview/backtest/AAPL?strategy=rsi")

        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "AAPL"
        assert data["win_rate"] == 0.6

    def test_get_sentiment(self, client):
        """Test GET /tradingview/sentiment/{symbol}."""
        mock_sentiment = MagicMock(
            symbol="AAPL",
            reddit_score=0.3,
            news_score=0.5,
            overall=0.4,
            sources=["reddit", "news"],
        )
        with patch("graxia.packages.quant_os.api.tv_routes.TradingViewClient") as MockClient:
            instance = MockClient.return_value.__aenter__.return_value
            instance.get_sentiment = AsyncMock(return_value=mock_sentiment)
            resp = client.get("/api/v1/tradingview/sentiment/AAPL")

        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "AAPL"
        assert data["overall"] == 0.4

    def test_analyze_symbol(self, client):
        """Test GET /tradingview/analyze/{symbol}."""
        mock_analysis = MagicMock(
            symbol="AAPL",
            price=MagicMock(price=150, change=1.5, change_pct=1.01, volume=1000000),
            sentiment=MagicMock(reddit_score=0.3, news_score=0.5, overall=0.4),
            technical={"rsi": 35.0},
            recommendation="buy",
            confidence=0.75,
        )
        with patch("graxia.packages.quant_os.api.tv_routes.TradingViewClient") as MockClient:
            instance = MockClient.return_value.__aenter__.return_value
            instance.analyze_symbol = AsyncMock(return_value=mock_analysis)
            resp = client.get("/api/v1/tradingview/analyze/AAPL")

        assert resp.status_code == 200
        data = resp.json()
        assert data["recommendation"] == "buy"
        assert data["confidence"] == 0.75


# ===========================================================================
# Visual Search Routes — /api/v1/visual
# ===========================================================================


class TestVisualRoutes:
    """Test /visual endpoints."""

    def test_search_text(self, client):
        """Test POST /visual/search/text."""
        mock_results = [
            MagicMock(
                id="001",
                score=0.92,
                image_path=Path("test.png"),
                metadata={"symbol": "AAPL"},
                snippet="double top",
            ),
        ]
        with patch("graxia.packages.quant_os.api.visual_routes._get_search") as mock_get:
            mock_search = mock_get.return_value
            mock_search.search_by_text = AsyncMock(return_value=mock_results)
            resp = client.post("/api/v1/visual/search/text?query=double+top&n_docs=5")

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["results"][0]["score"] == 0.92

    def test_index_stats(self, client):
        """Test GET /visual/index/stats."""
        mock_stats = MagicMock(
            to_dict=MagicMock(
                return_value={
                    "total_documents": 100,
                    "index_size_mb": 50.0,
                    "last_updated": datetime.now(tz=UTC).isoformat(),
                    "source_types": {"chart": 80, "report": 20},
                }
            ),
        )
        with patch("graxia.packages.quant_os.api.visual_routes._get_search") as mock_get:
            mock_search = mock_get.return_value
            mock_search.get_index_stats = MagicMock(return_value=mock_stats)
            resp = client.get("/api/v1/visual/index/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_documents"] == 100

    def test_build_index(self, client):
        """Test POST /visual/index/build."""
        with patch("graxia.packages.quant_os.api.visual_routes._get_search") as mock_get:
            mock_search = mock_get.return_value
            mock_search.build_index = AsyncMock(return_value=True)
            mock_search.index_dir = Path("data/visual_index")
            resp = client.post("/api/v1/visual/index/build")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "built"

    def test_index_url(self, client):
        """Test POST /visual/index/url."""
        with patch("graxia.packages.quant_os.api.visual_routes._get_search") as mock_get:
            mock_search = mock_get.return_value
            mock_search.index_url = AsyncMock(return_value=True)
            resp = client.post("/api/v1/visual/index/url?url=https://example.com")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "indexed"


# ===========================================================================
# CDP Routes — /api/v1/cdp
# ===========================================================================


class TestCDPRoutes:
    """Test /cdp endpoints."""

    def test_get_symbol(self, client):
        """Test GET /cdp/symbol."""
        with patch("graxia.packages.quant_os.api.cdp_routes._get_cdp") as mock_get:
            mock_cdp = AsyncMock()
            mock_cdp.get_current_symbol = AsyncMock(return_value="XAUUSD")
            mock_cdp.disconnect = AsyncMock()
            mock_get.return_value = mock_cdp
            resp = client.get("/api/v1/cdp/symbol")

        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "XAUUSD"

    def test_change_symbol(self, client):
        """Test POST /cdp/symbol/{symbol}."""
        with patch("graxia.packages.quant_os.api.cdp_routes._get_cdp") as mock_get:
            mock_cdp = AsyncMock()
            mock_cdp.change_symbol = AsyncMock(return_value=True)
            mock_cdp.disconnect = AsyncMock()
            mock_get.return_value = mock_cdp
            resp = client.post("/api/v1/cdp/symbol/BTCUSD")

        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "BTCUSD"

    def test_change_timeframe(self, client):
        """Test POST /cdp/timeframe/{timeframe}."""
        with patch("graxia.packages.quant_os.api.cdp_routes._get_cdp") as mock_get:
            mock_cdp = AsyncMock()
            mock_cdp.change_timeframe = AsyncMock(return_value=True)
            mock_cdp.disconnect = AsyncMock()
            mock_get.return_value = mock_cdp
            resp = client.post("/api/v1/cdp/timeframe/1h")

        assert resp.status_code == 200
        data = resp.json()
        assert data["timeframe"] == "1h"

    def test_draw_support(self, client):
        """Test POST /cdp/draw/support."""
        with patch("graxia.packages.quant_os.api.cdp_routes._get_cdp") as mock_get:
            mock_cdp = AsyncMock()
            mock_cdp.draw_support_line = AsyncMock(return_value=True)
            mock_cdp.disconnect = AsyncMock()
            mock_get.return_value = mock_cdp
            resp = client.post("/api/v1/cdp/draw/support?price=2300.0")

        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "support"
        assert data["price"] == 2300.0

    def test_draw_resistance(self, client):
        """Test POST /cdp/draw/resistance."""
        with patch("graxia.packages.quant_os.api.cdp_routes._get_cdp") as mock_get:
            mock_cdp = AsyncMock()
            mock_cdp.draw_resistance_line = AsyncMock(return_value=True)
            mock_cdp.disconnect = AsyncMock()
            mock_get.return_value = mock_cdp
            resp = client.post("/api/v1/cdp/draw/resistance?price=2500.0")

        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "resistance"
        assert data["price"] == 2500.0

    def test_write_pine(self, client):
        """Test POST /cdp/pine/write."""
        with patch("graxia.packages.quant_os.api.cdp_routes._get_cdp") as mock_get:
            mock_cdp = AsyncMock()
            mock_cdp.write_pine_script = AsyncMock(return_value=True)
            mock_cdp.disconnect = AsyncMock()
            mock_get.return_value = mock_cdp
            resp = client.post("/api/v1/cdp/pine/write?script=//@version=5%0Astrategy('test')")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_compile_pine(self, client):
        """Test POST /cdp/pine/compile."""
        mock_result = MagicMock(
            success=True,
            errors=[],
            warnings=[],
            script_id="pine-001",
        )
        with patch("graxia.packages.quant_os.api.cdp_routes._get_cdp") as mock_get:
            mock_cdp = AsyncMock()
            mock_cdp.compile_pine_script = AsyncMock(return_value=mock_result)
            mock_cdp.disconnect = AsyncMock()
            mock_get.return_value = mock_cdp
            resp = client.post("/api/v1/cdp/pine/compile")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_set_layout(self, client):
        """Test POST /cdp/layout/{layout}."""
        with patch("graxia.packages.quant_os.api.cdp_routes._get_cdp") as mock_get:
            mock_cdp = AsyncMock()
            mock_cdp.set_layout = AsyncMock(return_value=True)
            mock_cdp.disconnect = AsyncMock()
            mock_get.return_value = mock_cdp
            resp = client.post("/api/v1/cdp/layout/2x2")

        assert resp.status_code == 200
        data = resp.json()
        assert data["layout"] == "2x2"

    def test_screenshot_chart(self, client):
        """Test POST /cdp/screenshot."""
        with patch("graxia.packages.quant_os.api.cdp_routes._get_cdp") as mock_get:
            mock_cdp = AsyncMock()
            mock_cdp.screenshot_chart = AsyncMock(return_value=Path("chart.png"))
            mock_cdp.disconnect = AsyncMock()
            mock_get.return_value = mock_cdp
            resp = client.post("/api/v1/cdp/screenshot")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "path" in data
