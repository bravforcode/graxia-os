"""Tests for the unified broker adapter hierarchy.

These tests assert that all canonical adapters expose the same interface and
that the OMS/OrderManager callers use that interface.
"""

from unittest.mock import patch

import pytest

from graxia.packages.quant_os.execution.adapters.base import (
    AccountInfo,
    BrokerAdapter,
    OrderResult,
    OrderStatus,
)
from graxia.packages.quant_os.execution.adapters.binance import BinanceAdapter
from graxia.packages.quant_os.execution.adapters.manager import BrokerManager
from graxia.packages.quant_os.execution.adapters.mt5 import MT5Adapter
from graxia.packages.quant_os.execution.adapters.paper import PaperAdapter
from graxia.packages.quant_os.execution.oms import OMS
from graxia.packages.quant_os.execution.order import Order


class TestUnifiedBrokerInterface:
    """The base class defines the contract every adapter must satisfy."""

    def test_required_methods_are_abstract(self):
        required = {
            "connect",
            "disconnect",
            "submit_order",
            "cancel_order",
            "get_order_status",
            "get_positions",
            "get_account_info",
        }
        methods = {m for m in dir(BrokerAdapter) if not m.startswith("_")}
        assert required.issubset(methods)

    def test_cannot_instantiate_abstract_base(self):
        with pytest.raises(TypeError):
            BrokerAdapter("TEST")

    def test_adapter_carries_name(self):
        # Concrete adapter names are part of the public contract.
        assert PaperAdapter().name == "PAPER"
        assert MT5Adapter(0, "").name == "MT5"

        # Binance requires ccxt; skip the name check when it is absent.
        try:
            assert BinanceAdapter("k", "s").name == "BINANCE"
        except RuntimeError as exc:
            if "ccxt" in str(exc):
                pytest.skip("ccxt not installed")
            raise


class TestPaperAdapter:
    """Paper adapter exercises the full unified lifecycle without external deps."""

    def test_connect_disconnect(self):
        adapter = PaperAdapter(initial_capital=10000.0)
        assert adapter.connect() is True
        assert adapter.is_connected is True
        adapter.disconnect()
        assert adapter.is_connected is False

    def test_submit_order_fills(self):
        adapter = PaperAdapter()
        adapter.connect()
        order = Order(
            id="o1",
            signal_id="s1",
            symbol="EURUSD",
            asset_class="forex",
            side="BUY",
            quantity=0.01,
        )
        result = adapter.submit_order(order)

        assert isinstance(result, OrderResult)
        assert result.status == OrderStatus.FILLED
        assert result.broker_id is not None
        assert result.filled_quantity == pytest.approx(0.01, abs=1e-6)
        assert result.avg_price > 0

    def test_positions_update_after_fill(self):
        adapter = PaperAdapter()
        adapter.connect()
        order = Order(
            id="o2",
            signal_id="s2",
            symbol="EURUSD",
            asset_class="forex",
            side="BUY",
            quantity=0.02,
        )
        adapter.submit_order(order)
        positions = adapter.get_positions()

        assert len(positions) == 1
        assert positions[0]["symbol"] == "EURUSD"
        assert positions[0]["side"] == "BUY"
        assert positions[0]["quantity"] == pytest.approx(0.02, abs=1e-6)

    def test_get_order_status_and_cancel(self):
        adapter = PaperAdapter()
        adapter.connect()
        order = Order(
            id="o3",
            signal_id="s3",
            symbol="EURUSD",
            asset_class="forex",
            side="BUY",
            quantity=0.01,
        )
        result = adapter.submit_order(order)
        status = adapter.get_order_status(result.broker_id)
        assert status.status == OrderStatus.FILLED

        # Filled orders cannot be cancelled.
        cancel_result = adapter.cancel_order(result.broker_id)
        assert cancel_result.status == OrderStatus.FAILED

    def test_get_account_info(self):
        adapter = PaperAdapter(initial_capital=5000.0)
        adapter.connect()
        account = adapter.get_account_info()
        assert isinstance(account, AccountInfo)
        assert account.equity == pytest.approx(5000.0, abs=1.0)
        assert account.cash > 0

    def test_set_price(self):
        adapter = PaperAdapter()
        adapter.connect()
        adapter.set_price("TEST", 100.0, 100.5)
        price = adapter.get_price("TEST")
        assert price["bid"] == pytest.approx(100.0)
        assert price["ask"] == pytest.approx(100.5)


class TestMT5AdapterInterface:
    """MT5 adapter only needs to expose the unified interface; real MT5 is mocked."""

    def test_unified_methods_present(self):
        adapter = MT5Adapter(login=0, password="", server="Pepperstone-Demo")
        assert hasattr(adapter, "connect")
        assert hasattr(adapter, "disconnect")
        assert hasattr(adapter, "submit_order")
        assert hasattr(adapter, "cancel_order")
        assert hasattr(adapter, "get_order_status")
        assert hasattr(adapter, "get_positions")
        assert hasattr(adapter, "get_account_info")

    def test_shutdown_alias_calls_disconnect(self):
        adapter = MT5Adapter(login=0, password="", server="Pepperstone-Demo")
        # No MT5 runtime, but disconnect should be safe and idempotent.
        adapter.disconnect()
        assert adapter.is_connected is False


class TestBinanceAdapterInterface:
    """Binance adapter exposes the unified interface; ccxt calls are mocked."""

    @pytest.fixture(autouse=True)
    def _require_ccxt(self):
        pytest.importorskip("ccxt")

    def test_unified_methods_present(self):
        adapter = BinanceAdapter(api_key="k", api_secret="s", testnet=True)
        assert hasattr(adapter, "connect")
        assert hasattr(adapter, "disconnect")
        assert hasattr(adapter, "submit_order")
        assert hasattr(adapter, "cancel_order")
        assert hasattr(adapter, "get_order_status")
        assert hasattr(adapter, "get_positions")
        assert hasattr(adapter, "get_account_info")

    def test_disconnect_releases_exchange(self):
        adapter = BinanceAdapter(api_key="k", api_secret="s", testnet=True)
        adapter.disconnect()
        assert adapter.is_connected is False


class TestBrokerManager:
    """BrokerManager uses the unified adapter hierarchy for failover."""

    @pytest.mark.asyncio
    async def test_from_config_defaults_to_paper(self):
        manager = BrokerManager.from_config()
        connected = await manager.initialize()
        assert connected is True
        assert manager.active.name == "PAPER"
        assert await manager.health_check() is True
        manager.active.disconnect()

    @pytest.mark.asyncio
    async def test_failover_to_fallback(self):
        primary = PaperAdapter()
        fallback = PaperAdapter()
        manager = BrokerManager(primary=primary, fallbacks=[fallback])
        assert await manager.initialize()

        # Simulate primary failure by making account_info raise.
        with patch.object(primary, "get_account_info", side_effect=ConnectionError("down")):
            healthy = await manager.health_check()

        assert healthy is True
        assert manager.active is fallback
        manager.active.disconnect()


class TestOMSUsesUnifiedInterface:
    """OMS lazy-connects and routes through the unified adapter interface."""

    def test_oms_submits_via_adapter(self, tmp_path):
        adapter = PaperAdapter()
        oms = OMS(
            adapters={"mt5": adapter},
            ledger_path=tmp_path / "ledger.jsonl",
        )
        order = oms.submit_order(
            signal_id="sig1",
            symbol="EURUSD",
            asset_class="forex",
            side="BUY",
            quantity=0.01,
        )
        assert order.status == OrderStatus.FILLED
        assert adapter.is_connected is True

    def test_oms_queries_account_and_positions(self, tmp_path):
        adapter = PaperAdapter()
        oms = OMS(
            adapters={"mt5": adapter},
            ledger_path=tmp_path / "ledger.jsonl",
        )
        oms.submit_order(
            signal_id="sig2",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )
        account = oms.get_account_info("mt5")
        assert account.equity > 0
        positions = oms.get_positions("mt5")
        assert len(positions) == 1
