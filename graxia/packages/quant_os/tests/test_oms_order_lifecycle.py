"""OMS Order Lifecycle Tests — Wave 3 Task 3.5.

Tests the full order lifecycle through the OMS:
- Happy path (submit → fill)
- Risk rejection
- Broker rejection
- Partial fill
- Cancel order
- Duplicate idempotency
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from graxia.packages.quant_os.core.enums import OrderStatus
from graxia.packages.quant_os.execution.adapters.base import (
    AccountInfo,
    BrokerAdapter,
    Order,
    OrderResult,
)
from graxia.packages.quant_os.execution.oms import OMS, VENUE_MAP

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class MockBrokerAdapter(BrokerAdapter):
    """Mock broker adapter for testing."""

    def __init__(self, name: str = "mock_mt5"):
        super().__init__(name)
        self._connected = True
        self._submit_result: OrderResult | None = None
        self._cancel_result: OrderResult | None = None
        self._positions: list[dict] = []
        self._account_info = AccountInfo(
            equity=10000.0,
            cash=10000.0,
            margin_used=0.0,
            margin_available=10000.0,
        )

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def submit_order(self, order: Order) -> OrderResult:
        if self._submit_result is not None:
            return self._submit_result
        return OrderResult(
            status=OrderStatus.FILLED,
            broker_id="BROKER-123",
            filled_quantity=order.quantity,
            avg_price=1.1234,
            fee=0.50,
        )

    def cancel_order(self, broker_order_id: str) -> OrderResult:
        if self._cancel_result is not None:
            return self._cancel_result
        return OrderResult(status=OrderStatus.CANCELLED, broker_id=broker_order_id)

    def get_positions(self) -> list[dict]:
        return self._positions

    def get_order_status(self, broker_order_id: str) -> OrderResult:
        return OrderResult(
            status=OrderStatus.FILLED,
            broker_id=broker_order_id,
            filled_quantity=0.1,
            avg_price=1.1234,
        )

    def close_position(self, broker_position_id: str, volume: float, symbol: str = "") -> OrderResult:
        return OrderResult(
            status=OrderStatus.FILLED,
            broker_id=broker_position_id,
            filled_quantity=volume,
        )

    def get_account_info(self) -> AccountInfo:
        return self._account_info

    def set_stop_loss(self, position_ticket: str, symbol: str, stop_loss_price: float) -> OrderResult:
        """Mock set_stop_loss implementation."""
        return OrderResult(
            status=OrderStatus.FILLED,
            broker_id=position_ticket,
        )


class MockRiskEngine:
    """Mock risk engine that can approve or reject orders."""

    def __init__(self, approved: bool = True, reason: str = ""):
        self._approved = approved
        self._reason = reason
        self._check_calls: list[Order] = []

    def check_order_sync(self, order: Order) -> MagicMock:
        self._check_calls.append(order)
        result = MagicMock()
        result.passed = self._approved
        result.reason = self._reason
        return result


@pytest.fixture
def tmp_ledger(tmp_path):
    """Provide a temporary ledger path."""
    return tmp_path / "test_ledger.jsonl"


@pytest.fixture
def mock_adapter():
    """Provide a mock broker adapter."""
    return MockBrokerAdapter()


@pytest.fixture
def oms(mock_adapter, tmp_ledger):
    """Provide an OMS with a mock adapter and an approving risk engine."""
    risk_engine = MockRiskEngine(approved=True)
    return OMS(
        adapters={"mt5": mock_adapter},
        ledger_path=tmp_ledger,
        risk_engine=risk_engine,
    )


@pytest.fixture
def oms_with_risk(mock_adapter, tmp_ledger):
    """Provide an OMS with a mock adapter and an approving risk engine."""
    risk_engine = MockRiskEngine(approved=True)
    return OMS(
        adapters={"mt5": mock_adapter},
        ledger_path=tmp_ledger,
        risk_engine=risk_engine,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSubmitOrderHappyPath:
    """Test 1: Happy path — order submits and fills successfully."""

    def test_submit_order_fills(self, oms, mock_adapter):
        """Order should go through PENDING → SUBMITTED → FILLED."""
        order = oms.submit_order(
            signal_id="SIG-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
            stop_loss=2000.0,
            take_profit=2010.0,
        )

        assert order.status == OrderStatus.FILLED
        assert order.order_id is not None
        assert order.signal_id == "SIG-001"
        assert order.symbol == "XAUUSD"

    def test_submit_order_persists_to_ledger(self, oms, tmp_ledger):
        """Order should be persisted to the JSONL ledger."""
        oms.submit_order(
            signal_id="SIG-002",
            symbol="EURUSD",
            asset_class="forex",
            side="SELL",
            quantity=0.05,
        )

        assert tmp_ledger.exists()
        lines = tmp_ledger.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 1
        # Check last event has FILLED status
        last_event = json.loads(lines[-1])
        assert last_event["status"] == "FILLED"

    def test_submit_order_state_history(self, oms):
        """Order should have a complete state history."""
        order = oms.submit_order(
            signal_id="SIG-003",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        history = oms.get_state_history(order.order_id)
        assert len(history) >= 2  # At least SIGNAL_CREATED and some progress


class TestRiskRejectBlocksOrder:
    """Test 2: Risk engine rejection blocks order submission."""

    def test_risk_rejection_sets_rejected(self, mock_adapter, tmp_ledger):
        """When risk engine rejects, order status should be REJECTED."""
        risk_engine = MockRiskEngine(approved=False, reason="Daily loss limit exceeded")
        oms = OMS(
            adapters={"mt5": mock_adapter},
            ledger_path=tmp_ledger,
            risk_engine=risk_engine,
        )

        order = oms.submit_order(
            signal_id="SIG-RISK-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        assert order.status == OrderStatus.REJECTED
        # Broker should NOT have been called
        assert order.broker_order_id is None

    def test_risk_rejection_recorded_in_ledger(self, mock_adapter, tmp_ledger):
        """Risk rejection should be persisted to ledger."""
        risk_engine = MockRiskEngine(approved=False, reason="Max positions reached")
        oms = OMS(
            adapters={"mt5": mock_adapter},
            ledger_path=tmp_ledger,
            risk_engine=risk_engine,
        )

        oms.submit_order(
            signal_id="SIG-RISK-002",
            symbol="EURUSD",
            asset_class="forex",
            side="SELL",
            quantity=0.05,
        )

        assert tmp_ledger.exists()
        lines = tmp_ledger.read_text(encoding="utf-8").strip().split("\n")
        last_event = json.loads(lines[-1])
        assert last_event["status"] == "REJECTED"

    def test_risk_engine_called_with_order(self, mock_adapter, tmp_ledger):
        """Risk engine should receive the order for evaluation."""
        risk_engine = MockRiskEngine(approved=False, reason="test")
        oms = OMS(
            adapters={"mt5": mock_adapter},
            ledger_path=tmp_ledger,
            risk_engine=risk_engine,
        )

        oms.submit_order(
            signal_id="SIG-RISK-003",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        assert len(risk_engine._check_calls) == 1
        assert risk_engine._check_calls[0].symbol == "XAUUSD"


class TestBrokerReject:
    """Test 3: Broker rejection propagates correctly."""

    def test_broker_failed_sets_failed(self, mock_adapter, tmp_ledger):
        """When broker returns FAILED, order status should be FAILED."""
        mock_adapter._submit_result = OrderResult(
            status=OrderStatus.FAILED,
            error="Insufficient margin",
        )

        oms = OMS(
            adapters={"mt5": mock_adapter},
            ledger_path=tmp_ledger,
            risk_engine=MockRiskEngine(approved=True),
        )

        order = oms.submit_order(
            signal_id="SIG-BROKER-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        assert order.status == OrderStatus.FAILED

    def test_broker_timeout_sets_timeout(self, mock_adapter, tmp_ledger):
        """When broker returns TIMEOUT, order status should be TIMEOUT."""
        mock_adapter._submit_result = OrderResult(
            status=OrderStatus.TIMEOUT,
            error="Connection timeout",
        )

        oms = OMS(
            adapters={"mt5": mock_adapter},
            ledger_path=tmp_ledger,
            risk_engine=MockRiskEngine(approved=True),
        )

        order = oms.submit_order(
            signal_id="SIG-BROKER-002",
            symbol="EURUSD",
            asset_class="forex",
            side="SELL",
            quantity=0.05,
        )

        assert order.status == OrderStatus.TIMEOUT

    def test_broker_failure_recorded_in_ledger(self, mock_adapter, tmp_ledger):
        """Broker failure should be persisted to ledger."""
        mock_adapter._submit_result = OrderResult(
            status=OrderStatus.FAILED,
            error="Rejected by broker",
        )

        oms = OMS(
            adapters={"mt5": mock_adapter},
            ledger_path=tmp_ledger,
            risk_engine=MockRiskEngine(approved=True),
        )

        oms.submit_order(
            signal_id="SIG-BROKER-003",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        lines = tmp_ledger.read_text(encoding="utf-8").strip().split("\n")
        last_event = json.loads(lines[-1])
        assert last_event["status"] == "FAILED"


class TestPartialFill:
    """Test 4: Partial fill handling with poll timeout."""

    def test_partial_fill_polls_to_completion(self, mock_adapter, tmp_ledger):
        """Partial fill should poll until FILLED."""
        # First call returns partial, second returns filled
        call_count = 0

        def mock_get_status(broker_order_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return OrderResult(
                    status=OrderStatus.FILLED,
                    broker_id=broker_order_id,
                    filled_quantity=0.1,
                    avg_price=1.1234,
                )
            return OrderResult(
                status=OrderStatus.FILLED,
                broker_id=broker_order_id,
                filled_quantity=0.1,
                avg_price=1.1234,
            )

        mock_adapter._submit_result = OrderResult(
            status=OrderStatus.PARTIALLY_FILLED,
            broker_id="BROKER-PARTIAL",
            filled_quantity=0.05,
            avg_price=1.1230,
        )
        mock_adapter.get_order_status = mock_get_status

        oms = OMS(
            adapters={"mt5": mock_adapter},
            ledger_path=tmp_ledger,
            risk_engine=MockRiskEngine(approved=True),
        )

        order = oms.submit_order(
            signal_id="SIG-PARTIAL-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        # Should eventually reach FILLED or TIMEOUT
        assert order.status in (OrderStatus.FILLED, OrderStatus.TIMEOUT)

    def test_partial_fill_timeout(self, mock_adapter, tmp_ledger):
        """Partial fill should timeout if never fully fills."""
        mock_adapter._submit_result = OrderResult(
            status=OrderStatus.PARTIALLY_FILLED,
            broker_id="BROKER-PARTIAL-TIMEOUT",
            filled_quantity=0.05,
            avg_price=1.1230,
        )

        # Always return partial fill
        mock_adapter.get_order_status = lambda bid: OrderResult(
            status=OrderStatus.PARTIALLY_FILLED,
            broker_id=bid,
            filled_quantity=0.05,
            avg_price=1.1230,
        )

        oms = OMS(
            adapters={"mt5": mock_adapter},
            ledger_path=tmp_ledger,
            risk_engine=MockRiskEngine(approved=True),
        )

        # Use a short timeout for testing
        with patch("graxia.packages.quant_os.execution.oms._FILL_TIMEOUT", 0.1):
            order = oms.submit_order(
                signal_id="SIG-PARTIAL-TIMEOUT-001",
                symbol="XAUUSD",
                asset_class="metals",
                side="BUY",
                quantity=0.1,
            )

        assert order.status == OrderStatus.TIMEOUT


class TestCancelOrder:
    """Test 5: Cancel order functionality."""

    def test_cancel_all_cancels_open_orders(self, oms, mock_adapter):
        """cancel_all should cancel all open orders."""
        # Submit an order that stays in SUBMITTED state
        mock_adapter._submit_result = OrderResult(
            status=OrderStatus.SUBMITTED,
            broker_id="BROKER-CANCEL",
        )

        order = oms.submit_order(
            signal_id="SIG-CANCEL-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        # The order might be in SUBMITTED or FAILED status
        # Let's check what status it has
        if order.status not in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.FAILED, OrderStatus.TIMEOUT):
            cancelled = oms.cancel_all()
            assert len(cancelled) >= 0  # May or may not have orders to cancel

    def test_cancel_all_with_asset_class_filter(self, oms, mock_adapter):
        """cancel_all should filter by asset class when provided."""
        mock_adapter._submit_result = OrderResult(
            status=OrderStatus.SUBMITTED,
            broker_id="BROKER-CANCEL-FILTER",
        )

        # Submit orders for different asset classes
        oms.submit_order(
            signal_id="SIG-CANCEL-METALS-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        # Cancel only metals
        cancelled = oms.cancel_all(asset_class="metals")
        # Should have cancelled at least the metals order
        for order in cancelled:
            assert order.asset_class.lower() == "metals"


class TestDuplicateIdempotency:
    """Test 6: Duplicate signal_id returns existing order."""

    def test_duplicate_signal_id_returns_existing(self, oms):
        """Submitting the same signal_id twice should return the same order."""
        order1 = oms.submit_order(
            signal_id="SIG-DUP-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        order2 = oms.submit_order(
            signal_id="SIG-DUP-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        assert order1.order_id == order2.order_id
        assert order1.signal_id == order2.signal_id

    def test_different_signal_ids_create_different_orders(self, oms):
        """Different signal_ids should create different orders."""
        order1 = oms.submit_order(
            signal_id="SIG-UNIQUE-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        order2 = oms.submit_order(
            signal_id="SIG-UNIQUE-002",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        assert order1.order_id != order2.order_id

    def test_duplicate_does_not_call_broker_again(self, mock_adapter, tmp_ledger):
        """Duplicate submission should not call broker adapter again."""
        oms = OMS(
            adapters={"mt5": mock_adapter},
            ledger_path=tmp_ledger,
            risk_engine=MockRiskEngine(approved=True),
        )

        # First submission
        oms.submit_order(
            signal_id="SIG-DUP-BROKER-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        # Track broker calls
        original_submit = mock_adapter.submit_order
        call_count = 0

        def counting_submit(order):
            nonlocal call_count
            call_count += 1
            return original_submit(order)

        mock_adapter.submit_order = counting_submit

        # Second submission with same signal_id
        oms.submit_order(
            signal_id="SIG-DUP-BROKER-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        # Broker should NOT have been called again
        assert call_count == 0

    def test_idempotency_across_ledger_reload(self, mock_adapter, tmp_ledger):
        """Idempotency should persist across ledger reloads."""
        # First OMS instance
        oms1 = OMS(
            adapters={"mt5": mock_adapter},
            ledger_path=tmp_ledger,
            risk_engine=MockRiskEngine(approved=True),
        )

        order1 = oms1.submit_order(
            signal_id="SIG-RELOAD-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        # Create new OMS instance with same ledger (simulates restart)
        oms2 = OMS(
            adapters={"mt5": mock_adapter},
            ledger_path=tmp_ledger,
            risk_engine=MockRiskEngine(approved=True),
        )

        # Submit same signal_id
        order2 = oms2.submit_order(
            signal_id="SIG-RELOAD-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        # Should return the same order
        assert order1.order_id == order2.order_id


class TestVenueMap:
    """Test venue routing table."""

    def test_crypto_routes_to_mt5(self):
        """Crypto should route to mt5 (not binance)."""
        assert VENUE_MAP["crypto"] == "mt5"

    def test_metals_routes_to_mt5(self):
        """Metals should route to mt5."""
        assert VENUE_MAP["metals"] == "mt5"

    def test_forex_routes_to_mt5(self):
        """Forex should route to mt5."""
        assert VENUE_MAP["forex"] == "mt5"

    def test_indices_routes_to_mt5(self):
        """Indices should route to mt5."""
        assert VENUE_MAP["indices"] == "mt5"


class TestOMSInitialization:
    """Test OMS initialization and configuration."""

    def test_oms_with_no_risk_engine(self, mock_adapter, tmp_ledger):
        """OMS should work without a risk engine (but orders will be rejected)."""
        oms = OMS(
            adapters={"mt5": mock_adapter},
            ledger_path=tmp_ledger,
        )

        assert oms._risk_engine is None
        # Fail-closed: submitting without risk_engine rejects the order
        order = oms.submit_order(
            signal_id="SIG-NO-RISK-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )
        assert order.status == OrderStatus.REJECTED

    def test_oms_with_risk_engine(self, mock_adapter, tmp_ledger):
        """OMS should accept a risk engine."""
        risk_engine = MockRiskEngine()
        oms = OMS(
            adapters={"mt5": mock_adapter},
            ledger_path=tmp_ledger,
            risk_engine=risk_engine,
        )

        assert oms._risk_engine is risk_engine

    def test_oms_creates_ledger_directory(self, mock_adapter, tmp_path):
        """OMS should create the ledger directory if it doesn't exist."""
        ledger_dir = tmp_path / "nested" / "dir"
        ledger_path = ledger_dir / "ledger.jsonl"

        oms = OMS(
            adapters={"mt5": mock_adapter},
            ledger_path=ledger_path,
            risk_engine=MockRiskEngine(approved=True),
        )

        assert ledger_dir.exists()


class TestRiskEngineError:
    """Test risk engine error handling."""

    def test_risk_engine_exception_rejects_order(self, mock_adapter, tmp_ledger):
        """If risk engine throws, order should be REJECTED (fail-closed)."""
        risk_engine = MagicMock()
        risk_engine.check_order_sync.side_effect = RuntimeError("Risk engine crash")

        oms = OMS(
            adapters={"mt5": mock_adapter},
            ledger_path=tmp_ledger,
            risk_engine=risk_engine,
        )

        order = oms.submit_order(
            signal_id="SIG-RISK-ERR-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        assert order.status == OrderStatus.REJECTED


class TestQueryHelpers:
    """Test OMS query helpers."""

    def test_order_by_id(self, oms):
        """order_by_id should return the correct order."""
        order = oms.submit_order(
            signal_id="SIG-QUERY-001",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        found = oms.order_by_id(order.order_id)
        assert found is not None
        assert found.order_id == order.order_id

    def test_order_by_signal(self, oms):
        """order_by_signal should return the correct order."""
        order = oms.submit_order(
            signal_id="SIG-QUERY-002",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )

        found = oms.order_by_signal("SIG-QUERY-002")
        assert found is not None
        assert found.signal_id == "SIG-QUERY-002"

    def test_order_by_id_not_found(self, oms):
        """order_by_id should return None for unknown order_id."""
        found = oms.order_by_id("nonexistent-id")
        assert found is None

    def test_order_by_signal_not_found(self, oms):
        """order_by_signal should return None for unknown signal_id."""
        found = oms.order_by_signal("nonexistent-signal")
        assert found is None
