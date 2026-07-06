"""Comprehensive unit tests for the MT5 adapter and execution layer.

Covers connection management, order submission, position management,
stop-loss management, symbol management, account info, and error handling.
All MetaTrader5 module calls are mocked.
"""

import hashlib
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from graxia.packages.quant_os.core.enums import OrderStatus
from graxia.packages.quant_os.execution.order import Order

# ---------------------------------------------------------------------------
# Helpers – build lightweight MT5-like return objects
# ---------------------------------------------------------------------------


def _make_order_result(
    retcode: int = 10009, comment: str = "OK", ticket: int = 12345, price: float = 1.23456, volume: float = 0.1
) -> Any:
    """Create a mock MT5 trade result object."""
    obj = MagicMock()
    obj.retcode = retcode
    obj.comment = comment
    obj.order = ticket
    obj.price = price
    obj.volume = volume
    return obj


def _make_position(
    ticket: int = 11111,
    symbol: str = "XAUUSD",
    pos_type: int = 0,
    volume: float = 0.1,
    price_open: float = 2300.0,
    profit: float = 50.0,
    sl: float = 2280.0,
    tp: float = 2350.0,
    comment: str = "test",
) -> Any:
    """Create a mock MT5 position object."""
    obj = MagicMock()
    obj.ticket = ticket
    obj.symbol = symbol
    obj.type = pos_type
    obj.volume = volume
    obj.price_open = price_open
    obj.profit = profit
    obj.sl = sl
    obj.tp = tp
    obj.comment = comment
    return obj


def _make_symbol_info(visible: bool = True, filling_mode: int = 5) -> Any:
    """Create a mock MT5 symbol_info object.

    filling_mode bitmask: bit0=FOK(1), bit1=IOC(2), bit2=RETURN(4).
    5 = FOK|RETURN (typical Pepperstone).
    """
    obj = MagicMock()
    obj.visible = visible
    obj.filling_mode = filling_mode
    return obj


def _make_account_info(
    equity: float = 10000.0, balance: float = 9800.0, margin: float = 500.0, margin_free: float = 9500.0
) -> Any:
    obj = MagicMock()
    obj.equity = equity
    obj.balance = balance
    obj.margin = margin
    obj.margin_free = margin_free
    return obj


def _make_order(
    symbol: str = "XAUUSD", side: str = "BUY", quantity: float = 0.1, sl: float | None = None, tp: float | None = None
) -> Order:
    return Order(
        id="test-order-001",
        signal_id="sig-001",
        symbol=symbol,
        asset_class="metals",
        side=side,
        quantity=quantity,
        stop_price=sl,
        take_profit=tp,
    )


def _make_terminal_info() -> Any:
    obj = MagicMock()
    return obj


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_mt5():
    """Patch the MetaTrader5 module used by the adapter."""
    mock = MagicMock()
    mock.TRADE_ACTION_DEAL = 1
    mock.TRADE_ACTION_SLTP = 5
    mock.ORDER_FILLING_FOK = 0
    mock.ORDER_FILLING_IOC = 1
    mock.ORDER_FILLING_RETURN = 2
    mock.ORDER_TYPE_BUY = 0
    mock.ORDER_TYPE_SELL = 1
    return mock


@pytest.fixture
def adapter(mock_mt5):
    """Create an MT5Adapter with mocked MT5 module."""
    with patch.dict("sys.modules", {"MetaTrader5": mock_mt5}):
        # Re-import so the module-level `mt5` variable picks up the mock
        import importlib

        import graxia.packages.quant_os.execution.adapters.mt5 as mt5_mod

        mt5_mod.mt5 = mock_mt5
        importlib.reload(mt5_mod)

        from graxia.packages.quant_os.execution.adapters.mt5 import MT5Adapter

        a = MT5Adapter(login=12345, password="test", server="Test-Server")
        yield a, mock_mt5, mt5_mod
        # Cleanup
        mt5_mod.mt5 = None


def _get_mod(adapter):
    return adapter[2]


# ===================================================================
# 1. CONNECTION MANAGEMENT
# ===================================================================


class TestConnectionManagement:
    def test_connect_success(self, adapter):
        adp, mt5, _ = adapter
        mt5.initialize.return_value = True
        mt5.login.return_value = True
        assert adp.connect() is True
        assert adp.is_connected is True
        mt5.initialize.assert_called_once()
        mt5.login.assert_called_once()

    def test_connect_failure_initialize(self, adapter):
        adp, mt5, _ = adapter
        mt5.initialize.return_value = False
        mt5.last_error.return_value = "Init failed"
        assert adp.connect() is False
        assert adp.is_connected is False

    def test_connect_failure_login(self, adapter):
        adp, mt5, _ = adapter
        mt5.initialize.return_value = True
        mt5.login.return_value = False
        mt5.last_error.return_value = "Login failed"
        assert adp.connect() is False
        assert adp.is_connected is False

    def test_connect_raises_when_mt5_none(self, adapter):
        adp, _, mod = adapter
        mod.mt5 = None
        with pytest.raises(RuntimeError, match="not installed"):
            adp.connect()

    def test_disconnect(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        adp.disconnect()
        mt5.shutdown.assert_called_once()
        assert adp.is_connected is False

    def test_shutdown_alias(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        adp.shutdown()
        mt5.shutdown.assert_called_once()
        assert adp.is_connected is False

    def test_ensure_connected_already_connected(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        adp._ensure_connected()
        mt5.initialize.assert_not_called()

    def test_ensure_connected_reconnects(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = False
        mt5.terminal_info.return_value = None
        mt5.initialize.return_value = True
        mt5.login.return_value = True
        with patch("graxia.packages.quant_os.execution.adapters.mt5.time.sleep"):
            adp._ensure_connected()
        assert adp.is_connected is True

    def test_ensure_connected_all_attempts_fail(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = False
        mt5.terminal_info.return_value = None
        mt5.initialize.return_value = False
        mt5.last_error.return_value = "fail"
        with patch("graxia.packages.quant_os.execution.adapters.mt5.time.sleep"):
            with pytest.raises(ConnectionError, match="reconnect failed"):
                adp._ensure_connected()


# ===================================================================
# 2. ORDER SUBMISSION
# ===================================================================


class TestOrderSubmission:
    def test_submit_order_buy_success(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.symbol_info.return_value = _make_symbol_info()
        mt5.symbol_select.return_value = True
        mt5.order_send.return_value = _make_order_result(retcode=10009, ticket=99999, price=2305.0, volume=0.1)

        order = _make_order(side="BUY")
        result = adp.submit_order(order)

        assert result.status == OrderStatus.FILLED
        assert result.broker_id == "99999"
        assert result.filled_quantity == 0.1
        assert result.avg_price == 2305.0

    def test_submit_order_sell_success(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.symbol_info.return_value = _make_symbol_info()
        mt5.symbol_select.return_value = True
        mt5.order_send.return_value = _make_order_result(retcode=10009, ticket=88888, price=1.0850, volume=0.5)

        order = _make_order(side="SELL", symbol="EURUSD")
        result = adp.submit_order(order)

        assert result.status == OrderStatus.FILLED
        assert result.broker_id == "88888"

    def test_submit_order_with_sl_tp(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.symbol_info.return_value = _make_symbol_info()
        mt5.symbol_select.return_value = True
        mt5.order_send.return_value = _make_order_result(retcode=10009)

        order = _make_order(sl=2280.0, tp=2350.0)
        adp.submit_order(order)

        call_args = mt5.order_send.call_args[0][0]
        assert call_args["sl"] == 2280.0
        assert call_args["tp"] == 2350.0

    def test_submit_order_comment_is_md5_hash(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.symbol_info.return_value = _make_symbol_info()
        mt5.symbol_select.return_value = True
        mt5.order_send.return_value = _make_order_result(retcode=10009)

        order = _make_order()
        adp.submit_order(order)

        call_args = mt5.order_send.call_args[0][0]
        expected_comment = hashlib.md5(order.order_id.encode()).hexdigest()[:8]
        assert call_args["comment"] == expected_comment

    def test_submit_order_fok_filling(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        # filling_mode=1 means only FOK bit set
        mt5.symbol_info.return_value = _make_symbol_info(filling_mode=1)
        mt5.symbol_select.return_value = True
        mt5.order_send.return_value = _make_order_result(retcode=10009)

        order = _make_order()
        adp.submit_order(order)

        call_args = mt5.order_send.call_args[0][0]
        assert call_args["type_filling"] == 0  # FOK

    def test_submit_order_return_filling(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        # filling_mode=4 means RETURN bit set
        mt5.symbol_info.return_value = _make_symbol_info(filling_mode=4)
        mt5.symbol_select.return_value = True
        mt5.order_send.return_value = _make_order_result(retcode=10009)

        order = _make_order()
        adp.submit_order(order)

        call_args = mt5.order_send.call_args[0][0]
        assert call_args["type_filling"] == 2  # RETURN

    def test_submit_order_ioc_filling(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        # filling_mode=2 means only IOC bit set
        mt5.symbol_info.return_value = _make_symbol_info(filling_mode=2)
        mt5.symbol_select.return_value = True
        mt5.order_send.return_value = _make_order_result(retcode=10009)

        order = _make_order()
        adp.submit_order(order)

        call_args = mt5.order_send.call_args[0][0]
        assert call_args["type_filling"] == 1  # IOC

    def test_submit_order_retry_on_invalid_price(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.symbol_info.return_value = _make_symbol_info()
        mt5.symbol_select.return_value = True
        # First two calls return invalid price, third succeeds
        mt5.order_send.side_effect = [
            _make_order_result(retcode=10014, comment="Invalid price"),
            _make_order_result(retcode=10014, comment="Invalid price"),
            _make_order_result(retcode=10009, ticket=77777, price=1.5, volume=0.1),
        ]

        order = _make_order()
        with patch("graxia.packages.quant_os.execution.adapters.mt5.time.sleep"):
            result = adp.submit_order(order)

        assert result.status == OrderStatus.FILLED
        assert mt5.order_send.call_count == 3

    def test_submit_order_max_retries_exceeded(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.symbol_info.return_value = _make_symbol_info()
        mt5.symbol_select.return_value = True
        mt5.order_send.side_effect = [
            _make_order_result(retcode=10014, comment="Invalid price"),
            _make_order_result(retcode=10014, comment="Invalid price"),
            _make_order_result(retcode=10014, comment="Invalid price"),
        ]

        order = _make_order()
        with patch("graxia.packages.quant_os.execution.adapters.mt5.time.sleep"):
            result = adp.submit_order(order)

        assert result.status == OrderStatus.TIMEOUT
        assert "retries exhausted" in result.error

    def test_submit_order_permanent_failure(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.symbol_info.return_value = _make_symbol_info()
        mt5.symbol_select.return_value = True
        # retcode 10013 = insufficient funds (permanent)
        mt5.order_send.return_value = _make_order_result(retcode=10013, comment="Insufficient funds")

        order = _make_order()
        result = adp.submit_order(order)

        assert result.status == OrderStatus.FAILED
        assert "10013" in result.error
        assert mt5.order_send.call_count == 1

    def test_submit_order_none_result_triggers_reconnect(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.symbol_info.return_value = _make_symbol_info()
        mt5.symbol_select.return_value = True
        # First call returns None (connection lost), then reconnect + succeed
        mt5.order_send.side_effect = [
            None,
            _make_order_result(retcode=10009, ticket=55555, price=1.0, volume=0.1),
        ]
        mt5.last_error.return_value = "Connection lost"
        mt5.initialize.return_value = True
        mt5.login.return_value = True

        order = _make_order()
        with patch("graxia.packages.quant_os.execution.adapters.mt5.time.sleep"):
            result = adp.submit_order(order)

        assert result.status == OrderStatus.FILLED
        assert adp._connected is True

    def test_submit_order_symbol_not_visible(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        # Symbol not found
        mt5.symbol_info.return_value = None

        order = _make_order()
        result = adp.submit_order(order)

        assert result.status == OrderStatus.FAILED
        assert "not found" in result.error.lower()

    def test_submit_order_symbol_select_fails(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.symbol_info.return_value = _make_symbol_info(visible=False)
        mt5.symbol_select.return_value = False

        order = _make_order()
        result = adp.submit_order(order)

        assert result.status == OrderStatus.FAILED
        assert "not visible" in result.error.lower()

    def test_submit_order_auto_detect_filling_fallback(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        # filling_mode=0 means no bits set — should default to RETURN
        mt5.symbol_info.return_value = _make_symbol_info(filling_mode=0)
        mt5.symbol_select.return_value = True
        mt5.order_send.return_value = _make_order_result(retcode=10009)

        order = _make_order()
        adp.submit_order(order)

        call_args = mt5.order_send.call_args[0][0]
        assert call_args["type_filling"] == 2  # RETURN fallback

    def test_submit_order_filling_mode_symbol_info_none(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        # symbol_info returns None during filling detection — but then
        # _ensure_symbol_visible would also fail, so test _get_filling_mode directly
        mt5.symbol_info.return_value = None

        # Test the standalone function
        assert mod._get_filling_mode("UNKNOWN") == 2  # RETURN fallback

    def test_submit_order_type_buy_constant(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.symbol_info.return_value = _make_symbol_info()
        mt5.symbol_select.return_value = True
        mt5.order_send.return_value = _make_order_result(retcode=10009)

        order = _make_order(side="BUY")
        adp.submit_order(order)

        call_args = mt5.order_send.call_args[0][0]
        assert call_args["type"] == 0  # _ORDER_TYPE_BUY

    def test_submit_order_type_sell_constant(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.symbol_info.return_value = _make_symbol_info()
        mt5.symbol_select.return_value = True
        mt5.order_send.return_value = _make_order_result(retcode=10009)

        order = _make_order(side="SELL")
        adp.submit_order(order)

        call_args = mt5.order_send.call_args[0][0]
        assert call_args["type"] == 1  # _ORDER_TYPE_SELL

    def test_side_to_order_type_invalid(self, adapter):
        adp, mt5, mod = adapter
        with pytest.raises(ValueError, match="Unknown side"):
            mod._side_to_order_type("HOLD")


# ===================================================================
# 3. POSITION MANAGEMENT
# ===================================================================


class TestPositionManagement:
    def test_get_positions_success(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.positions_get.return_value = [
            _make_position(ticket=111, symbol="XAUUSD", pos_type=0, volume=0.1),
            _make_position(ticket=222, symbol="EURUSD", pos_type=1, volume=0.5),
        ]

        positions = adp.get_positions()
        assert len(positions) == 2
        assert positions[0]["type"] == "BUY"
        assert positions[1]["type"] == "SELL"
        assert positions[0]["ticket"] == 111
        assert positions[1]["volume"] == 0.5

    def test_get_positions_empty(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.positions_get.return_value = None

        positions = adp.get_positions()
        assert positions == []

    def test_get_positions_fields(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.positions_get.return_value = [
            _make_position(
                ticket=111,
                symbol="XAUUSD",
                pos_type=0,
                volume=0.1,
                price_open=2300.0,
                profit=50.0,
                sl=2280.0,
                tp=2350.0,
                comment="test-order",
            )
        ]

        positions = adp.get_positions()
        p = positions[0]
        assert p["ticket"] == 111
        assert p["symbol"] == "XAUUSD"
        assert p["type"] == "BUY"
        assert p["volume"] == 0.1
        assert p["price_open"] == 2300.0
        assert p["profit"] == 50.0
        assert p["sl"] == 2280.0
        assert p["tp"] == 2350.0
        assert p["comment"] == "test-order"

    def test_close_position_success(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.positions_get.return_value = [_make_position(ticket=111, pos_type=0, symbol="XAUUSD")]
        mt5.symbol_info.return_value = _make_symbol_info()
        mt5.order_send.return_value = _make_order_result(retcode=10009, ticket=33333, price=2310.0, volume=0.1)

        result = adp.close_position("111", 0.1, "XAUUSD")
        assert result.status == OrderStatus.FILLED
        assert result.broker_id == "33333"

        # Verify it sent opposite type (SELL to close BUY)
        call_args = mt5.order_send.call_args[0][0]
        assert call_args["type"] == 1  # SELL
        assert call_args["position"] == 111

    def test_close_position_not_found(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.positions_get.return_value = None

        result = adp.close_position("999", 0.1, "XAUUSD")
        assert result.status == OrderStatus.FAILED
        assert "not found" in result.error

    def test_close_position_permanent_failure(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.positions_get.return_value = [_make_position(ticket=111, pos_type=0)]
        mt5.symbol_info.return_value = _make_symbol_info()
        mt5.order_send.return_value = _make_order_result(retcode=10015, comment="Invalid volume")

        result = adp.close_position("111", 0.1, "XAUUSD")
        assert result.status == OrderStatus.FAILED
        assert mt5.order_send.call_count == 1

    def test_close_position_retries_on_none(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.positions_get.return_value = [_make_position(ticket=111, pos_type=0)]
        mt5.symbol_info.return_value = _make_symbol_info()
        mt5.order_send.side_effect = [
            None,
            _make_order_result(retcode=10009, ticket=44444, price=1.0, volume=0.1),
        ]
        mt5.last_error.return_value = "timeout"
        mt5.initialize.return_value = True
        mt5.login.return_value = True

        with patch("graxia.packages.quant_os.execution.adapters.mt5.time.sleep"):
            result = adp.close_position("111", 0.1, "XAUUSD")

        assert result.status == OrderStatus.FILLED

    def test_close_position_retries_exhausted(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.positions_get.return_value = [_make_position(ticket=111, pos_type=0)]
        mt5.symbol_info.return_value = _make_symbol_info()
        mt5.order_send.side_effect = [None, None, None]
        mt5.last_error.return_value = "timeout"
        mt5.initialize.return_value = True
        mt5.login.return_value = True

        with patch("graxia.packages.quant_os.execution.adapters.mt5.time.sleep"):
            result = adp.close_position("111", 0.1, "XAUUSD")

        assert result.status == OrderStatus.TIMEOUT
        assert "retries exhausted" in result.error

    def test_close_position_sell_to_close(self, adapter):
        """Closing a SELL position should send BUY."""
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.positions_get.return_value = [
            _make_position(ticket=222, pos_type=1)  # SELL
        ]
        mt5.symbol_info.return_value = _make_symbol_info()
        mt5.order_send.return_value = _make_order_result(retcode=10009)

        adp.close_position("222", 0.1, "EURUSD")
        call_args = mt5.order_send.call_args[0][0]
        assert call_args["type"] == 0  # BUY to close SELL


# ===================================================================
# 4. STOP-LOSS MANAGEMENT
# ===================================================================


class TestStopLossManagement:
    def test_set_stop_loss_success(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.order_send.return_value = _make_order_result(retcode=10009)

        result = adp.set_stop_loss(111, "XAUUSD", 2280.0)
        assert result is True

        call_args = mt5.order_send.call_args[0][0]
        assert call_args["action"] == 5  # TRADE_ACTION_SLTP
        assert call_args["sl"] == 2280.0
        assert call_args["position"] == 111

    def test_set_stop_loss_with_take_profit(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.order_send.return_value = _make_order_result(retcode=10009)

        result = adp.set_stop_loss(111, "XAUUSD", 2280.0, take_profit=2350.0)
        assert result is True

        call_args = mt5.order_send.call_args[0][0]
        assert call_args["sl"] == 2280.0
        assert call_args["tp"] == 2350.0

    def test_set_stop_loss_failure_permanent(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.order_send.return_value = _make_order_result(retcode=10013, comment="Invalid SL")

        result = adp.set_stop_loss(111, "XAUUSD", 2280.0)
        assert result is False
        assert mt5.order_send.call_count == 1

    def test_set_stop_loss_retries_on_invalid_price(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.order_send.side_effect = [
            _make_order_result(retcode=10014, comment="Invalid price"),
            _make_order_result(retcode=10009),
        ]

        with patch("graxia.packages.quant_os.execution.adapters.mt5.time.sleep"):
            result = adp.set_stop_loss(111, "XAUUSD", 2280.0)

        assert result is True
        assert mt5.order_send.call_count == 2

    def test_set_stop_loss_retries_exhausted(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.order_send.side_effect = [
            _make_order_result(retcode=10014, comment="Invalid price"),
            _make_order_result(retcode=10014, comment="Invalid price"),
            _make_order_result(retcode=10014, comment="Invalid price"),
        ]

        with patch("graxia.packages.quant_os.execution.adapters.mt5.time.sleep"):
            result = adp.set_stop_loss(111, "XAUUSD", 2280.0)

        assert result is False

    def test_set_stop_loss_none_result_reconnects(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.order_send.side_effect = [
            None,
            _make_order_result(retcode=10009),
        ]
        mt5.last_error.return_value = "timeout"
        mt5.initialize.return_value = True
        mt5.login.return_value = True

        with patch("graxia.packages.quant_os.execution.adapters.mt5.time.sleep"):
            result = adp.set_stop_loss(111, "XAUUSD", 2280.0)

        assert result is True

    def test_update_trailing_stop_buy_profitable(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        # Position with current SL at 2280
        mt5.positions_get.return_value = [_make_position(ticket=111, sl=2280.0)]
        mt5.order_send.return_value = _make_order_result(retcode=10009)

        # Current price moved up → new SL should trail up
        result = adp.update_trailing_stop(
            position_ticket=111,
            symbol="XAUUSD",
            side="BUY",
            entry_price=2300.0,
            current_price=2340.0,
            atr_value=10.0,
            trail_multiplier=2.0,
        )
        assert result is True

        call_args = mt5.order_send.call_args[0][0]
        # new_sl = 2340 - (10 * 2) = 2320
        assert call_args["sl"] == 2320.0

    def test_update_trailing_stop_buy_not_profitable(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        # Current SL at 2300
        mt5.positions_get.return_value = [_make_position(ticket=111, sl=2300.0)]

        # Current price is below SL territory → no move
        result = adp.update_trailing_stop(
            position_ticket=111,
            symbol="XAUUSD",
            side="BUY",
            entry_price=2300.0,
            current_price=2290.0,
            atr_value=10.0,
            trail_multiplier=2.0,
        )
        assert result is False

    def test_update_trailing_stop_sell_profitable(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        # Position with SL at 1.1000
        mt5.positions_get.return_value = [_make_position(ticket=222, sl=1.1000)]
        mt5.order_send.return_value = _make_order_result(retcode=10009)

        result = adp.update_trailing_stop(
            position_ticket=222,
            symbol="EURUSD",
            side="SELL",
            entry_price=1.0900,
            current_price=1.0800,
            atr_value=0.0050,
            trail_multiplier=2.0,
        )
        assert result is True

        call_args = mt5.order_send.call_args[0][0]
        # new_sl = 1.0800 + (0.0050 * 2) = 1.0900
        assert call_args["sl"] == 1.09

    def test_update_trailing_stop_atr_negative(self, adapter):
        adp, mt5, _ = adapter
        result = adp.update_trailing_stop(
            position_ticket=111,
            symbol="XAUUSD",
            side="BUY",
            entry_price=2300.0,
            current_price=2340.0,
            atr_value=-5.0,
            trail_multiplier=2.0,
        )
        assert result is False

    def test_update_trailing_stop_unknown_side(self, adapter):
        adp, mt5, _ = adapter
        result = adp.update_trailing_stop(
            position_ticket=111,
            symbol="XAUUSD",
            side="HOLD",
            entry_price=2300.0,
            current_price=2340.0,
            atr_value=10.0,
            trail_multiplier=2.0,
        )
        assert result is False

    def test_update_trailing_stop_position_not_found(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.positions_get.return_value = None

        result = adp.update_trailing_stop(
            position_ticket=999,
            symbol="XAUUSD",
            side="BUY",
            entry_price=2300.0,
            current_price=2340.0,
            atr_value=10.0,
            trail_multiplier=2.0,
        )
        assert result is False

    def test_update_trailing_stop_order_send_fails(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.positions_get.return_value = [_make_position(ticket=111, sl=2280.0)]
        mt5.order_send.return_value = _make_order_result(retcode=10013, comment="fail")

        result = adp.update_trailing_stop(
            position_ticket=111,
            symbol="XAUUSD",
            side="BUY",
            entry_price=2300.0,
            current_price=2340.0,
            atr_value=10.0,
            trail_multiplier=2.0,
        )
        assert result is False

    def test_update_trailing_stop_none_result(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.positions_get.return_value = [_make_position(ticket=111, sl=2280.0)]
        mt5.order_send.return_value = None
        mt5.last_error.return_value = "err"

        result = adp.update_trailing_stop(
            position_ticket=111,
            symbol="XAUUSD",
            side="BUY",
            entry_price=2300.0,
            current_price=2340.0,
            atr_value=10.0,
            trail_multiplier=2.0,
        )
        assert result is False

    def test_set_fixed_atr_stop_buy(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.order_send.return_value = _make_order_result(retcode=10009)

        result = adp.set_fixed_atr_stop(
            position_ticket=111,
            symbol="XAUUSD",
            side="BUY",
            entry_price=2300.0,
            atr_value=10.0,
            atr_multiplier=2.0,
        )
        assert result is True

        call_args = mt5.order_send.call_args[0][0]
        # SL = 2300 - (10 * 2) = 2280
        assert call_args["sl"] == 2280.0

    def test_set_fixed_atr_stop_sell(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.order_send.return_value = _make_order_result(retcode=10009)

        result = adp.set_fixed_atr_stop(
            position_ticket=222,
            symbol="EURUSD",
            side="SELL",
            entry_price=1.0900,
            atr_value=0.0050,
            atr_multiplier=3.0,
        )
        assert result is True

        call_args = mt5.order_send.call_args[0][0]
        # SL = 1.0900 + (0.0050 * 3) = 1.1050
        assert call_args["sl"] == 1.105

    def test_set_fixed_atr_stop_negative_atr(self, adapter):
        adp, mt5, _ = adapter
        result = adp.set_fixed_atr_stop(
            position_ticket=111,
            symbol="XAUUSD",
            side="BUY",
            entry_price=2300.0,
            atr_value=-5.0,
            atr_multiplier=2.0,
        )
        assert result is False

    def test_set_fixed_atr_stop_invalid_side(self, adapter):
        adp, mt5, _ = adapter
        result = adp.set_fixed_atr_stop(
            position_ticket=111,
            symbol="XAUUSD",
            side="HOLD",
            entry_price=2300.0,
            atr_value=10.0,
            atr_multiplier=2.0,
        )
        assert result is False


# ===================================================================
# 5. SYMBOL MANAGEMENT
# ===================================================================


class TestSymbolManagement:
    def test_ensure_symbol_visible_already_visible(self, adapter):
        adp, mt5, mod = adapter
        mt5.symbol_info.return_value = _make_symbol_info(visible=True)
        assert mod._ensure_symbol_visible("XAUUSD") is True
        mt5.symbol_select.assert_not_called()

    def test_ensure_symbol_visible_adds_to_watch(self, adapter):
        adp, mt5, mod = adapter
        mt5.symbol_info.return_value = _make_symbol_info(visible=False)
        mt5.symbol_select.return_value = True

        with patch("graxia.packages.quant_os.execution.adapters.mt5.time.sleep"):
            assert mod._ensure_symbol_visible("XAUUSD") is True

        mt5.symbol_select.assert_called_once_with("XAUUSD", True)

    def test_ensure_symbol_visible_select_fails(self, adapter):
        adp, mt5, mod = adapter
        mt5.symbol_info.return_value = _make_symbol_info(visible=False)
        mt5.symbol_select.return_value = False

        assert mod._ensure_symbol_visible("XAUUSD") is False

    def test_ensure_symbol_visible_not_found(self, adapter):
        adp, mt5, mod = adapter
        mt5.symbol_info.return_value = None

        assert mod._ensure_symbol_visible("FAKE") is False

    def test_ensure_symbol_visible_mt5_none(self, adapter):
        adp, mt5, mod = adapter
        mod.mt5 = None
        assert mod._ensure_symbol_visible("XAUUSD") is False

    def test_get_filling_mode_fok(self, adapter):
        adp, mt5, mod = adapter
        mt5.symbol_info.return_value = _make_symbol_info(filling_mode=1)
        assert mod._get_filling_mode("XAUUSD") == 0  # FOK

    def test_get_filling_mode_ioc(self, adapter):
        adp, mt5, mod = adapter
        mt5.symbol_info.return_value = _make_symbol_info(filling_mode=2)
        assert mod._get_filling_mode("XAUUSD") == 1  # IOC

    def test_get_filling_mode_return(self, adapter):
        adp, mt5, mod = adapter
        mt5.symbol_info.return_value = _make_symbol_info(filling_mode=4)
        assert mod._get_filling_mode("XAUUSD") == 2  # RETURN

    def test_get_filling_mode_fok_return_combined(self, adapter):
        """filling_mode=5 (bit0+bit2) → RETURN takes priority."""
        adp, mt5, mod = adapter
        mt5.symbol_info.return_value = _make_symbol_info(filling_mode=5)
        assert mod._get_filling_mode("XAUUSD") == 2  # RETURN

    def test_get_filling_mode_none_info(self, adapter):
        adp, mt5, mod = adapter
        mt5.symbol_info.return_value = None
        assert mod._get_filling_mode("UNKNOWN") == 2  # RETURN fallback

    def test_get_filling_mode_mt5_none(self, adapter):
        adp, mt5, mod = adapter
        mod.mt5 = None
        assert mod._get_filling_mode("XAUUSD") == 2  # RETURN fallback


# ===================================================================
# 6. ACCOUNT INFO
# ===================================================================


class TestAccountInfo:
    def test_get_account_info_success(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.account_info.return_value = _make_account_info(
            equity=10000.0, balance=9800.0, margin=500.0, margin_free=9500.0
        )

        info = adp.get_account_info()
        assert info.equity == 10000.0
        assert info.cash == 9800.0
        assert info.margin_used == 500.0
        assert info.margin_available == 9500.0

    def test_get_account_info_failure(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.account_info.return_value = None
        mt5.last_error.return_value = "Account not available"

        with pytest.raises(RuntimeError, match="account_info failed"):
            adp.get_account_info()


# ===================================================================
# 7. ERROR HANDLING
# ===================================================================


class TestErrorHandling:
    def test_adapter_is_connected_property(self, adapter):
        adp, _, _ = adapter
        assert adp.is_connected is False
        adp._connected = True
        assert adp.is_connected is True

    def test_adapter_name(self, adapter):
        adp, _, _ = adapter
        assert adp.name == "MT5"

    def test_order_status_success_ticket(self, adapter):
        """When order not found in MT5 open orders, returns UNKNOWN (not FILLED)."""
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.orders_get.return_value = None

        result = adp.get_order_status("12345")
        assert result.status == OrderStatus.UNKNOWN
        assert result.broker_id == "12345"

    def test_order_status_pending(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mock_order = MagicMock()
        mock_order.ticket = 12345
        mt5.orders_get.return_value = [mock_order]

        result = adp.get_order_status("12345")
        assert result.status == OrderStatus.SUBMITTED

    def test_cancel_order_success(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.order_send.return_value = _make_order_result(retcode=10009)

        result = adp.cancel_order("12345")
        assert result.status == OrderStatus.CANCELLED
        assert result.broker_id == "12345"

    def test_cancel_order_failure(self, adapter):
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.order_send.return_value = _make_order_result(retcode=10013, comment="Order not found")

        result = adp.cancel_order("99999")
        assert result.status == OrderStatus.FAILED

    def test_cancel_order_none_result(self, adapter):
        """When cancel_order returns None (connection lost), retries and returns TIMEOUT."""
        adp, mt5, _ = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.order_send.return_value = None
        mt5.last_error.return_value = "Connection lost"

        result = adp.cancel_order("12345")
        assert result.status == OrderStatus.TIMEOUT

    def test_submit_order_action_constants(self, adapter):
        adp, mt5, mod = adapter
        adp._connected = True
        mt5.terminal_info.return_value = _make_terminal_info()
        mt5.symbol_info.return_value = _make_symbol_info()
        mt5.symbol_select.return_value = True
        mt5.order_send.return_value = _make_order_result(retcode=10009)

        order = _make_order()
        adp.submit_order(order)

        call_args = mt5.order_send.call_args[0][0]
        assert call_args["action"] == 1  # TRADE_ACTION_DEAL
        assert call_args["type_time"] == 0  # ORDER_TIME_GTC

    def test_module_constants(self, adapter):
        adp, mt5, mod = adapter
        assert mod._TRADE_ACTION_DEAL == 1
        assert mod._TRADE_ACTION_SLTP == 5
        assert mod._ORDER_FILLING_FOK == 0
        assert mod._ORDER_FILLING_IOC == 1
        assert mod._ORDER_FILLING_RETURN == 2
        assert mod._ORDER_TYPE_BUY == 0
        assert mod._ORDER_TYPE_SELL == 1
        assert mod._RETRIES == 3
        assert mod._RETRY_DELAY == 1.0
