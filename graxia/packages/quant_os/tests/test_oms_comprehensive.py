"""Comprehensive OMS & order lifecycle tests — 30+ tests.

Covers:
1. Order creation and submission (idempotency, crash recovery, risk gate)
2. Order state machine (full happy path, rejection, timeout, partial fill)
3. Close position (success, failure, idempotency)
4. Ledger persistence (write on submit/fill/close, crash recovery)
5. Risk integration (block, allow, circuit breaker, kill switch)
6. Error handling (timeout, broker rejection, network error, invalid symbol)
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
from graxia.packages.quant_os.execution.oms import OMS

# ---------------------------------------------------------------------------
# Mock broker adapter
# ---------------------------------------------------------------------------


class MockBrokerAdapter(BrokerAdapter):
    """Configurable mock broker for unit tests."""

    def __init__(self, name: str = "mock_mt5"):
        super().__init__(name)
        self._connected = True
        self._submit_result: OrderResult | None = None
        self._cancel_result: OrderResult | None = None
        self._close_result: OrderResult | None = None
        self._positions: list[dict] = []
        self._account_info = AccountInfo(
            equity=10000.0,
            cash=10000.0,
            margin_used=0.0,
            margin_available=10000.0,
        )
        self._submit_calls: list[Order] = []
        self._close_calls: list[tuple] = []
        self._cancel_calls: list[str] = []

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def submit_order(self, order: Order) -> OrderResult:
        self._submit_calls.append(order)
        if self._submit_result is not None:
            return self._submit_result
        return OrderResult(
            status=OrderStatus.FILLED,
            broker_id="BROKER-001",
            filled_quantity=order.quantity,
            avg_price=1.1234,
            fee=0.50,
        )

    def cancel_order(self, broker_order_id: str) -> OrderResult:
        self._cancel_calls.append(broker_order_id)
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
        self._close_calls.append((broker_position_id, volume, symbol))
        if self._close_result is not None:
            return self._close_result
        return OrderResult(
            status=OrderStatus.FILLED,
            broker_id=broker_position_id,
            filled_quantity=volume,
        )

    def set_stop_loss(
        self,
        position_ticket: int,
        symbol: str,
        stop_loss_price: float,
        take_profit: float | None = None,
    ) -> bool:
        return True

    def get_account_info(self) -> AccountInfo:
        return self._account_info


# ---------------------------------------------------------------------------
# Mock risk engine
# ---------------------------------------------------------------------------


class MockRiskEngine:
    """Mock risk engine with configurable pass/fail."""

    def __init__(self, approved: bool = True, reason: str = "", exception: Exception | None = None):
        self._approved = approved
        self._reason = reason
        self._exception = exception
        self._check_calls: list[Order] = []

    def check_order_sync(self, order: Order):
        self._check_calls.append(order)
        if self._exception is not None:
            raise self._exception
        result = MagicMock()
        result.passed = self._approved
        result.reason = self._reason
        return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_ledger(tmp_path):
    return tmp_path / "test_ledger.jsonl"


@pytest.fixture
def mock_adapter():
    return MockBrokerAdapter()


@pytest.fixture
def oms(mock_adapter, tmp_ledger):
    return OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)


@pytest.fixture
def oms_with_risk(mock_adapter, tmp_ledger):
    risk = MockRiskEngine(approved=True)
    return OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger, risk_engine=risk)


def _make_order_kwargs(
    signal_id: str = "SIG-TEST",
    symbol: str = "XAUUSD",
    asset_class: str = "metals",
    side: str = "BUY",
    quantity: float = 0.1,
) -> dict:
    return dict(signal_id=signal_id, symbol=symbol, asset_class=asset_class, side=side, quantity=quantity)


# ===================================================================
# 1. Order creation and submission
# ===================================================================


class TestSubmitOrderValid:
    """submit_order with a valid order should produce FILLED status."""

    def test_submit_order_filled(self, oms, mock_adapter):
        order = oms.submit_order(**_make_order_kwargs())
        assert order.status == OrderStatus.FILLED
        assert order.order_id is not None
        assert order.signal_id == "SIG-TEST"

    def test_submit_order_has_broker_id(self, oms, mock_adapter):
        """After fix: submit_order propagates broker_order_id from adapter result."""
        order = oms.submit_order(**_make_order_kwargs())
        assert order.broker_order_id == "BROKER-001"
        # And it's in the ledger too
        lines = [l.strip() for l in oms._ledger_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        broker_ids = [json.loads(l).get("broker_order_id") for l in lines]
        assert "BROKER-001" in broker_ids

    def test_submit_order_with_sl_tp(self, oms):
        order = oms.submit_order(
            **_make_order_kwargs(),
            stop_loss=2000.0,
            take_profit=2010.0,
        )
        assert order.status == OrderStatus.FILLED


class TestSubmitOrderInvalid:
    """submit_order with missing fields should raise or fail."""

    def test_submit_order_empty_symbol(self, oms):
        order = oms.submit_order(
            signal_id="SIG-NO-SYMBOL",
            symbol="",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
        )
        # OMS doesn't validate symbol; adapter handles it
        assert order.status in (OrderStatus.FILLED, OrderStatus.FAILED)

    def test_submit_order_zero_quantity(self, oms):
        order = oms.submit_order(
            signal_id="SIG-ZERO-QTY",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.0,
        )
        assert order.order_id is not None

    def test_submit_order_unknown_asset_class_raises(self, oms):
        with pytest.raises(ValueError, match="No venue mapped"):
            oms.submit_order(
                signal_id="SIG-BAD-ASSET",
                symbol="XYZ",
                asset_class="unknown_class",
                side="BUY",
                quantity=0.1,
            )


class TestSubmitOrderIdempotency:
    """Same signal_id twice must return the same order, no duplicate broker call."""

    def test_duplicate_returns_same_order(self, oms):
        o1 = oms.submit_order(**_make_order_kwargs(signal_id="SIG-IDEMP"))
        o2 = oms.submit_order(**_make_order_kwargs(signal_id="SIG-IDEMP"))
        assert o1.order_id == o2.order_id

    def test_duplicate_no_second_broker_call(self, oms, mock_adapter):
        oms.submit_order(**_make_order_kwargs(signal_id="SIG-IDEMP-NO2"))
        before = len(mock_adapter._submit_calls)
        oms.submit_order(**_make_order_kwargs(signal_id="SIG-IDEMP-NO2"))
        assert len(mock_adapter._submit_calls) == before

    def test_different_signal_ids_different_orders(self, oms):
        o1 = oms.submit_order(**_make_order_kwargs(signal_id="SIG-A"))
        o2 = oms.submit_order(**_make_order_kwargs(signal_id="SIG-B"))
        assert o1.order_id != o2.order_id


class TestSubmitOrderCrashRecovery:
    """Ledger replay must reconstruct orders on restart."""

    def test_ledger_reload_reconstructs_orders(self, mock_adapter, tmp_ledger):
        oms1 = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        o1 = oms1.submit_order(**_make_order_kwargs(signal_id="SIG-CRASH"))

        oms2 = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        found = oms2.order_by_signal("SIG-CRASH")
        assert found is not None
        assert found.order_id == o1.order_id

    def test_ledger_reload_preserves_status(self, mock_adapter, tmp_ledger):
        oms1 = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        o1 = oms1.submit_order(**_make_order_kwargs(signal_id="SIG-CRASH-2"))

        oms2 = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        found = oms2.order_by_signal("SIG-CRASH-2")
        assert found is not None
        assert found.status == o1.status


class TestSubmitOrderRiskGate:
    """submit_order must pass through the risk engine when provided."""

    def test_risk_engine_called(self, mock_adapter, tmp_ledger):
        risk = MockRiskEngine(approved=True)
        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger, risk_engine=risk)
        oms.submit_order(**_make_order_kwargs(signal_id="SIG-RISK-CALL"))
        assert len(risk._check_calls) == 1
        assert risk._check_calls[0].symbol == "XAUUSD"

    def test_risk_engine_not_called_when_none(self, oms):
        oms.submit_order(**_make_order_kwargs(signal_id="SIG-NO-RISK"))
        assert oms._risk_engine is None


# ===================================================================
# 2. Order state machine
# ===================================================================


class TestStateMachineHappyPath:
    """Full lifecycle: SIGNAL_CREATED → RISK_CHECKED → ORDER_PRECHECKED → ORDER_SUBMITTED → FILLED."""

    def test_full_happy_path(self, oms):
        order = oms.submit_order(**_make_order_kwargs(signal_id="SIG-SM-HAPPY"))
        history = oms.get_state_history(order.order_id)
        assert "SIGNAL_CREATED" in history
        assert "RISK_CHECKED" in history
        assert "ORDER_PRECHECKED" in history
        assert "ORDER_SUBMITTED" in history
        assert "FILLED" in history

    def test_state_machine_exists_for_order(self, oms):
        order = oms.submit_order(**_make_order_kwargs(signal_id="SIG-SM-EXISTS"))
        sm = oms.get_state_machine(order.order_id)
        assert sm is not None
        assert sm.state == OrderStatus.FILLED


class TestStateMachineRejection:
    """SIGNAL_CREATED → REJECTED (risk gate blocks)."""

    def test_risk_rejection_transitions_to_rejected(self, mock_adapter, tmp_ledger):
        risk = MockRiskEngine(approved=False, reason="Daily loss limit")
        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger, risk_engine=risk)
        order = oms.submit_order(**_make_order_kwargs(signal_id="SIG-SM-REJ"))
        history = oms.get_state_history(order.order_id)
        assert "SIGNAL_CREATED" in history
        assert "REJECTED" in history

    def test_risk_rejection_blocks_broker(self, mock_adapter, tmp_ledger):
        risk = MockRiskEngine(approved=False, reason="Max positions")
        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger, risk_engine=risk)
        oms.submit_order(**_make_order_kwargs(signal_id="SIG-SM-REJ-2"))
        assert len(mock_adapter._submit_calls) == 0


class TestStateMachineTimeout:
    """ORDER_SUBMITTED → TIMEOUT when broker times out."""

    def test_broker_timeout(self, mock_adapter, tmp_ledger):
        mock_adapter._submit_result = OrderResult(
            status=OrderStatus.TIMEOUT,
            error="Connection timeout",
        )
        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        order = oms.submit_order(**_make_order_kwargs(signal_id="SIG-TIMEOUT"))
        assert order.status == OrderStatus.TIMEOUT
        history = oms.get_state_history(order.order_id)
        assert "TIMEOUT" in history or "REJECTED" in history


class TestStateMachinePartialFill:
    """ORDER_SUBMITTED → PARTIAL_FILL → FILLED."""

    def test_partial_fill_polls_to_filled(self, mock_adapter, tmp_ledger):
        call_count = 0

        def mock_status(bid):
            nonlocal call_count
            call_count += 1
            return OrderResult(
                status=OrderStatus.FILLED,
                broker_id=bid,
                filled_quantity=0.1,
                avg_price=1.1234,
            )

        mock_adapter._submit_result = OrderResult(
            status=OrderStatus.PARTIALLY_FILLED,
            broker_id="BROKER-PARTIAL",
            filled_quantity=0.05,
            avg_price=1.1230,
        )
        mock_adapter.get_order_status = mock_status

        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        order = oms.submit_order(**_make_order_kwargs(signal_id="SIG-PART-FILL"))
        assert order.status in (OrderStatus.FILLED, OrderStatus.TIMEOUT)

    def test_partial_fill_timeout(self, mock_adapter, tmp_ledger):
        mock_adapter._submit_result = OrderResult(
            status=OrderStatus.PARTIALLY_FILLED,
            broker_id="BROKER-PART-TMO",
            filled_quantity=0.05,
            avg_price=1.1230,
        )
        mock_adapter.get_order_status = lambda bid: OrderResult(
            status=OrderStatus.PARTIALLY_FILLED,
            broker_id=bid,
            filled_quantity=0.05,
            avg_price=1.1230,
        )

        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        with patch("graxia.packages.quant_os.execution.oms._FILL_TIMEOUT", 0.1):
            order = oms.submit_order(**_make_order_kwargs(signal_id="SIG-PART-TMO"))
        assert order.status == OrderStatus.TIMEOUT


class TestStateMachineOrderRejected:
    """ORDER_SUBMITTED → REJECTED (broker permanently rejects)."""

    def test_broker_failed_transitions_to_rejected_or_failed(self, mock_adapter, tmp_ledger):
        mock_adapter._submit_result = OrderResult(
            status=OrderStatus.FAILED,
            error="Insufficient margin",
        )
        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        order = oms.submit_order(**_make_order_kwargs(signal_id="SIG-BROKER-REJ"))
        assert order.status == OrderStatus.FAILED


# ===================================================================
# 3. Close position
# ===================================================================


class TestClosePosition:
    """close_position: success, failure, idempotency."""

    def test_close_position_success(self, oms, mock_adapter):
        order = oms.close_position(
            symbol="XAUUSD",
            broker_position_id="POS-001",
            volume=0.1,
            asset_class="metals",
        )
        assert order.status == OrderStatus.FILLED
        assert order.order_id == "close-POS-001"
        assert order.symbol == "XAUUSD"
        assert len(mock_adapter._close_calls) == 1

    def test_close_position_failure(self, oms, mock_adapter):
        mock_adapter._close_result = OrderResult(
            status=OrderStatus.FAILED,
            error="Position not found",
        )
        order = oms.close_position(
            symbol="XAUUSD",
            broker_position_id="POS-BAD",
            volume=0.1,
            asset_class="metals",
        )
        assert order.status == OrderStatus.FAILED

    def test_close_position_exception_returns_failed(self, oms, mock_adapter):
        mock_adapter.close_position = MagicMock(side_effect=ConnectionError("Broker down"))
        order = oms.close_position(
            symbol="XAUUSD",
            broker_position_id="POS-ERR",
            volume=0.1,
            asset_class="metals",
        )
        assert order.status == OrderStatus.FAILED

    def test_close_position_idempotent(self, oms, mock_adapter):
        o1 = oms.close_position(
            symbol="XAUUSD",
            broker_position_id="POS-IDEMP",
            volume=0.1,
            asset_class="metals",
        )
        o2 = oms.close_position(
            symbol="XAUUSD",
            broker_position_id="POS-IDEMP",
            volume=0.1,
            asset_class="metals",
        )
        assert o1.order_id == o2.order_id

    def test_close_position_negative_volume_uses_buy(self, oms):
        order = oms.close_position(
            symbol="XAUUSD",
            broker_position_id="POS-NEG",
            volume=-0.1,
            asset_class="metals",
        )
        assert order.side == "BUY"

    def test_close_position_positive_volume_uses_sell(self, oms):
        order = oms.close_position(
            symbol="XAUUSD",
            broker_position_id="POS-POS",
            volume=0.1,
            asset_class="metals",
        )
        assert order.side == "SELL"


# ===================================================================
# 4. Ledger persistence
# ===================================================================


class TestLedgerPersistSubmit:
    """Ledger must be written on order submit."""

    def test_ledger_written_on_submit(self, oms, tmp_ledger):
        oms.submit_order(**_make_order_kwargs(signal_id="SIG-LED-SUB"))
        assert tmp_ledger.exists()
        lines = [l.strip() for l in tmp_ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) >= 1
        record = json.loads(lines[0])
        assert record["signal_id"] == "SIG-LED-SUB"

    def test_ledger_contains_all_fields(self, oms, tmp_ledger):
        oms.submit_order(**_make_order_kwargs(signal_id="SIG-LED-FIELDS"))
        lines = [l.strip() for l in tmp_ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
        record = json.loads(lines[-1])
        for key in ("order_id", "signal_id", "symbol", "asset_class", "side", "quantity", "status", "created_at"):
            assert key in record


class TestLedgerPersistFill:
    """Ledger must be written on fill."""

    def test_ledger_records_filled_status(self, oms, tmp_ledger):
        oms.submit_order(**_make_order_kwargs(signal_id="SIG-LED-FILL"))
        lines = [l.strip() for l in tmp_ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
        statuses = [json.loads(l)["status"] for l in lines]
        assert "FILLED" in statuses


class TestLedgerPersistClose:
    """Ledger must be written on close_position."""

    def test_close_position_written_to_ledger(self, oms, tmp_ledger):
        """After fix: close_position writes to ledger."""
        order = oms.close_position(
            symbol="XAUUSD",
            broker_position_id="POS-LED",
            volume=0.1,
            asset_class="metals",
        )
        assert tmp_ledger.exists()
        lines = [l.strip() for l in tmp_ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) >= 1
        record = json.loads(lines[-1])
        assert record["order_id"] == "close-POS-LED"
        assert record["status"] == "FILLED"


class TestLedgerCrashRecovery:
    """Ledger replay must reconstruct order from events."""

    def test_full_replay_multiple_events(self, mock_adapter, tmp_ledger):
        """Each submit_order writes 2 ledger entries: SUBMITTED + FILLED."""
        oms1 = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        o1 = oms1.submit_order(**_make_order_kwargs(signal_id="SIG-REPLAY"))

        # Count lines in ledger for this order
        lines = [l.strip() for l in tmp_ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
        order_events = [l for l in lines if "SIG-REPLAY" in l]
        # SUBMITTED + FILLED = 2 events
        assert len(order_events) >= 2

        # Replay reconstructs order
        oms2 = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        history = oms2.get_state_history(o1.order_id)
        assert len(history) >= 2

    def test_replay_preserves_order_count(self, mock_adapter, tmp_ledger):
        oms1 = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        oms1.submit_order(**_make_order_kwargs(signal_id="SIG-CNT-1"))
        oms1.submit_order(**_make_order_kwargs(signal_id="SIG-CNT-2"))

        oms2 = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        assert oms2.order_by_signal("SIG-CNT-1") is not None
        assert oms2.order_by_signal("SIG-CNT-2") is not None


class TestLedgerCompaction:
    """Ledger compaction deduplicates by order_id and drops old entries."""

    def test_compact_removes_duplicate_events(self, oms, tmp_ledger):
        oms.submit_order(**_make_order_kwargs(signal_id="SIG-COMP"))
        line_before = oms._line_count()
        oms.compact_ledger()
        line_after = oms._line_count()
        assert line_after <= line_before

    def test_compact_empty_ledger_returns_false(self, oms, tmp_ledger):
        assert oms.compact_ledger() is False

    def test_compact_preserves_latest_status(self, mock_adapter, tmp_ledger):
        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        oms.submit_order(**_make_order_kwargs(signal_id="SIG-COMP2"))
        oms.compact_ledger()
        found = oms.order_by_signal("SIG-COMP2")
        assert found is not None
        assert found.status == OrderStatus.FILLED


# ===================================================================
# 5. Risk integration
# ===================================================================


class TestPreTradeRiskGate:
    """PreTradeRiskGate blocks high-risk and allows low-risk orders."""

    def test_risk_blocks_high_risk(self, mock_adapter, tmp_ledger):
        risk = MockRiskEngine(approved=False, reason="Position size too large")
        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger, risk_engine=risk)
        order = oms.submit_order(**_make_order_kwargs(signal_id="SIG-RISK-HIGH"))
        assert order.status == OrderStatus.REJECTED

    def test_risk_allows_low_risk(self, mock_adapter, tmp_ledger):
        risk = MockRiskEngine(approved=True)
        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger, risk_engine=risk)
        order = oms.submit_order(**_make_order_kwargs(signal_id="SIG-RISK-LOW"))
        assert order.status == OrderStatus.FILLED

    def test_risk_exception_fail_closed(self, mock_adapter, tmp_ledger):
        risk = MockRiskEngine(exception=RuntimeError("Risk engine crash"))
        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger, risk_engine=risk)
        order = oms.submit_order(**_make_order_kwargs(signal_id="SIG-RISK-ERR"))
        assert order.status == OrderStatus.REJECTED


class TestCircuitBreakerIntegration:
    """Circuit breaker (risk engine) must block orders when triggered."""

    def test_circuit_breaker_blocks_order(self, mock_adapter, tmp_ledger):
        risk = MockRiskEngine(approved=False, reason="Circuit breaker triggered")
        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger, risk_engine=risk)
        order = oms.submit_order(**_make_order_kwargs(signal_id="SIG-CB"))
        assert order.status == OrderStatus.REJECTED
        assert len(mock_adapter._submit_calls) == 0

    def test_circuit_breaker_tracks_order_for_audit(self, mock_adapter, tmp_ledger):
        risk = MockRiskEngine(approved=False, reason="CB active")
        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger, risk_engine=risk)
        oms.submit_order(**_make_order_kwargs(signal_id="SIG-CB-2"))
        assert len(risk._check_calls) == 1


class TestKillSwitchIntegration:
    """Kill switch (cancel_all) must cancel all open orders."""

    def test_kill_switch_cancels_all(self, mock_adapter, tmp_ledger):
        mock_adapter._submit_result = OrderResult(
            status=OrderStatus.SUBMITTED,
            broker_id="BROKER-KS",
        )
        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        oms.submit_order(**_make_order_kwargs(signal_id="SIG-KS-1"))
        cancelled = oms.cancel_all()
        for o in cancelled:
            assert o.status in (OrderStatus.CANCELLED, OrderStatus.FAILED)

    def test_kill_switch_skips_terminal_orders(self, oms, mock_adapter):
        oms.submit_order(**_make_order_kwargs(signal_id="SIG-KS-TERM"))
        cancelled = oms.cancel_all()
        for o in cancelled:
            assert o.order_id != "SIG-KS-TERM" or o.status not in (
                OrderStatus.FILLED,
                OrderStatus.CANCELLED,
                OrderStatus.FAILED,
                OrderStatus.TIMEOUT,
            )

    def test_kill_switch_with_asset_class_filter(self, mock_adapter, tmp_ledger):
        mock_adapter._submit_result = OrderResult(
            status=OrderStatus.SUBMITTED,
            broker_id="BROKER-KS-FLT",
        )
        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        oms.submit_order(**_make_order_kwargs(signal_id="SIG-KS-M", asset_class="metals"))
        cancelled = oms.cancel_all(asset_class="metals")
        for o in cancelled:
            assert o.asset_class.lower() == "metals"


# ===================================================================
# 6. Error handling
# ===================================================================


class TestBrokerTimeout:
    """Broker timeout results in TIMEOUT status."""

    def test_broker_timeout_sets_timeout(self, mock_adapter, tmp_ledger):
        mock_adapter._submit_result = OrderResult(
            status=OrderStatus.TIMEOUT,
            error="Connection timed out",
        )
        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        order = oms.submit_order(**_make_order_kwargs(signal_id="SIG-TMO"))
        assert order.status == OrderStatus.TIMEOUT

    def test_broker_timeout_recorded_in_ledger(self, mock_adapter, tmp_ledger):
        mock_adapter._submit_result = OrderResult(
            status=OrderStatus.TIMEOUT,
            error="Timeout",
        )
        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        oms.submit_order(**_make_order_kwargs(signal_id="SIG-TMO-LED"))
        lines = [l.strip() for l in tmp_ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
        statuses = [json.loads(l)["status"] for l in lines]
        assert "TIMEOUT" in statuses


class TestBrokerRejection:
    """Broker rejection results in FAILED status."""

    def test_broker_rejection_sets_failed(self, mock_adapter, tmp_ledger):
        mock_adapter._submit_result = OrderResult(
            status=OrderStatus.FAILED,
            error="Insufficient margin",
        )
        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        order = oms.submit_order(**_make_order_kwargs(signal_id="SIG-REJ-BRK"))
        assert order.status == OrderStatus.FAILED

    def test_broker_rejection_recorded_in_ledger(self, mock_adapter, tmp_ledger):
        mock_adapter._submit_result = OrderResult(
            status=OrderStatus.FAILED,
            error="Rejected",
        )
        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        oms.submit_order(**_make_order_kwargs(signal_id="SIG-REJ-LED"))
        lines = [l.strip() for l in tmp_ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
        statuses = [json.loads(l)["status"] for l in lines]
        assert "FAILED" in statuses


class TestNetworkError:
    """Network error during broker call propagates as FAILED."""

    def test_network_error_on_submit(self, mock_adapter, tmp_ledger):
        mock_adapter.submit_order = MagicMock(side_effect=ConnectionError("Network unreachable"))
        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        with pytest.raises(ConnectionError):
            oms.submit_order(**_make_order_kwargs(signal_id="SIG-NET"))

    def test_network_error_on_close(self, oms, mock_adapter):
        mock_adapter.close_position = MagicMock(side_effect=ConnectionError("Network down"))
        order = oms.close_position(
            symbol="XAUUSD",
            broker_position_id="POS-NET",
            volume=0.1,
            asset_class="metals",
        )
        assert order.status == OrderStatus.FAILED


class TestInvalidSymbol:
    """Invalid symbol should be handled by the adapter."""

    def test_invalid_symbol_adapter_returns_failed(self, mock_adapter, tmp_ledger):
        mock_adapter._submit_result = OrderResult(
            status=OrderStatus.FAILED,
            error="Symbol not found",
        )
        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        order = oms.submit_order(
            **_make_order_kwargs(
                signal_id="SIG-BAD-SYM",
                symbol="INVALIDSYM",
            )
        )
        assert order.status == OrderStatus.FAILED


# ===================================================================
# 7. Cancel order
# ===================================================================


class TestCancelAll:
    """cancel_all as kill-switch."""

    def test_cancel_all_returns_list(self, oms):
        cancelled = oms.cancel_all()
        assert isinstance(cancelled, list)

    def test_cancel_all_no_open_orders(self, oms):
        cancelled = oms.cancel_all()
        assert len(cancelled) == 0


# ===================================================================
# 8. Query helpers
# ===================================================================


class TestQueryHelpers:
    """order_by_id, order_by_signal, get_state_history."""

    def test_order_by_id_found(self, oms):
        order = oms.submit_order(**_make_order_kwargs(signal_id="SIG-QH"))
        assert oms.order_by_id(order.order_id) is not None

    def test_order_by_id_not_found(self, oms):
        assert oms.order_by_id("nonexistent") is None

    def test_order_by_signal_found(self, oms):
        oms.submit_order(**_make_order_kwargs(signal_id="SIG-QH-SIG"))
        assert oms.order_by_signal("SIG-QH-SIG") is not None

    def test_order_by_signal_not_found(self, oms):
        assert oms.order_by_signal("nonexistent") is None

    def test_get_state_history_returns_list(self, oms):
        order = oms.submit_order(**_make_order_kwargs(signal_id="SIG-QH-HIST"))
        history = oms.get_state_history(order.order_id)
        assert isinstance(history, list)
        assert len(history) > 0

    def test_get_state_history_unknown_returns_empty(self, oms):
        assert oms.get_state_history("nonexistent") == []


# ===================================================================
# 9. Adapter routing
# ===================================================================


class TestAdapterRouting:
    """Orders route to the correct adapter by asset_class."""

    def test_metals_routes_to_mt5(self, oms):
        adapter = oms._get_adapter("metals")
        assert adapter.name == "mock_mt5"  # Mock adapter name

    def test_forex_routes_to_mt5(self, oms):
        adapter = oms._get_adapter("forex")
        assert adapter.name == "mock_mt5"

    def test_indices_routes_to_mt5(self, oms):
        adapter = oms._get_adapter("indices")
        assert adapter.name == "mock_mt5"

    def test_crypto_routes_to_mt5(self, oms):
        adapter = oms._get_adapter("crypto")
        assert adapter.name == "mock_mt5"

    def test_unknown_asset_class_raises(self, oms):
        with pytest.raises(ValueError, match="No venue mapped"):
            oms._get_adapter("unknown")


# ===================================================================
# 10. Account info & positions
# ===================================================================


class TestAccountInfoAndPositions:
    """get_account_info and get_positions delegation to adapter."""

    def test_get_account_info(self, oms):
        info = oms.get_account_info("mt5")
        assert isinstance(info, AccountInfo)
        assert info.equity == 10000.0

    def test_get_positions(self, oms):
        positions = oms.get_positions("mt5")
        assert isinstance(positions, list)

    def test_get_account_info_unknown_venue_raises(self, oms):
        with pytest.raises(RuntimeError, match="not registered"):
            oms.get_account_info("binance")

    def test_get_positions_unknown_venue_raises(self, oms):
        with pytest.raises(RuntimeError, match="not registered"):
            oms.get_positions("binance")


# ===================================================================
# 11. Stop-loss configuration
# ===================================================================


class TestTrailingStopConfig:
    """TrailingStopConfig and symbol_stop_configs defaults."""

    def test_default_trailing_configs_exist(self):
        from graxia.packages.quant_os.execution.oms import _DEFAULT_TRAILING_CONFIGS

        assert "metals" in _DEFAULT_TRAILING_CONFIGS
        assert "forex" in _DEFAULT_TRAILING_CONFIGS

    def test_symbol_stop_configs_exist(self):
        from graxia.packages.quant_os.execution.oms import _SYMBOL_STOP_CONFIGS

        assert "XAUUSD" in _SYMBOL_STOP_CONFIGS
        assert "NAS100" in _SYMBOL_STOP_CONFIGS
        assert len(_SYMBOL_STOP_CONFIGS) >= 4

    def test_custom_trailing_configs(self, mock_adapter, tmp_ledger):
        from graxia.packages.quant_os.execution.oms import TrailingStopConfig

        custom = {"metals": TrailingStopConfig(enabled=False)}
        oms = OMS(
            adapters={"mt5": mock_adapter},
            ledger_path=tmp_ledger,
            trailing_stop_configs=custom,
        )
        assert oms._trailing_stop_configs["metals"].enabled is False
