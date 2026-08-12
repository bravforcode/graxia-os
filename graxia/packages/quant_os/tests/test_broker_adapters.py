"""Tests for execution/adapters/ — Binance, Paper, and BrokerManager.

All external dependencies (ccxt, MT5, file I/O) are mocked.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from graxia.packages.quant_os.core.enums import OrderStatus
from graxia.packages.quant_os.execution.adapters.base import (
    AccountInfo,
    Order,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_order(
    order_id: str = "ORD-001",
    symbol: str = "BTCUSDT",
    side: str = "BUY",
    quantity: float = 0.01,
) -> Order:
    """Create a minimal Order for testing."""
    return Order(
        order_id=order_id,
        signal_id="SIG-001",
        symbol=symbol,
        asset_class="crypto",
        side=side,
        quantity=quantity,
    )


# ===================================================================
# BinanceAdapter tests
# ===================================================================


class TestBinanceAdapter:
    """Tests for BinanceAdapter via mocked ccxt."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Create a BinanceAdapter with mocked ccxt module."""
        # Create a mock ccxt module with all needed exception types
        mock_ccxt = MagicMock()
        mock_ccxt.AuthenticationError = type("AuthenticationError", (Exception,), {})
        mock_ccxt.InvalidOrder = type("InvalidOrder", (Exception,), {})
        mock_ccxt.InsufficientFunds = type("InsufficientFunds", (Exception,), {})
        mock_ccxt.RateLimitExceeded = type("RateLimitExceeded", (Exception,), {})
        mock_ccxt.NetworkError = type("NetworkError", (Exception,), {})
        mock_ccxt.ExchangeError = type("ExchangeError", (Exception,), {})

        self.mock_exchange = MagicMock()
        mock_ccxt.binance.return_value = self.mock_exchange

        # Patch sys.modules so the binance adapter can import ccxt
        with patch.dict("sys.modules", {"ccxt": mock_ccxt}):
            # Force reimport of the binance module to pick up mocked ccxt
            import graxia.packages.quant_os.execution.adapters.binance as mod

            # Save the original ccxt reference and replace it
            original_ccxt = mod.ccxt
            mod.ccxt = mock_ccxt
            self.mod = mod
            self.mock_ccxt = mock_ccxt

            # Now create the adapter — it will use the mocked ccxt
            self.adapter = mod.BinanceAdapter.__new__(mod.BinanceAdapter)
            self.adapter.name = "BINANCE"
            self.adapter._connected = False
            self.adapter._api_key = "test_key"
            self.adapter._api_secret = "test_secret"
            self.adapter._testnet = False
            self.adapter._default_type = "future"
            self.adapter._exchange = self.mock_exchange
            self.adapter._last_call = 0.0
            self.adapter._order_symbols = {}

            yield

            # Restore original ccxt
            mod.ccxt = original_ccxt

    def test_binance_connect_success(self) -> None:
        """connect() loads markets and returns True on success."""
        self.mock_exchange.load_markets.return_value = {}
        assert self.adapter.connect() is True
        self.mock_exchange.load_markets.assert_called_once()

    def test_binance_connect_auth_failure(self) -> None:
        """connect() raises RuntimeError on AuthenticationError."""
        self.mock_exchange.load_markets.side_effect = self.mock_ccxt.AuthenticationError("bad key")
        with pytest.raises(RuntimeError, match="authentication failed"):
            self.adapter.connect()

    def test_binance_submit_order_success(self) -> None:
        """submit_order returns FILLED OrderResult on success."""
        self.mock_exchange.create_order.return_value = {
            "id": "BIN-123",
            "filled": 0.01,
            "average": 65000.0,
        }
        result = self.adapter.submit_order(_make_order())
        assert result.status == OrderStatus.FILLED
        assert result.broker_id == "BIN-123"
        assert result.filled_quantity == 0.01
        assert result.avg_price == 65000.0

    def test_binance_submit_order_retry(self) -> None:
        """submit_order retries on RateLimitExceeded then succeeds."""
        self.mock_exchange.create_order.side_effect = [
            self.mock_ccxt.RateLimitExceeded("rate limited"),
            {"id": "BIN-456", "filled": 0.01, "average": 65000.0},
        ]
        with patch.object(self.mod, "time") as mock_time:
            mock_time.sleep = MagicMock()
            mock_time.monotonic = MagicMock(return_value=999999.0)
            result = self.adapter.submit_order(_make_order())
        assert result.status == OrderStatus.FILLED
        assert result.broker_id == "BIN-456"

    def test_binance_submit_order_invalid(self) -> None:
        """submit_order returns FAILED on InvalidOrder."""
        self.mock_exchange.create_order.side_effect = self.mock_ccxt.InvalidOrder("bad quantity")
        result = self.adapter.submit_order(_make_order())
        assert result.status == OrderStatus.FAILED
        assert "invalid order" in result.error.lower()

    def test_binance_close_correct_side(self) -> None:
        """close_position determines correct side from position info.

        Fetches position to determine LONG→sell, SHORT→buy.
        """

        # Mock fetch_positions to return a LONG position
        self.mock_exchange.fetch_positions.return_value = [{"symbol": "BTCUSDT", "side": "long", "contracts": 0.01}]
        self.mock_exchange.create_order.return_value = {
            "id": "CLOSE-1",
            "filled": 0.01,
            "average": 65000.0,
        }
        # Patch time to avoid throttle delays
        with patch.object(self.mod, "time") as mock_time:
            mock_time.sleep = MagicMock()
            mock_time.monotonic = MagicMock(return_value=999999.0)
            result = self.adapter.close_position("POS-1", 0.01, symbol="BTCUSDT")
        assert result.status == OrderStatus.FILLED
        # Verify the side was "sell" (LONG position closing)
        call_args = self.mock_exchange.create_order.call_args
        assert call_args[1]["side"] == "sell"
        assert call_args[1]["params"]["closePosition"] is True

    def test_binance_close_short_position(self) -> None:
        """close_position sends 'buy' for SHORT positions."""
        # Mock fetch_positions to return a SHORT position
        self.mock_exchange.fetch_positions.return_value = [{"symbol": "BTCUSDT", "side": "short", "contracts": 0.01}]
        self.mock_exchange.create_order.return_value = {
            "id": "CLOSE-2",
            "filled": 0.01,
            "average": 65000.0,
        }
        with patch.object(self.mod, "time") as mock_time:
            mock_time.sleep = MagicMock()
            mock_time.monotonic = MagicMock(return_value=999999.0)
            result = self.adapter.close_position("POS-2", 0.01, symbol="BTCUSDT")
        assert result.status == OrderStatus.FILLED
        call_args = self.mock_exchange.create_order.call_args
        assert call_args[1]["side"] == "buy"

    def test_binance_throttle(self) -> None:
        """_throttle enforces minimum gap between calls."""
        # First call should not sleep (no previous call)
        self.adapter._last_call = 0.0
        with patch.object(self.mod, "time") as mock_time:
            mock_time.monotonic = MagicMock(return_value=999999.0)
            mock_time.sleep = MagicMock()
            self.adapter._throttle()
            # Second call immediately after — should sleep
            self.adapter._last_call = mock_time.monotonic.return_value
            mock_time.monotonic = MagicMock(return_value=mock_time.monotonic.return_value + 0.1)
            self.adapter._throttle()
            mock_time.sleep.assert_called()

    def test_binance_map_ccxt_status(self) -> None:
        """_map_ccxt_status maps ccxt statuses to OrderStatus correctly."""
        assert self.mod.BinanceAdapter._map_ccxt_status("open") == OrderStatus.SUBMITTED
        assert self.mod.BinanceAdapter._map_ccxt_status("closed") == OrderStatus.FILLED
        assert self.mod.BinanceAdapter._map_ccxt_status("canceled") == OrderStatus.CANCELLED
        assert self.mod.BinanceAdapter._map_ccxt_status("expired") == OrderStatus.CANCELLED
        assert self.mod.BinanceAdapter._map_ccxt_status("unknown") == OrderStatus.FAILED


# ===================================================================
# PaperAdapter tests
# ===================================================================


class TestPaperAdapter:
    """Tests for PaperAdapter (in-memory paper broker)."""

    @pytest.fixture(autouse=True)
    def _patch_config(self):
        """Patch get_config to return a predictable config."""
        mock_config = MagicMock()
        mock_config.paper_initial_capital = 10000.0
        mock_config.paper_slippage_pips = 0.5
        mock_config.paper_commission_per_lot = 3.5
        mock_config.units_per_lot = 100000.0
        with patch(
            "graxia.packages.quant_os.execution.adapters.paper.get_config",
            return_value=mock_config,
        ):
            from graxia.packages.quant_os.execution.adapters.paper import PaperAdapter

            self.adapter = PaperAdapter(initial_capital=10000.0)
            yield

    def test_paper_connect(self) -> None:
        """connect() returns True immediately."""
        assert self.adapter.connect() is True
        assert self.adapter.is_connected

    def test_paper_submit_order(self) -> None:
        """submit_order simulates a fill with realistic pricing."""
        self.adapter.set_price("EURUSD", bid=1.0850, ask=1.0852)
        order = _make_order(symbol="EURUSD", side="BUY", quantity=100000)
        result = self.adapter.submit_order(order)
        assert result.status == OrderStatus.FILLED
        assert result.broker_id.startswith("PAPER_")
        assert result.filled_quantity == 100000
        assert result.avg_price > 0

    def test_paper_cancel_order(self) -> None:
        """cancel_order returns FAILED for unknown order."""
        result = self.adapter.cancel_order("NONEXISTENT")
        assert result.status == OrderStatus.FAILED

    def test_paper_get_positions(self) -> None:
        """get_positions returns open positions after a fill."""
        self.adapter.set_price("EURUSD", bid=1.0850, ask=1.0852)
        order = _make_order(symbol="EURUSD", side="BUY", quantity=100000)
        self.adapter.submit_order(order)
        positions = self.adapter.get_positions()
        assert len(positions) == 1
        assert positions[0]["symbol"] == "EURUSD"
        assert positions[0]["side"] == "BUY"
        assert positions[0]["quantity"] == 100000

    def test_paper_close_position(self) -> None:
        """close_position closes an open position."""
        self.adapter.set_price("EURUSD", bid=1.0850, ask=1.0852)
        order = _make_order(symbol="EURUSD", side="BUY", quantity=100000)
        self.adapter.submit_order(order)
        result = self.adapter.close_position("EURUSD", 100000)
        assert result.status == OrderStatus.FILLED
        assert len(self.adapter.get_positions()) == 0

    def test_paper_get_account_info(self) -> None:
        """get_account_info returns AccountInfo with equity and cash."""
        info = self.adapter.get_account_info()
        assert isinstance(info, AccountInfo)
        assert info.equity == 10000.0
        assert info.cash == 10000.0


# ===================================================================
# BrokerManager tests
# ===================================================================


class TestBrokerManager:
    """Tests for BrokerManager lifecycle and failover."""

    def _run(self, coro):
        """Run an async coroutine in a new event loop."""
        return asyncio.run(coro)

    def test_manager_from_config_paper(self) -> None:
        """from_config with live_trading_enabled=False creates PaperAdapter."""
        mock_config = MagicMock()
        mock_config.live_trading_enabled = False
        with patch("graxia.packages.quant_os.execution.adapters.manager.PaperAdapter") as mock_paper:
            mock_paper.return_value = MagicMock(name="PAPER")
            from graxia.packages.quant_os.execution.adapters.manager import BrokerManager

            manager = BrokerManager.from_config(mock_config)
            assert manager.primary is not None
            assert manager.fallbacks == []

    def test_manager_failover(self) -> None:
        """When primary fails, manager promotes fallback."""
        from graxia.packages.quant_os.execution.adapters.manager import BrokerManager

        primary = MagicMock(name="PRIMARY")
        primary.connect.side_effect = ConnectionError("broker down")
        primary.name = "PRIMARY"

        fallback = MagicMock(name="FALLBACK")
        fallback.connect.return_value = True
        fallback.name = "FALLBACK"

        manager = BrokerManager(primary=primary, fallbacks=[fallback])
        result = self._run(manager.initialize())
        assert result is True
        assert manager.active is fallback

    def test_manager_health_check(self) -> None:
        """health_check returns True when active adapter is healthy."""
        from graxia.packages.quant_os.execution.adapters.manager import BrokerManager

        adapter = MagicMock(name="ADAPTER")
        adapter.connect.return_value = True
        adapter.get_account_info.return_value = AccountInfo(
            equity=10000, cash=10000, margin_used=0, margin_available=10000
        )
        adapter.name = "ADAPTER"

        manager = BrokerManager(primary=adapter, fallbacks=[])
        self._run(manager.initialize())
        result = self._run(manager.health_check())
        assert result is True

    def test_manager_health_check_failover(self) -> None:
        """health_check triggers failover when active adapter raises."""
        from graxia.packages.quant_os.execution.adapters.manager import BrokerManager

        primary = MagicMock(name="PRIMARY")
        primary.connect.return_value = True
        primary.get_account_info.side_effect = RuntimeError("disconnected")
        primary.name = "PRIMARY"

        fallback = MagicMock(name="FALLBACK")
        fallback.connect.return_value = True
        fallback.name = "FALLBACK"

        manager = BrokerManager(primary=primary, fallbacks=[fallback])
        self._run(manager.initialize())
        result = self._run(manager.health_check())
        assert result is True
        assert manager.active is fallback
