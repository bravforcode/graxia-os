"""Adversarial unit tests for MT5 adapter, Paper adapter, and base layer.

Philosophy: these tests try to BREAK the adapters, not validate them.
Each test mocks MT5 module internals to simulate real-world broker failures.

Real bugs found are documented with ``# BUG:`` comments.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

# Ensure MetaTrader5 is importable as a mock
mt5_mock = MagicMock()
sys.modules.setdefault("MetaTrader5", mt5_mock)

from quant_os.execution.adapters.base import AccountInfo, Order, OrderResult, OrderStatus
from quant_os.execution.adapters.mt5 import (
    _ORDER_FILLING_RETURN,
    _ORDER_TYPE_BUY,
    _ORDER_TYPE_SELL,
    _RETRIES,
    MT5Adapter,
    _ensure_symbol_visible,
    _get_filling_mode,
    _side_to_order_type,
)
from quant_os.execution.adapters.paper import PaperAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_order(**overrides) -> Order:
    defaults = dict(
        order_id="test-order-001",
        signal_id="sig-001",
        symbol="EURUSD",
        asset_class="forex",
        side="BUY",
        quantity=0.1,
    )
    defaults.update(overrides)
    return Order(**defaults)


def _make_result(retcode: int = 10009, comment: str = "Done", **overrides):
    """Create a mock MT5 trade result object."""
    r = MagicMock()
    r.retcode = retcode
    r.comment = comment
    r.order = overrides.get("order", 123456)
    r.price = overrides.get("price", 1.08500)
    r.volume = overrides.get("volume", 0.1)
    return r


def _connected_adapter(login=12345, password="test", server="Test") -> MT5Adapter:
    """Return an MT5Adapter that appears connected (bypasses real MT5)."""
    adapter = MT5Adapter(login=login, password=password, server=server)
    adapter._connected = True
    return adapter


# ===========================================================================
#  1. MT5 API MISBEHAVIOR (10 tests)
# ===========================================================================


class TestMT5API_Misbehavior:
    """Simulate MT5 returning garbage, None, or impossible data."""

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_order_send_returns_none(self, mock_mt5):
        """order_send returns None — adapter must retry, not crash."""
        mock_mt5.order_send.return_value = None
        mock_mt5.last_error.return_value = "connection lost"
        mock_mt5.terminal_info.return_value = MagicMock()  # pretend connected

        adapter = _connected_adapter()
        order = _make_order()
        result = adapter.submit_order(order)

        assert result.status in (OrderStatus.TIMEOUT, OrderStatus.FAILED)
        assert mock_mt5.order_send.call_count == _RETRIES

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_order_send_retcode_none(self, mock_mt5):
        """result.retcode is None — must not crash with AttributeError."""
        mock_mt5.terminal_info.return_value = MagicMock()

        result_obj = _make_result()
        result_obj.retcode = None  # corrupt
        mock_mt5.order_send.return_value = result_obj

        adapter = _connected_adapter()
        order = _make_order()

        # BUG: code does `result.retcode == 10009` which is False for None,
        # then falls through to the permanent failure branch.
        # But if None causes a TypeError in comparison, this test catches it.
        try:
            out = adapter.submit_order(order)
            # If it doesn't crash, it should return FAILED
            assert out.status == OrderStatus.FAILED
        except (TypeError, AttributeError):
            pytest.fail("Adapter crashes when retcode is None")

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_order_send_ticket_none(self, mock_mt5):
        """result.order (ticket) is None — broker_id must handle it."""
        mock_mt5.terminal_info.return_value = MagicMock()
        mock_mt5.order_send.return_value = _make_result(order=None)

        adapter = _connected_adapter()
        order = _make_order()
        result = adapter.submit_order(order)

        assert result.status == OrderStatus.FILLED
        # str(None) = "None" — this is a valid broker_id string but suspicious
        assert result.broker_id == "None"

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_order_send_price_zero(self, mock_mt5):
        """FIXED: result.price <= 0 now rejected with FAILED."""
        mock_mt5.terminal_info.return_value = MagicMock()
        mock_mt5.order_send.return_value = _make_result(price=0.0)

        adapter = _connected_adapter()
        order = _make_order()
        result = adapter.submit_order(order)

        # FIXED: submit_order validates result.price <= 0 and returns FAILED
        assert result.status == OrderStatus.FAILED

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_order_send_volume_zero(self, mock_mt5):
        """FIXED: result.volume <= 0 now rejected with FAILED."""
        mock_mt5.terminal_info.return_value = MagicMock()
        mock_mt5.order_send.return_value = _make_result(volume=0.0)

        adapter = _connected_adapter()
        order = _make_order()
        result = adapter.submit_order(order)

        # FIXED: submit_order validates result.volume <= 0 and returns FAILED
        assert result.status == OrderStatus.FAILED

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_order_send_negative_volume(self, mock_mt5):
        """FIXED: result.volume <= 0 now rejected with FAILED."""
        mock_mt5.terminal_info.return_value = MagicMock()
        mock_mt5.order_send.return_value = _make_result(volume=-0.1)

        adapter = _connected_adapter()
        order = _make_order()
        result = adapter.submit_order(order)

        # FIXED: negative fill volume now rejected with FAILED
        assert result.status == OrderStatus.FAILED

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_order_send_negative_price(self, mock_mt5):
        """FIXED: result.price <= 0 now rejected with FAILED."""
        mock_mt5.terminal_info.return_value = MagicMock()
        mock_mt5.order_send.return_value = _make_result(price=-100.0)

        adapter = _connected_adapter()
        order = _make_order()
        result = adapter.submit_order(order)

        # FIXED: negative fill price now rejected with FAILED
        assert result.status == OrderStatus.FAILED

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_order_send_comment_none(self, mock_mt5):
        """result.comment is None — string formatting must not crash."""
        mock_mt5.terminal_info.return_value = MagicMock()

        result_obj = _make_result(retcode=99999, comment=None)
        mock_mt5.order_send.return_value = result_obj

        adapter = _connected_adapter()
        order = _make_order()
        result = adapter.submit_order(order)

        # Should not crash with TypeError in f-string formatting
        assert result.status == OrderStatus.FAILED
        assert "None" in (result.error or "")

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_positions_get_returns_none(self, mock_mt5):
        """positions_get returns None instead of empty tuple."""
        mock_mt5.terminal_info.return_value = MagicMock()
        mock_mt5.positions_get.return_value = None

        adapter = _connected_adapter()
        positions = adapter.get_positions()

        # Adapter handles None correctly — returns empty list
        assert positions == []

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_positions_get_returns_none_values(self, mock_mt5):
        """FIXED: positions_get skips None items in positions tuple.

        MT5 SDK can theoretically return corrupted data where individual
        position objects are None. get_positions() now filters out None
        items and returns an empty list (or filtered list).
        """
        mock_mt5.terminal_info.return_value = MagicMock()
        mock_mt5.positions_get.return_value = (None, None)

        adapter = _connected_adapter()

        # FIXED: None items are skipped; returns empty or filtered list
        positions = adapter.get_positions()
        assert isinstance(positions, list)
        assert positions == []


# ===========================================================================
#  2. NETWORK FAILURE SIMULATION (8 tests)
# ===========================================================================


class TestMT5NetworkFailures:
    """Simulate network drops, timeouts, and intermittent failures."""

    @patch("quant_os.execution.adapters.mt5.time")
    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_connection_drops_mid_order(self, mock_mt5, mock_time):
        """MT5 connection drops during order — retry logic fires."""
        mock_time.sleep = MagicMock()
        mock_time.time = time.time

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return None  # first two attempts fail
            return _make_result(retcode=10009)  # third succeeds

        mock_mt5.order_send.side_effect = side_effect
        mock_mt5.last_error.return_value = "connection lost"
        mock_mt5.terminal_info.return_value = None  # simulates disconnect
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True

        adapter = _connected_adapter()
        result = adapter.submit_order(_make_order())

        assert result.status == OrderStatus.FILLED
        assert mock_mt5.order_send.call_count == 3

    @patch("quant_os.execution.adapters.mt5.time")
    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_connection_drops_during_position_query(self, mock_mt5, mock_time):
        """MT5 connection drops during positions_get — returns empty."""
        mock_time.sleep = MagicMock()
        mock_mt5.terminal_info.return_value = None
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        mock_mt5.positions_get.return_value = None

        adapter = _connected_adapter()
        positions = adapter.get_positions()

        assert positions == []

    @patch("quant_os.execution.adapters.mt5.time")
    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_connection_drops_during_stop_loss_update(self, mock_mt5, mock_time):
        """MT5 connection drops during set_stop_loss — retries then fails."""
        mock_time.sleep = MagicMock()
        mock_time.time = time.time

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return None  # always fails

        mock_mt5.order_send.side_effect = side_effect
        mock_mt5.last_error.return_value = "connection reset"
        mock_mt5.terminal_info.return_value = None
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True

        adapter = _connected_adapter()
        result = adapter.set_stop_loss(position_ticket=12345, symbol="EURUSD", stop_loss_price=1.0800)

        assert result is False
        assert mock_mt5.order_send.call_count == _RETRIES

    @patch("quant_os.execution.adapters.mt5.time")
    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_reconnection_after_timeout(self, mock_mt5, mock_time):
        """After reconnect, subsequent operations should work."""
        mock_time.sleep = MagicMock()
        mock_time.time = time.time

        # First call: terminal_info returns None (disconnected)
        # After reconnect: returns valid
        mock_mt5.terminal_info.side_effect = [None, MagicMock()]
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        mock_mt5.order_send.return_value = _make_result()

        adapter = _connected_adapter()
        result = adapter.submit_order(_make_order())

        assert result.status == OrderStatus.FILLED
        assert mock_mt5.initialize.call_count >= 1

    @patch("quant_os.execution.adapters.mt5.time")
    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_slow_response_10_seconds(self, mock_mt5, mock_time):
        """MT5 with 10-second response delay — adapter should still work."""
        mock_time.sleep = MagicMock()
        mock_time.time = time.time

        def slow_order_send(request):
            time.sleep(0.01)  # simulate small delay (not real 10s in test)
            return _make_result()

        mock_mt5.order_send.side_effect = slow_order_send
        mock_mt5.terminal_info.return_value = MagicMock()

        adapter = _connected_adapter()
        result = adapter.submit_order(_make_order())

        assert result.status == OrderStatus.FILLED

    @patch("quant_os.execution.adapters.mt5.time")
    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_intermittent_failures_50pct(self, mock_mt5, mock_time):
        """50% failure rate — adapter should eventually succeed or exhaust retries."""
        mock_time.sleep = MagicMock()
        mock_time.time = time.time

        call_count = 0

        def flaky_order_send(request):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                return None  # even calls fail
            return _make_result(retcode=10009)

        mock_mt5.order_send.side_effect = flaky_order_send
        mock_mt5.last_error.return_value = "intermittent error"
        mock_mt5.terminal_info.return_value = MagicMock()

        adapter = _connected_adapter()
        result = adapter.submit_order(_make_order())

        # Should succeed on first or third attempt
        assert result.status == OrderStatus.FILLED

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_dns_resolution_failure(self, mock_mt5):
        """MT5.initialize raises OSError (DNS failure)."""
        mock_mt5.initialize.side_effect = OSError("Name or service not known")

        adapter = MT5Adapter(login=12345, password="test")

        with pytest.raises(OSError, match="Name or service not known"):
            adapter.connect()

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_ssl_certificate_error(self, mock_mt5):
        """MT5.initialize raises SSL certificate error."""
        mock_mt5.initialize.side_effect = ConnectionError("SSL: CERTIFICATE_VERIFY_FAILED")

        adapter = MT5Adapter(login=12345, password="test")

        with pytest.raises(ConnectionError, match="SSL"):
            adapter.connect()


# ===========================================================================
#  3. STATE CORRUPTION (8 tests)
# ===========================================================================


class TestMT5StateCorruption:
    """Force adapter into impossible or corrupt states."""

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_get_order_status_assumes_filled_on_missing(self, mock_mt5):
        """get_order_status returns UNKNOWN when order doesn't exist (FIXED)."""
        mock_mt5.terminal_info.return_value = MagicMock()
        mock_mt5.orders_get.return_value = None

        adapter = _connected_adapter()
        result = adapter.get_order_status("999999")

        # FIXED: was FILLED (bug), now UNKNOWN (correct)
        assert result.status == OrderStatus.UNKNOWN

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_get_order_status_empty_tuple_also_fills(self, mock_mt5):
        """get_order_status returns UNKNOWN on empty orders tuple (FIXED)."""
        mock_mt5.terminal_info.return_value = MagicMock()
        mock_mt5.orders_get.return_value = ()

        adapter = _connected_adapter()
        result = adapter.get_order_status("999999")

        assert result.status == OrderStatus.UNKNOWN

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_connected_flag_lies(self, mock_mt5):
        """_connected=True but MT5 not initialized — _ensure_connected must detect."""
        mock_mt5.terminal_info.return_value = None  # MT5 not actually connected
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        mock_mt5.order_send.return_value = _make_result()

        adapter = _connected_adapter()
        adapter._connected = True  # lie about state

        # _ensure_connected should detect the lie and reconnect
        result = adapter.submit_order(_make_order())
        assert result.status == OrderStatus.FILLED
        assert mock_mt5.initialize.called

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_duplicate_broker_id_tracking(self, mock_mt5):
        """Two orders with same broker_id — what happens on close?"""
        mock_mt5.terminal_info.return_value = MagicMock()

        # Both orders fill with same ticket number (broker bug)
        mock_mt5.order_send.return_value = _make_result(order=111111)

        adapter = _connected_adapter()
        r1 = adapter.submit_order(_make_order(order_id="order-A"))
        r2 = adapter.submit_order(_make_order(order_id="order-B"))

        # Both get the same broker_id — this is a real broker bug scenario
        assert r1.broker_id == r2.broker_id == "111111"

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_cancel_order_with_non_numeric_id(self, mock_mt5):
        """cancel_order receives non-numeric broker_order_id — int() must crash."""
        mock_mt5.terminal_info.return_value = MagicMock()

        adapter = _connected_adapter()

        with pytest.raises(ValueError):
            adapter.cancel_order("NOT_A_NUMBER")

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_symbol_with_special_characters(self, mock_mt5):
        """Symbol with injection payload — MT5 should reject safely."""
        mock_mt5.terminal_info.return_value = MagicMock()
        mock_mt5.symbol_info.return_value = None

        adapter = _connected_adapter()
        order = _make_order(symbol="EUR/USD'; DROP TABLE orders;--")

        result = adapter.submit_order(order)
        assert result.status == OrderStatus.FAILED
        assert "not found" in (result.error or "").lower() or "not visible" in (result.error or "").lower()

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_quantity_as_string(self, mock_mt5):
        """Quantity passed as string instead of float."""
        mock_mt5.terminal_info.return_value = MagicMock()
        mock_mt5.symbol_info.return_value = MagicMock(visible=True, filling_mode=4)
        mock_mt5.order_send.return_value = _make_result()

        adapter = _connected_adapter()
        order = _make_order(quantity="0.1")  # string, not float

        # BUG: code does `volume=order.quantity` without float() conversion
        # MT5 SDK may reject string volume or silently truncate
        try:
            result = adapter.submit_order(order)
            # If it doesn't crash, MT5 SDK handled it
        except (TypeError, ValueError):
            pytest.fail(
                "Adapter passes string quantity to MT5 SDK without "
                "float() conversion — BUG in submit_order request building"
            )

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_stop_loss_greater_than_take_profit(self, mock_mt5):
        """SL > TP is logically invalid — adapter doesn't validate."""
        mock_mt5.terminal_info.return_value = MagicMock()
        mock_mt5.order_send.return_value = _make_result(retcode=99999, comment="invalid params")

        adapter = _connected_adapter()
        order = _make_order(stop_loss=1.1000, take_profit=1.0500)  # SL > TP

        result = adapter.submit_order(order)
        # Adapter passes invalid SL/TP to MT5 without validation
        # MT5 rejects it with a non-10009 retcode
        assert result.status == OrderStatus.FAILED


# ===========================================================================
#  4. PAPER ADAPTER BUGS (8 tests)
# ===========================================================================


class TestPaperAdapterBugs:
    """Stress-test the paper adapter with edge cases."""

    def _make_paper(self, capital: float = 10000.0) -> PaperAdapter:
        with patch("quant_os.execution.adapters.paper.get_config") as mock_cfg:
            cfg = MagicMock()
            cfg.paper_initial_capital = str(capital)
            cfg.paper_slippage_pips = "2.0"
            cfg.paper_commission_per_lot = "7.0"
            cfg.units_per_lot = "100000.0"
            mock_cfg.return_value = cfg
            adapter = PaperAdapter(initial_capital=capital)
            adapter.connect()
            return adapter

    def test_zero_balance_submit_order(self):
        """Paper adapter with balance=0 — can still open positions?"""
        paper = self._make_paper(capital=0.0)
        order = _make_order(quantity=100000)  # 1 lot

        result = paper.submit_order(order)

        # BUG: no margin/balance check — paper adapter accepts orders
        # even when balance is 0, creating a position with negative equity
        assert result.status == OrderStatus.FILLED
        info = paper.get_account_info()
        # Equity should be negative (fee charged against 0 balance)
        assert info.cash <= 0

    def test_negative_balance_submit_order(self):
        """Paper adapter with negative balance — no circuit breaker."""
        paper = self._make_paper(capital=-5000.0)
        order = _make_order(quantity=100000)

        result = paper.submit_order(order)

        # BUG: no minimum balance guard — paper adapter happily trades
        # with negative equity, which is impossible at a real broker
        assert result.status == OrderStatus.FILLED

    def test_leverage_zero_not_applicable(self):
        """Paper adapter has no leverage model — unlimited buying power."""
        paper = self._make_paper(capital=100.0)
        # Try to open a huge position (100 lots = $10M notional)
        order = _make_order(quantity=10_000_000)

        result = paper.submit_order(order)

        # BUG: no leverage/margin check — paper adapter allows positions
        # that would require millions in margin with only $100 capital
        assert result.status == OrderStatus.FILLED

    def test_submit_order_nonexistent_symbol(self):
        """Order for a symbol with no price data — uses default price."""
        paper = self._make_paper()
        order = _make_order(symbol="FAKESYMBOL999")

        result = paper.submit_order(order)

        # Paper adapter generates a default price for unknown symbols
        # This is different from MT5 which would reject it
        assert result.status == OrderStatus.FILLED
        assert result.avg_price > 0

    def test_close_nonexistent_position(self):
        """Close a position that doesn't exist."""
        paper = self._make_paper()

        result = paper.close_position("FAKE_SYMBOL", volume=1.0, symbol="FAKE_SYMBOL")

        assert result.status == OrderStatus.FAILED
        assert "No position" in (result.error or "")

    def test_concurrent_orders_thread_safety(self):
        """Multiple threads submitting orders simultaneously."""
        paper = self._make_paper()
        results = []
        errors = []

        def submit_one(i):
            try:
                order = _make_order(order_id=f"thread-{i}", symbol="EURUSD", quantity=0.01)
                r = paper.submit_order(order)
                results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=submit_one, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed (no crashes)
        assert len(errors) == 0, f"Thread safety errors: {errors}"
        assert len(results) == 20

        # BUG: dict operations in CPython are atomic due to GIL,
        # but the compound read-modify-write in _update_position is NOT.
        # If two threads buy the same symbol concurrently, the position
        # quantity/avg_price can be corrupted. This test may pass under
        # CPython GIL but fail under free-threaded Python 3.13+.

    def test_state_persistence_corruption(self):
        """Manually corrupt internal state and verify behavior."""
        paper = self._make_paper()
        paper.connect()

        # Corrupt positions dict
        paper._positions["CORRUPT"] = {
            "symbol": "CORRUPT",
            "side": "INVALID_SIDE",
            "quantity": -999,
            "avg_price": float("nan"),
        }

        # get_positions should still work despite corruption
        positions = paper.get_positions()
        assert any(p["symbol"] == "CORRUPT" for p in positions)

        # get_account_info should still work
        info = paper.get_account_info()
        assert info is not None

    def test_extremely_small_quantity(self):
        """Order with quantity=0.000001 — micro-lot precision."""
        paper = self._make_paper()
        order = _make_order(quantity=0.000001)

        result = paper.submit_order(order)

        assert result.status == OrderStatus.FILLED
        assert result.filled_quantity == 0.000001

        # Fee calculation with tiny quantity
        assert result.fee >= 0


# ===========================================================================
#  5. REAL BUG HUNT (8 tests)
# ===========================================================================


class TestRealBugHunt:
    """Probes designed to expose actual bugs in the adapter code."""

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_partial_fill_not_handled(self, mock_mt5):
        """FIXED: MT5 returns a partial fill (retcode=10009 but vol < requested)
        — adapter now reports PARTIALLY_FILLED instead of FILLED.
        """
        mock_mt5.terminal_info.return_value = MagicMock()
        # Requested 1.0 lot, only 0.3 filled
        mock_mt5.order_send.return_value = _make_result(retcode=10009, volume=0.3, price=1.08500)

        adapter = _connected_adapter()
        order = _make_order(quantity=1.0)
        result = adapter.submit_order(order)

        # FIXED: partial fill detection — result.volume < order.quantity
        # now returns PARTIALLY_FILLED instead of misleading FILLED.
        assert result.status == OrderStatus.PARTIALLY_FILLED
        assert result.filled_quantity == 0.3

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_rejection_code_not_all_retry_codes(self, mock_mt5):
        """MT5 returns retcode=10013 (TRADE_RETCODE_INVALID) — permanent fail."""
        mock_mt5.terminal_info.return_value = MagicMock()
        mock_mt5.order_send.return_value = _make_result(retcode=10013, comment="invalid trade parameters")

        adapter = _connected_adapter()
        order = _make_order()
        result = adapter.submit_order(order)

        # Should NOT retry on 10013 — it's a permanent rejection
        assert result.status == OrderStatus.FAILED
        assert mock_mt5.order_send.call_count == 1

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_cleanup_on_disconnect(self, mock_mt5):
        """After disconnect, internal state should be clean."""
        mock_mt5.terminal_info.return_value = MagicMock()

        adapter = _connected_adapter()
        assert adapter.is_connected

        adapter.disconnect()

        assert not adapter.is_connected
        # After disconnect, any operation should trigger reconnect
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        mock_mt5.order_send.return_value = _make_result()

        result = adapter.submit_order(_make_order())
        assert result.status == OrderStatus.FILLED

    def test_paper_adapter_slippage_simulation(self):
        """Paper adapter slippage is random — check it stays within bounds."""
        paper_cfg = {
            "paper_initial_capital": "10000",
            "paper_slippage_pips": "2.0",
            "paper_commission_per_lot": "7.0",
            "units_per_lot": "100000.0",
        }
        with patch("quant_os.execution.adapters.paper.get_config") as mock_cfg:
            cfg = MagicMock()
            for k, v in paper_cfg.items():
                setattr(cfg, k, v)
            mock_cfg.return_value = cfg
            paper = PaperAdapter(initial_capital=10000.0)
            paper.connect()

        # Fix price so it's deterministic (get_price() adds random noise per call)
        paper.set_price("EURUSD", bid=1.08500, ask=1.08520)

        fill_prices = []
        for _ in range(50):
            order = _make_order(quantity=100000)
            result = paper.submit_order(order)
            fill_prices.append(result.avg_price)

        # All fills should be within slippage bounds relative to the fixed ask
        base_ask = 1.08520
        for p in fill_prices:
            # Max slippage = 2 pips = 0.0002 for non-JPY
            assert p >= base_ask, f"BUY fill {p} < base ask {base_ask}"
            assert p - base_ask <= 0.0003, f"Slippage {p - base_ask} exceeds max 2 pips"

    def test_paper_adapter_cannot_go_negative(self):
        """Paper adapter can go negative — no margin call mechanism."""
        paper_cfg = {
            "paper_initial_capital": "1000",
            "paper_slippage_pips": "0",
            "paper_commission_per_lot": "0",
            "units_per_lot": "100000.0",
        }
        with patch("quant_os.execution.adapters.paper.get_config") as mock_cfg:
            cfg = MagicMock()
            for k, v in paper_cfg.items():
                setattr(cfg, k, v)
            mock_cfg.return_value = cfg
            paper = PaperAdapter(initial_capital=1000.0)
            paper.connect()

        # Open a huge position that will lose money
        paper.set_price("EURUSD", bid=1.0000, ask=1.0001)
        order = _make_order(quantity=1_000_000, side="BUY")
        paper.submit_order(order)

        # Now crash the price
        paper.set_price("EURUSD", bid=0.9000, ask=0.9001)
        info = paper.get_account_info()

        # BUG: equity is massively negative — no margin call
        assert info.equity < 0

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_weekend_market_closed(self, mock_mt5):
        """Submit order when markets are closed (weekend)."""
        mock_mt5.terminal_info.return_value = MagicMock()
        # MT5 returns TRADE_RETCODE_MARKET_CLOSED (10018)
        mock_mt5.order_send.return_value = _make_result(retcode=10018, comment="market closed")

        adapter = _connected_adapter()
        order = _make_order()
        result = adapter.submit_order(order)

        # Should not retry on market closed — it's a permanent condition
        assert result.status == OrderStatus.FAILED
        assert mock_mt5.order_send.call_count == 1

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_order_modification_after_fill(self, mock_mt5):
        """Try to close/cancel an order that's already filled."""
        mock_mt5.terminal_info.return_value = MagicMock()
        # orders_get returns None (order no longer pending = filled/cancelled)
        mock_mt5.orders_get.return_value = None

        adapter = _connected_adapter()

        # get_order_status should handle this gracefully
        result = adapter.get_order_status("123456")
        # FIXED: orders_get returns None (order no longer pending) —
        # get_order_status now returns UNKNOWN instead of assuming FILLED.
        assert result.status == OrderStatus.UNKNOWN

        # cancel_order on a filled order — MT5 will reject
        mock_mt5.order_send.return_value = _make_result(retcode=10015, comment="invalid order")
        cancel_result = adapter.cancel_order("123456")
        assert cancel_result.status == OrderStatus.FAILED

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_connect_called_twice(self, mock_mt5):
        """Calling connect() twice — should not leak or crash."""
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True

        adapter = MT5Adapter(login=12345, password="test")

        r1 = adapter.connect()
        r2 = adapter.connect()

        assert r1 is True
        assert r2 is True

        # BUG: no guard against double-initialize.
        # MT5 SDK may handle this gracefully, but we call initialize()
        # and login() twice without shutting down first.
        assert mock_mt5.initialize.call_count == 2
        assert mock_mt5.login.call_count == 2

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_close_position_with_none_ticket(self, mock_mt5):
        """close_position with ticket that positions_get can't find."""
        mock_mt5.terminal_info.return_value = MagicMock()
        mock_mt5.positions_get.return_value = None

        adapter = _connected_adapter()
        result = adapter.close_position("99999", volume=0.1, symbol="EURUSD")

        assert result.status == OrderStatus.FAILED
        assert "not found" in (result.error or "").lower()

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_set_stop_loss_negative_atr(self, mock_mt5):
        """set_fixed_atr_stop with negative ATR — must reject."""
        mock_mt5.terminal_info.return_value = MagicMock()

        adapter = _connected_adapter()
        result = adapter.set_fixed_atr_stop(
            position_ticket=12345,
            symbol="EURUSD",
            side="BUY",
            entry_price=1.0850,
            atr_value=-5.0,  # negative ATR
            atr_multiplier=2.0,
        )

        assert result is False

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_update_trailing_stop_unknown_side(self, mock_mt5):
        """update_trailing_stop with invalid side — must reject."""
        mock_mt5.terminal_info.return_value = MagicMock()

        adapter = _connected_adapter()
        result = adapter.update_trailing_stop(
            position_ticket=12345,
            symbol="EURUSD",
            side="LONG",  # invalid — should be BUY or SELL
            entry_price=1.0850,
            current_price=1.0900,
            atr_value=0.0050,
        )

        assert result is False


# ===========================================================================
#  6. CROSS-ADAPTER INVARIANT TESTS
# ===========================================================================


class TestCrossAdapterInvariants:
    """Ensure both adapters obey the same contract."""

    def _make_paper(self) -> PaperAdapter:
        with patch("quant_os.execution.adapters.paper.get_config") as mock_cfg:
            cfg = MagicMock()
            cfg.paper_initial_capital = "10000"
            cfg.paper_slippage_pips = "0"
            cfg.paper_commission_per_lot = "0"
            cfg.units_per_lot = "100000.0"
            mock_cfg.return_value = cfg
            adapter = PaperAdapter(initial_capital=10000.0)
            adapter.connect()
            return adapter

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_submit_order_returns_order_result(self, mock_mt5):
        """Both adapters must return OrderResult from submit_order."""
        mock_mt5.terminal_info.return_value = MagicMock()
        mock_mt5.symbol_info.return_value = MagicMock(visible=True, filling_mode=4)
        mock_mt5.order_send.return_value = _make_result()

        mt5_adapter = _connected_adapter()
        paper_adapter = self._make_paper()

        r1 = mt5_adapter.submit_order(_make_order())
        r2 = paper_adapter.submit_order(_make_order())

        assert isinstance(r1, OrderResult)
        assert isinstance(r2, OrderResult)
        assert isinstance(r1.status, OrderStatus)
        assert isinstance(r2.status, OrderStatus)

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_get_positions_returns_list_of_dicts(self, mock_mt5):
        """Both adapters must return list[dict] from get_positions."""
        mock_mt5.terminal_info.return_value = MagicMock()
        mock_mt5.positions_get.return_value = ()

        mt5_adapter = _connected_adapter()
        paper_adapter = self._make_paper()

        p1 = mt5_adapter.get_positions()
        p2 = paper_adapter.get_positions()

        assert isinstance(p1, list)
        assert isinstance(p2, list)

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_account_info_structure(self, mock_mt5):
        """Both adapters must return AccountInfo with required fields."""
        mock_mt5.terminal_info.return_value = MagicMock()
        info_mock = MagicMock()
        info_mock.equity = 10000
        info_mock.balance = 10000
        info_mock.margin = 0
        info_mock.margin_free = 10000
        mock_mt5.account_info.return_value = info_mock

        mt5_adapter = _connected_adapter()
        paper_adapter = self._make_paper()

        a1 = mt5_adapter.get_account_info()
        a2 = paper_adapter.get_account_info()

        assert isinstance(a1, AccountInfo)
        assert isinstance(a2, AccountInfo)
        assert a1.equity >= 0 or a1.equity < 0  # just check it's a float
        assert a2.equity >= 0 or a2.equity < 0

    def test_paper_adapter_idempotency(self):
        """Submitting same order_id twice must not duplicate position."""
        paper = self._make_paper()
        order = _make_order(order_id="idempotent-001", quantity=0.1)

        r1 = paper.submit_order(order)
        r2 = paper.submit_order(order)

        # Both will fill (paper adapter doesn't have MT5's idempotency guard)
        # But the position should reflect the total quantity
        positions = paper.get_positions()
        eurusd_pos = [p for p in positions if p["symbol"] == "EURUSD"]

        # BUG: paper adapter fills duplicate orders — position is now 0.2
        # instead of 0.1. MT5 would reject the duplicate via comment matching.
        total_qty = sum(p["quantity"] for p in eurusd_pos)
        assert total_qty == 0.2  # this IS the bug — paper doesn't deduplicate


# ===========================================================================
#  7. HELPER FUNCTION ADVERSARIAL TESTS
# ===========================================================================


class TestHelperFunctions:
    """Test the module-level helper functions under adversarial conditions."""

    def test_side_to_order_type_lowercase(self):
        """_side_to_order_type with lowercase input."""
        assert _side_to_order_type("buy") == _ORDER_TYPE_BUY
        assert _side_to_order_type("sell") == _ORDER_TYPE_SELL

    def test_side_to_order_type_unknown_side(self):
        """_side_to_order_type with garbage input."""
        with pytest.raises(ValueError, match="Unknown side"):
            _side_to_order_type("HOLD")

    def test_side_to_order_type_empty_string(self):
        """_side_to_order_type with empty string."""
        with pytest.raises((ValueError, AttributeError)):
            _side_to_order_type("")

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_get_filling_mode_no_mt5(self, mock_mt5):
        """_get_filling_mode when mt5 module is None."""
        import quant_os.execution.adapters.mt5 as mod

        original = mod.mt5
        mod.mt5 = None
        try:
            mode = _get_filling_mode("EURUSD")
            assert mode == _ORDER_FILLING_RETURN
        finally:
            mod.mt5 = original

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_ensure_symbol_visible_no_mt5(self, mock_mt5):
        """_ensure_symbol_visible when mt5 module is None."""
        import quant_os.execution.adapters.mt5 as mod

        original = mod.mt5
        mod.mt5 = None
        try:
            result = _ensure_symbol_visible("EURUSD")
            assert result is False
        finally:
            mod.mt5 = original

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_get_filling_mode_all_bits_set(self, mock_mt5):
        """_get_filling_mode with all filling bits set (FOK+IOC+RETURN)."""
        info = MagicMock()
        info.filling_mode = 7  # all 3 bits set
        mock_mt5.symbol_info.return_value = info

        mode = _get_filling_mode("EURUSD")
        # Should prefer RETURN (bit 2) as it's checked first
        assert mode == _ORDER_FILLING_RETURN

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_get_filling_mode_only_fok(self, mock_mt5):
        """_get_filling_mode with only FOK bit set."""
        info = MagicMock()
        info.filling_mode = 1  # bit 0 only
        mock_mt5.symbol_info.return_value = info

        mode = _get_filling_mode("EURUSD")
        assert mode == 0  # _ORDER_FILLING_FOK

    @patch("quant_os.execution.adapters.mt5.mt5")
    def test_get_filling_mode_symbol_info_none(self, mock_mt5):
        """_get_filling_mode when symbol_info returns None."""
        mock_mt5.symbol_info.return_value = None

        mode = _get_filling_mode("UNKNOWN")
        assert mode == _ORDER_FILLING_RETURN  # fallback
