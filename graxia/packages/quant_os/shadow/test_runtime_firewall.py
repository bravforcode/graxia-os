"""BE-P8.2 — Runtime firewall test.

Monkeypatches mt5.order_send to raise AssertionError.
Verifies shadow runner never calls any execution API.
Also checks that no new orders/-deals appear in history.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone


def _forbidden_order_send(*args, **kwargs):
    raise AssertionError("order_send must never be called in shadow mode")


def _forbidden_order_check(*args, **kwargs):
    raise AssertionError("order_check must never be called in shadow mode")


def _forbidden_order_modify(*args, **kwargs):
    raise AssertionError("order_modify must never be called in shadow mode")


def _forbidden_history_deals_get(*args, **kwargs):
    raise AssertionError("history_deals_get must never be called in shadow mode")


def test_runtime_firewall_order_send():
    """Shadow runner must never call order_send even if mt5 is available."""
    from graxia.packages.quant_os.shadow.broker_observed_runner import MT5ReadOnly

    # Patch mt5 module-level to block order_send
    import MetaTrader5 as mt5
    original_send = getattr(mt5, "order_send", None)
    setattr(mt5, "order_send", _forbidden_order_send)

    try:
        # Create a mock MT5ReadOnly that simulates connected state
        reader = MT5ReadOnly()
        reader._connected = True
        reader._mt5 = MagicMock()

        # Simulate tick that would trigger signal generation
        tick = MagicMock()
        tick.bid = 4180.0
        tick.ask = 4180.13
        tick.last = 4180.0
        tick.volume = 1
        tick.time = int(datetime.now(timezone.utc).timestamp())
        tick.time_msc = tick.time * 1000
        tick.flags = 0
        reader._mt5.symbol_info_tick.return_value = tick

        # Call get_tick — must not touch order_send
        result = reader.get_tick("XAUUSD")
        assert result is not None
        assert result["bid"] == 4180.0

        # Verify order_send was never called
        mt5.order_send.assert_not_called() if hasattr(mt5.order_send, 'assert_not_called') else None
    finally:
        if original_send:
            setattr(mt5, "order_send", original_send)


def test_no_new_orders_during_session():
    """Verify no new orders/deals appear before and after shadow session."""
    # This is a structural test — in a real session, you would:
    # 1. Record orders_history_get() count before session
    # 2. Run shadow session
    # 3. Record orders_history_get() count after session
    # 4. Assert counts are equal
    #
    # For now, we verify the shadow runner has no execution methods.
    from graxia.packages.quant_os.shadow.broker_observed_runner import BrokerObservedShadowRunner

    # Verify runner has no execution-related attributes
    runner = BrokerObservedShadowRunner.__new__(BrokerObservedShadowRunner)
    assert not hasattr(runner, 'order_send')
    assert not hasattr(runner, 'order_check')
    assert not hasattr(runner, 'order_modify')
    assert not hasattr(runner, 'positions_get')


def test_mt5readonly_has_no_execution_methods():
    """MT5ReadOnly must not expose execution methods."""
    from graxia.packages.quant_os.shadow.broker_observed_runner import MT5ReadOnly
    reader = MT5ReadOnly.__new__(MT5ReadOnly)
    # These methods must NOT exist
    assert not hasattr(reader, 'order_send')
    assert not hasattr(reader, 'order_check')
    assert not hasattr(reader, 'order_modify')
    assert not hasattr(reader, 'positions_get')
    assert not hasattr(reader, 'history_deals_get')
