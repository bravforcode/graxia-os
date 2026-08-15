"""Tests for the ShadowAdapter composite (Shadow Mode routing).

Shadow Mode must route DATA calls (price, account info, positions) to the
read-only source and EXECUTION calls (submit/cancel/close/SL) to the paper
adapter — never to the real broker. These tests verify that routing without
needing a live MT5 terminal.
"""

from __future__ import annotations

from graxia.packages.quant_os.core.enums import OrderStatus
from graxia.packages.quant_os.execution.adapters.base import AccountInfo, Order
from graxia.packages.quant_os.execution.adapters.paper import PaperAdapter
from graxia.packages.quant_os.execution.adapters.shadow import ShadowAdapter


class _FakeReadOnlyData:
    """Minimal read-only data source standing in for MT5 (read_only)."""

    def __init__(self) -> None:
        self.connected = False
        self.prices = {"XAUUSD": {"bid": 3300.0, "ask": 3300.5}}

    def connect(self) -> bool:
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.connected = False

    def get_price(self, symbol: str) -> dict[str, float]:
        return self.prices[symbol]

    def get_account_info(self) -> AccountInfo:
        return AccountInfo(equity=50000.0, cash=50000.0, margin_used=0.0, margin_available=50000.0)

    def get_positions(self) -> list[dict]:
        # Real broker book — must NOT leak into ShadowAdapter.get_positions
        return [{"symbol": "EURUSD", "side": "BUY", "volume": 1.0, "avg_price": 1.08}]


def _make_order(symbol: str = "XAUUSD", side: str = "BUY", qty: float = 100.0) -> Order:
    return Order(
        order_id="test-1",
        signal_id="sig-1",
        symbol=symbol,
        asset_class="metals",
        side=side,
        quantity=qty,
    )


def test_shadow_routes_execution_to_paper():
    data = _FakeReadOnlyData()
    paper = PaperAdapter(initial_capital=10000.0)
    shadow = ShadowAdapter(data_adapter=data, exec_adapter=paper)
    assert shadow.connect()
    assert shadow.is_connected

    # Execution hits paper, not the real broker
    result = shadow.submit_order(_make_order())
    assert result.status == OrderStatus.FILLED
    assert result.filled_quantity == 100.0

    # Paper book now has the position
    positions = shadow.get_positions()
    assert len(positions) == 1
    assert positions[0]["symbol"] == "XAUUSD"


def test_shadow_does_not_leak_real_broker_positions():
    data = _FakeReadOnlyData()
    paper = PaperAdapter(initial_capital=10000.0)
    shadow = ShadowAdapter(data_adapter=data, exec_adapter=paper)
    shadow.connect()

    # Real broker has an EURUSD position; shadow must report only the
    # simulated paper book (empty here) — this is the S-1 false-drift fix.
    assert shadow.get_positions() == []


def test_shadow_data_calls_use_read_only_source():
    data = _FakeReadOnlyData()
    paper = PaperAdapter(initial_capital=10000.0)
    shadow = ShadowAdapter(data_adapter=data, exec_adapter=paper)
    shadow.connect()

    # Account info comes from the live source, not the simulated paper equity
    info = shadow.get_account_info()
    assert info.equity == 50000.0

    # Price comes from the live source
    price = shadow.get_price("XAUUSD")
    assert price == {"bid": 3300.0, "ask": 3300.5}


def test_shadow_close_position_routes_to_paper():
    data = _FakeReadOnlyData()
    paper = PaperAdapter(initial_capital=10000.0)
    shadow = ShadowAdapter(data_adapter=data, exec_adapter=paper)
    shadow.connect()
    shadow.submit_order(_make_order())

    result = shadow.close_position(broker_position_id="XAUUSD", volume=100.0, symbol="XAUUSD")
    assert result.status == OrderStatus.FILLED
    assert shadow.get_positions() == []


def test_shadow_uses_per_symbol_contract_size_for_xauusd_fee():
    data = _FakeReadOnlyData()
    paper = PaperAdapter(initial_capital=10000.0)
    shadow = ShadowAdapter(data_adapter=data, exec_adapter=paper)
    shadow.connect()

    # XAUUSD: 100 oz = 1 lot. Fee should be 1 lot * commission (3.5), NOT
    # 0.001 lots (which the old global units_per_lot=100000 would compute).
    result = shadow.submit_order(_make_order(qty=100.0))
    assert result.fee == 3.5


def test_broker_manager_from_config_uses_shadow_adapter():
    from graxia.packages.quant_os.core.config import QuantConfig
    from graxia.packages.quant_os.execution.adapters.manager import BrokerManager

    config = QuantConfig()
    config.shadow_mode = True
    manager = BrokerManager.from_config(config=config)
    assert isinstance(manager.primary, ShadowAdapter)
    # Data source is read-only MT5, execution is paper
    assert manager.primary._data._read_only is True
    assert isinstance(manager.primary._exec, PaperAdapter)
