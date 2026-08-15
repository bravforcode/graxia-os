"""End-to-end live order test — OMS → MT5Adapter → mock MT5 module.

Proves the full flow works:
  Signal → OMS.submit_order → MT5Adapter.submit_order → mt5.order_send

Uses a fully mocked MT5 module (no real terminal needed).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Ensure quant_os is importable
# ---------------------------------------------------------------------------
_QOS = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
if _QOS not in sys.path:
    sys.path.insert(0, _QOS)

from graxia.packages.quant_os.core.enums import OrderStatus  # noqa: E402
from graxia.packages.quant_os.execution.adapters.mt5 import MT5Adapter  # noqa: E402
from graxia.packages.quant_os.execution.broker_reconnector import BrokerConfig, BrokerReconnector  # noqa: E402
from graxia.packages.quant_os.execution.oms import OMS  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_mt5() -> MagicMock:
    """Create a fully functional mock of the MetaTrader5 module."""
    mt5 = MagicMock()
    mt5.initialize.return_value = True
    mt5.login.return_value = True
    mt5.last_error.return_value = ""

    # Terminal info (connected)
    terminal = MagicMock()
    terminal.connected = True
    mt5.terminal_info.return_value = terminal

    # Account info
    acct = MagicMock()
    acct.login = 12345
    acct.server = "Pepperstone-Live"
    acct.currency = "USD"
    acct.leverage = 500
    acct.balance = 50000.0
    acct.equity = 50123.45
    acct.margin = 0.0
    acct.margin_free = 50000.0
    acct.margin_level = 0.0
    acct.profit = 123.45
    mt5.account_info.return_value = acct

    # Symbol info
    sym_info = MagicMock()
    sym_info.digits = 2
    sym_info.point = 0.01
    sym_info.trade_contract_size = 100
    sym_info.trade_tick_size = 0.01
    sym_info.trade_tick_value = 1.0
    sym_info.volume_min = 0.01
    sym_info.volume_max = 100.0
    sym_info.volume_step = 0.01
    sym_info.stops_level = 10
    sym_info.freeze_level = 5
    sym_info.visible = True
    sym_info.filling_mode = 4  # RETURN supported
    sym_info.trade_mode = 0
    sym_info.currency_base = "USD"
    sym_info.currency_profit = "USD"
    sym_info.currency_margin = "USD"
    mt5.symbol_info.return_value = sym_info

    # Tick
    tick = MagicMock()
    tick.bid = 2000.0
    tick.ask = 2000.5
    tick.last = 2000.25
    tick.volume = 1.0
    tick.time = int(datetime.now(UTC).timestamp())
    mt5.symbol_info_tick.return_value = tick

    return mt5


def _mock_fill_result(retcode=10009, order=99999, volume=0.1, price=2000.0, comment=""):
    """Create a mock MT5 order_send result for a successful fill."""
    r = MagicMock()
    r.retcode = retcode
    r.order = order
    r.volume = volume
    r.price = price
    r.comment = comment
    return r


def _mock_risk_engine(approved=True, reason=""):
    """Create a mock risk engine."""
    engine = MagicMock()
    result = MagicMock()
    result.passed = approved
    result.reason = reason
    engine.check_order_sync.return_value = result
    return engine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_mt5():
    """Provide a mock MT5 module and patch it into the adapter."""
    m = _make_mock_mt5()
    import graxia.packages.quant_os.execution.adapters.mt5 as mt5_mod

    original = mt5_mod.mt5
    mt5_mod.mt5 = m
    try:
        yield m
    finally:
        mt5_mod.mt5 = original


@pytest.fixture
def mt5_adapter(mock_mt5):
    """Provide an MT5Adapter with mocked MT5."""
    # Fast reconnector so reconnect-exhaustion tests (TIMEOUT path) run in
    # milliseconds instead of the production 5s x2^n backoff (~135s).
    fast_reconnector = BrokerReconnector(
        BrokerConfig(max_reconnect_attempts=2, reconnect_delay_sec=0.01, reconnect_backoff_mult=1.0)
    )
    adapter = MT5Adapter(login=12345, password="test", server="Pepperstone-Live", reconnector=fast_reconnector)
    adapter._connected = True  # skip connect for most tests
    return adapter


@pytest.fixture
def oms_with_mt5(mt5_adapter, tmp_path):
    """Provide an OMS wired to the real MT5Adapter (mocked MT5)."""
    risk = _mock_risk_engine(approved=True)
    return OMS(
        adapters={"mt5": mt5_adapter},
        ledger_path=tmp_path / "e2e_ledger.jsonl",
        risk_engine=risk,
    )


# ---------------------------------------------------------------------------
# Tests — Full Flow
# ---------------------------------------------------------------------------


class TestMT5E2EFill:
    """End-to-end: signal → OMS → MT5Adapter → mt5.order_send → fill."""

    def test_buy_order_fills(self, oms_with_mt5, mock_mt5):
        """BUY XAUUSD order fills successfully through full stack.

        quantity=10.0 is raw troy oz (the domain order.quantity/TrackedOrder
        use everywhere else) -- XAUUSD contract_size=100, so the adapter must
        send 10.0/100=0.1 lots to MT5, not 10.0 lots (2026-07-28/29
        units-vs-lots fix; see reports/live_sizing_units_lots_gap_20260728.md).
        """
        mock_mt5.order_send.return_value = _mock_fill_result(retcode=10009, order=11111, volume=0.1, price=2000.25)

        order = oms_with_mt5.submit_order(
            signal_id="E2E-BUY-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=10.0,
            stop_loss=1990.0,
            take_profit=2010.0,
        )

        assert order.status == OrderStatus.FILLED
        assert order.broker_order_id == "11111"
        assert order.symbol == "XAUUSD"
        assert order.side == "BUY"

        # Verify mt5.order_send was called with correct request — volume must
        # be in LOTS (0.1), not raw units (10.0). This is the exact bug: 100x
        # oversized order if this assertion were req["volume"] == 10.0.
        call_args = mock_mt5.order_send.call_args
        req = call_args[0][0]
        assert req["symbol"] == "XAUUSD"
        assert req["type"] == 0  # ORDER_TYPE_BUY
        assert req["volume"] == pytest.approx(0.1)
        assert req["sl"] == 1990.0
        assert req["tp"] == 2010.0

    def test_sell_order_fills(self, oms_with_mt5, mock_mt5):
        """SELL EURUSD order fills successfully through full stack.

        quantity=5000 is raw EUR units; EURUSD contract_size=100,000 (1 FX
        lot), so the adapter must send 5000/100000=0.05 lots to MT5.
        """
        # Setup symbol info for forex
        sym_info = mock_mt5.symbol_info.return_value
        sym_info.filling_mode = 4

        mock_mt5.order_send.return_value = _mock_fill_result(retcode=10009, order=22222, volume=0.05, price=1.0850)

        order = oms_with_mt5.submit_order(
            signal_id="E2E-SELL-001",
            symbol="EURUSD",
            asset_class="forex",
            side="SELL",
            quantity=5000.0,
        )

        assert order.status == OrderStatus.FILLED
        assert order.broker_order_id == "22222"

        req = mock_mt5.order_send.call_args[0][0]
        assert req["type"] == 1  # ORDER_TYPE_SELL
        assert req["volume"] == pytest.approx(0.05)

    def test_order_persisted_to_ledger(self, oms_with_mt5, mock_mt5, tmp_path):
        """Order events are persisted to the JSONL ledger."""
        mock_mt5.order_send.return_value = _mock_fill_result(order=33333)

        oms_with_mt5.submit_order(
            signal_id="E2E-LEDGER-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        ledger = tmp_path / "e2e_ledger.jsonl"
        assert ledger.exists()
        lines = [ln.strip() for ln in ledger.read_text().strip().split("\n") if ln.strip()]
        assert len(lines) >= 1

        # Last event should be FILLED
        last = json.loads(lines[-1])
        assert last["status"] == "FILLED"
        assert last["symbol"] == "XAUUSD"
        assert last["broker_order_id"] == "33333"


class TestMT5E2ERejection:
    """End-to-end: broker rejection flows through OMS correctly."""

    def test_broker_rejection(self, oms_with_mt5, mock_mt5):
        """MT5 rejects order → OMS marks as FAILED."""
        mock_mt5.order_send.return_value = _mock_fill_result(retcode=10013, comment="invalid volume")

        order = oms_with_mt5.submit_order(
            signal_id="E2E-REJECT-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        assert order.status == OrderStatus.FAILED

    def test_risk_rejection_blocks_broker(self, mt5_adapter, mock_mt5, tmp_path):
        """Risk engine rejects → broker never called."""
        risk = _mock_risk_engine(approved=False, reason="Max drawdown exceeded")
        oms = OMS(
            adapters={"mt5": mt5_adapter},
            ledger_path=tmp_path / "risk_reject.jsonl",
            risk_engine=risk,
        )

        order = oms.submit_order(
            signal_id="E2E-RISK-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        assert order.status == OrderStatus.REJECTED
        mock_mt5.order_send.assert_not_called()


class TestMT5E2EIdempotency:
    """End-to-end: duplicate signal_id is rejected (no double submit)."""

    def test_duplicate_signal_returns_existing(self, oms_with_mt5, mock_mt5):
        """Second submission with same signal_id returns first order."""
        mock_mt5.order_send.return_value = _mock_fill_result(order=44444)

        order1 = oms_with_mt5.submit_order(
            signal_id="E2E-IDEMP-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        order2 = oms_with_mt5.submit_order(
            signal_id="E2E-IDEMP-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        assert order1.order_id == order2.order_id
        # Only one order_send call
        assert mock_mt5.order_send.call_count == 1


class TestMT5E2EPartialFill:
    """End-to-end: partial fill triggers poll → eventual fill."""

    def test_partial_fill_then_fill(self, oms_with_mt5, mock_mt5):
        """Partial fill → poll → fill."""
        partial_result = _mock_fill_result(retcode=10009, order=55555, volume=0.05, price=2000.0)
        fill_result = _mock_fill_result(retcode=10009, order=55555, volume=0.1, price=2000.25)

        mock_mt5.order_send.return_value = partial_result

        # Mock get_order_status to return FILLED on poll
        fill_status = MagicMock()
        fill_status.retcode = 10009
        fill_status.order = 55555
        fill_status.volume = 0.1
        fill_status.price = 2000.25

        # orders_get returns None (not in open orders), history_deals_get returns fill
        mock_mt5.orders_get.return_value = None
        fill_deal = MagicMock()
        fill_deal.entry = 0  # ENTRY_IN
        fill_deal.volume = 0.1
        fill_deal.price = 2000.25
        mock_mt5.history_deals_get.return_value = [fill_deal]

        order = oms_with_mt5.submit_order(
            signal_id="E2E-PARTIAL-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        # Should eventually fill (partial → poll → fill)
        assert order.status in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED)


class TestMT5E2ECancel:
    """End-to-end: cancel order through OMS → MT5Adapter."""

    def test_cancel_all_with_open_orders(self, mt5_adapter, mock_mt5, tmp_path):
        """cancel_all cancels non-terminal orders via MT5Adapter."""
        risk = _mock_risk_engine(approved=True)
        oms = OMS(
            adapters={"mt5": mt5_adapter},
            ledger_path=tmp_path / "cancel_test.jsonl",
            risk_engine=risk,
        )

        # Directly inject a non-terminal order into OMS (bypass submit to avoid poll timeout)
        from graxia.packages.quant_os.execution.adapters.base import Order

        order = Order(
            order_id="cancel-test-001",
            signal_id="sig-cancel-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
            status=OrderStatus.SUBMITTED,
            broker_order_id="88888",
        )
        oms._orders[order.order_id] = order
        oms._orders_by_signal_id[order.signal_id] = order

        # Mock cancel
        mock_mt5.order_send.return_value = _mock_fill_result(retcode=10009)

        cancelled = oms.cancel_all(asset_class="metals")
        assert len(cancelled) == 1
        assert cancelled[0].order_id == "cancel-test-001"


class TestMT5E2EErrorRecovery:
    """End-to-end: MT5 connection errors are handled gracefully."""

    def test_mt5_returns_none_retries(self, oms_with_mt5, mock_mt5):
        """order_send returns None → reconnect → retry → timeout."""
        # Ensure initial connection check passes (terminal_info truthy)
        terminal = MagicMock()
        terminal.connected = True
        mock_mt5.terminal_info.return_value = terminal

        # order_send returns None (connection lost during trade)
        mock_mt5.order_send.return_value = None
        mock_mt5.last_error.return_value = "connection lost"

        # Reconnect will fail: initialize returns False
        mock_mt5.initialize.return_value = False

        order = oms_with_mt5.submit_order(
            signal_id="E2E-ERR-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        # Should result in TIMEOUT (reconnect failed inside retry loop)
        assert order.status in (OrderStatus.TIMEOUT, OrderStatus.FAILED)

    def test_entry_reconnect_exhausted_returns_timeout(self, oms_with_mt5, mock_mt5, mt5_adapter):
        """Connection already down at method entry, reconnect exhausts → TIMEOUT, not raise."""
        mt5_adapter._connected = False
        mock_mt5.terminal_info.return_value = None
        mock_mt5.initialize.return_value = False

        order = oms_with_mt5.submit_order(
            signal_id="E2E-ENTRY-ERR-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        assert order.status in (OrderStatus.TIMEOUT, OrderStatus.FAILED)

    def test_invalid_price_retries(self, oms_with_mt5, mock_mt5):
        """Invalid price (10014) triggers retry then success."""
        mock_mt5.order_send.side_effect = [
            _mock_fill_result(retcode=10014),  # first attempt: invalid price
            _mock_fill_result(retcode=10009, order=77777),  # retry: success
        ]

        order = oms_with_mt5.submit_order(
            signal_id="E2E-RETRY-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        assert order.status == OrderStatus.FILLED
        assert order.broker_order_id == "77777"
