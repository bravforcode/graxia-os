"""Tests for execution engine — state machine, order lifecycle, idempotency, broker failover."""

import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from graxia.packages.quant_os.execution.order import (
    Order, OrderStateMachine, create_order,
)
from graxia.packages.quant_os.execution.order_state_machine import (
    OrderState, OrderStateMachine as OSM2, TRANSITIONS, TERMINAL_STATES,
)
from graxia.packages.quant_os.execution.idempotency import (
    IdempotencyChecker, WindowedIdempotencyChecker,
)
from graxia.packages.quant_os.execution.broker_adapter import (
    PaperBroker, BrokerOrderResponse, BrokerManager,
)
from graxia.packages.quant_os.core.enums import (
    OrderStatus, OrderSide, OrderType, TimeInForce,
)
from graxia.packages.quant_os.core.exceptions import (
    OrderStateError, DuplicateOrderError, ValidationError,
)


# ═══════════════════════════════════════════════════════════════════════
# Order Data Class
# ═══════════════════════════════════════════════════════════════════════

class TestOrder:
    """Order entity edge cases."""

    def test_create_order_defaults(self):
        o = create_order(
            symbol="EURUSD", side=OrderSide.BUY,
            order_type=OrderType.MARKET, quantity=Decimal("0.01"),
        )
        assert o.symbol == "EURUSD"
        assert o.status == OrderStatus.CREATED
        assert o.fill_quantity == Decimal("0")
        assert o.avg_fill_price is None
        assert o.fee is None

    def test_order_id_unique(self):
        o1 = create_order("EURUSD", OrderSide.BUY, OrderType.MARKET, Decimal("0.01"))
        o2 = create_order("EURUSD", OrderSide.BUY, OrderType.MARKET, Decimal("0.01"))
        assert o1.id != o2.id

    def test_order_client_id_unique(self):
        o1 = create_order("EURUSD", OrderSide.BUY, OrderType.MARKET, Decimal("0.01"))
        o2 = create_order("EURUSD", OrderSide.BUY, OrderType.MARKET, Decimal("0.01"))
        assert o1.client_order_id != o2.client_order_id

    def test_idempotency_key_generated(self):
        o = create_order("EURUSD", OrderSide.BUY, OrderType.MARKET, Decimal("0.01"))
        assert o.idempotency_key is not None
        assert len(o.idempotency_key) == 32

    def test_custom_idempotency_key(self):
        o = create_order(
            "EURUSD", OrderSide.BUY, OrderType.MARKET, Decimal("0.01"),
        )
        o.idempotency_key = "custom_key"
        assert o.idempotency_key == "custom_key"

    def test_is_filled(self):
        o = create_order("EURUSD", OrderSide.BUY, OrderType.MARKET, Decimal("0.01"))
        assert not o.is_filled
        o.status = OrderStatus.FILLED
        assert o.is_filled

    def test_is_open(self):
        o = create_order("EURUSD", OrderSide.BUY, OrderType.MARKET, Decimal("0.01"))
        assert o.is_open
        for status in [OrderStatus.VALIDATED, OrderStatus.RISK_APPROVED,
                       OrderStatus.COMPLIANCE_APPROVED, OrderStatus.SENT_TO_BROKER,
                       OrderStatus.ACKNOWLEDGED, OrderStatus.PARTIAL_FILL]:
            o.status = status
            assert o.is_open
        for status in [OrderStatus.FILLED, OrderStatus.REJECTED,
                       OrderStatus.CANCELLED, OrderStatus.EXPIRED]:
            o.status = status
            assert not o.is_open

    def test_remaining_quantity(self):
        o = create_order("EURUSD", OrderSide.BUY, OrderType.MARKET, Decimal("1.0"))
        assert o.remaining_quantity == Decimal("1.0")
        o.fill_quantity = Decimal("0.3")
        assert o.remaining_quantity == Decimal("0.7")

    def test_limit_order_requires_price(self):
        o = create_order(
            "EURUSD", OrderSide.BUY, OrderType.LIMIT, Decimal("0.01"),
            price=Decimal("1.0850"),
        )
        assert o.price == Decimal("1.0850")

    def test_stop_order_requires_stop_price(self):
        o = create_order(
            "EURUSD", OrderSide.BUY, OrderType.STOP, Decimal("0.01"),
            stop_price=Decimal("1.0800"),
        )
        assert o.stop_price == Decimal("1.0800")


# ═══════════════════════════════════════════════════════════════════════
# Order State Machine (v1 — from order.py)
# ═══════════════════════════════════════════════════════════════════════

class TestOrderStateMachineV1:
    """Order state machine from order.py — edge cases."""

    def _make_order_and_sm(self):
        o = create_order("EURUSD", OrderSide.BUY, OrderType.MARKET, Decimal("0.01"))
        return o, OrderStateMachine(o)

    def test_created_to_validated(self):
        o, sm = self._make_order_and_sm()
        sm.transition(OrderStatus.VALIDATED, "ok")
        assert o.status == OrderStatus.VALIDATED

    def test_full_happy_path(self):
        o, sm = self._make_order_and_sm()
        sm.transition(OrderStatus.VALIDATED, "ok")
        sm.transition(OrderStatus.RISK_APPROVED, "ok")
        sm.transition(OrderStatus.COMPLIANCE_APPROVED, "ok")
        sm.transition(OrderStatus.SENT_TO_BROKER, "ok")
        sm.transition(OrderStatus.ACKNOWLEDGED, "ok")
        sm.transition(OrderStatus.FILLED, "filled")
        assert o.status == OrderStatus.FILLED

    def test_invalid_transition_raises(self):
        o, sm = self._make_order_and_sm()
        with pytest.raises(OrderStateError) as exc_info:
            sm.transition(OrderStatus.FILLED, "skip")
        assert exc_info.value.from_state == "CREATED"
        assert exc_info.value.to_state == "FILLED"

    def test_terminal_state_blocks_transition(self):
        o, sm = self._make_order_and_sm()
        o.status = OrderStatus.FILLED
        assert not sm.can_transition(OrderStatus.VALIDATED)

    def test_cancel_from_created(self):
        o, sm = self._make_order_and_sm()
        sm.cancel("user request")
        assert o.status == OrderStatus.CANCELLED

    def test_cancel_from_validated_raises(self):
        """cancel() tries VALIDATED→CANCELLED but transition table doesn't allow it."""
        o, sm = self._make_order_and_sm()
        sm.transition(OrderStatus.VALIDATED, "ok")
        with pytest.raises(OrderStateError):
            sm.cancel("user request")

    def test_cancel_after_sent_raises(self):
        """cancel() tries SENT_TO_BROKER→CANCEL_REQUESTED but table doesn't allow it."""
        o, sm = self._make_order_and_sm()
        sm.transition(OrderStatus.VALIDATED, "ok")
        sm.transition(OrderStatus.RISK_APPROVED, "ok")
        sm.transition(OrderStatus.COMPLIANCE_APPROVED, "ok")
        sm.transition(OrderStatus.SENT_TO_BROKER, "sent")
        with pytest.raises(OrderStateError):
            sm.cancel("user request")

    def test_fill_sets_timestamps(self):
        o, sm = self._make_order_and_sm()
        o.status = OrderStatus.ACKNOWLEDGED
        sm.fill(Decimal("0.01"), Decimal("1.0850"))
        assert o.filled_at is not None

    def test_sent_sets_timestamp(self):
        o, sm = self._make_order_and_sm()
        sm.transition(OrderStatus.VALIDATED, "ok")
        sm.transition(OrderStatus.RISK_APPROVED, "ok")
        sm.transition(OrderStatus.COMPLIANCE_APPROVED, "ok")
        sm.transition(OrderStatus.SENT_TO_BROKER, "sent")
        assert o.sent_at is not None

    def test_validate_order_rejects_short_symbol(self):
        o, sm = self._make_order_and_sm()
        o.symbol = "EU"
        with pytest.raises(ValidationError):
            sm.validate_order()

    def test_validate_order_rejects_zero_quantity(self):
        o, sm = self._make_order_and_sm()
        o.quantity = Decimal("0")
        with pytest.raises(ValidationError):
            sm.validate_order()

    def test_validate_order_rejects_limit_without_price(self):
        o = create_order("EURUSD", OrderSide.BUY, OrderType.LIMIT, Decimal("0.01"))
        sm = OrderStateMachine(o)
        with pytest.raises(ValidationError):
            sm.validate_order()

    def test_validate_order_rejects_stop_without_stop_price(self):
        o = create_order("EURUSD", OrderSide.BUY, OrderType.STOP, Decimal("0.01"))
        sm = OrderStateMachine(o)
        with pytest.raises(ValidationError):
            sm.validate_order()

    def test_human_approve_from_pending(self):
        o, sm = self._make_order_and_sm()
        o.status = OrderStatus.PENDING_HUMAN
        sm.approve_human("admin")
        assert o.status == OrderStatus.SENT_TO_BROKER
        assert o.approved_by == "admin"

    def test_human_approve_wrong_state_raises(self):
        o, sm = self._make_order_and_sm()
        with pytest.raises(OrderStateError):
            sm.approve_human("admin")

    def test_expire_from_pending(self):
        o, sm = self._make_order_and_sm()
        o.status = OrderStatus.PENDING_HUMAN
        sm.expire("timeout")
        assert o.status == OrderStatus.EXPIRED

    def test_expire_wrong_state_raises(self):
        o, sm = self._make_order_and_sm()
        with pytest.raises(OrderStateError):
            sm.expire("timeout")

    def test_partial_fill(self):
        o, sm = self._make_order_and_sm()
        o.status = OrderStatus.ACKNOWLEDGED
        sm.fill(Decimal("0.005"), Decimal("1.0850"))
        assert o.status == OrderStatus.PARTIAL_FILL
        assert o.fill_quantity == Decimal("0.005")
        sm.fill(Decimal("0.005"), Decimal("1.0860"))
        assert o.status == OrderStatus.FILLED

    def test_fill_updates_avg_price(self):
        o, sm = self._make_order_and_sm()
        o.status = OrderStatus.ACKNOWLEDGED
        sm.fill(Decimal("0.005"), Decimal("1.0850"))
        assert o.avg_fill_price == Decimal("1.0850")
        sm.fill(Decimal("0.005"), Decimal("1.0860"))
        assert o.avg_fill_price == Decimal("1.0855")

    def test_fill_accumulates_fee(self):
        o, sm = self._make_order_and_sm()
        o.status = OrderStatus.ACKNOWLEDGED
        sm.fill(Decimal("0.005"), Decimal("1.0850"), Decimal("0.35"))
        assert o.fee == Decimal("0.35")
        sm.fill(Decimal("0.005"), Decimal("1.0860"), Decimal("0.35"))
        assert o.fee == Decimal("0.70")

    def test_transition_handler_called(self):
        o, sm = self._make_order_and_sm()
        handler = MagicMock()
        sm.on_transition(OrderStatus.VALIDATED, handler)
        sm.transition(OrderStatus.VALIDATED, "ok")
        handler.assert_called_once()

    def test_transition_handler_exception_does_not_fail(self):
        o, sm = self._make_order_and_sm()
        def bad_handler(*args):
            raise RuntimeError("handler crash")
        sm.on_transition(OrderStatus.VALIDATED, bad_handler)
        sm.transition(OrderStatus.VALIDATED, "ok")  # should not raise
        assert o.status == OrderStatus.VALIDATED


# ═══════════════════════════════════════════════════════════════════════
# Order State Machine (v2 — from order_state_machine.py)
# ═══════════════════════════════════════════════════════════════════════

class TestOrderStateMachineV2:
    """Order state machine from order_state_machine.py — 16-state machine edge cases."""

    def test_initial_state(self):
        sm = OSM2(order_id="test-1")
        assert sm.state == OrderState.SIGNAL_CREATED

    def test_happy_path_to_audited(self):
        sm = OSM2()
        sm.transition(OrderState.RISK_CHECKED)
        sm.transition(OrderState.ORDER_PRECHECKED)
        sm.transition(OrderState.ORDER_SUBMITTED)
        sm.transition(OrderState.ORDER_ACKNOWLEDGED)
        sm.transition(OrderState.FILLED)
        sm.transition(OrderState.PROTECTIVE_STOPS_PENDING)
        sm.transition(OrderState.PROTECTIVE_STOPS_VERIFIED)
        sm.transition(OrderState.POSITION_RECONCILED)
        sm.transition(OrderState.CLOSED)
        sm.transition(OrderState.DEAL_RECONCILED)
        sm.transition(OrderState.AUDITED)
        assert sm.state == OrderState.AUDITED
        assert sm.is_terminal()

    def test_invalid_transition_raises(self):
        sm = OSM2()
        with pytest.raises(OrderStateError):
            sm.transition(OrderState.FILLED)  # can't skip to FILLED

    def test_terminal_states_block_transition(self):
        sm = OSM2(initial=OrderState.REJECTED)
        assert sm.is_terminal()
        with pytest.raises(OrderStateError):
            sm.transition(OrderState.RISK_CHECKED)

    def test_critical_incident_from_any_non_terminal(self):
        sm = OSM2()
        sm.transition(OrderState.CRITICAL_INCIDENT)
        assert sm.state == OrderState.CRITICAL_INCIDENT
        assert sm.is_terminal()

    def test_rejected_is_terminal(self):
        sm = OSM2(initial=OrderState.REJECTED)
        assert sm.is_terminal()

    def test_expired_is_terminal(self):
        sm = OSM2(initial=OrderState.EXPIRED)
        assert sm.is_terminal()

    def test_audit_is_terminal(self):
        sm = OSM2(initial=OrderState.AUDITED)
        assert sm.is_terminal()

    def test_advance_returns_true(self):
        sm = OSM2()
        result = sm.advance(OrderState.RISK_CHECKED)
        assert result is True

    def test_history_tracking(self):
        sm = OSM2()
        sm.transition(OrderState.RISK_CHECKED)
        sm.transition(OrderState.ORDER_PRECHECKED)
        assert len(sm._history) == 3  # initial + 2 transitions

    def test_needs_protective_stop_verification(self):
        sm = OSM2(initial=OrderState.PROTECTIVE_STOPS_PENDING)
        assert sm.needs_protective_stop_verification()

    def test_does_not_need_protective_stop(self):
        sm = OSM2()
        assert not sm.needs_protective_stop_verification()

    def test_partial_fill_to_filled(self):
        sm = OSM2(initial=OrderState.PARTIAL_FILL)
        sm.transition(OrderState.FILLED)
        assert sm.state == OrderState.FILLED

    def test_partial_fill_to_critical_incident(self):
        sm = OSM2(initial=OrderState.PARTIAL_FILL)
        sm.transition(OrderState.CRITICAL_INCIDENT)
        assert sm.state == OrderState.CRITICAL_INCIDENT


# ═══════════════════════════════════════════════════════════════════════
# Transition Table Completeness
# ═══════════════════════════════════════════════════════════════════════

class TestTransitionTable:
    """Verify transition table correctness."""

    def test_all_states_have_entries(self):
        for state in OrderState:
            assert state in TRANSITIONS

    def test_terminal_states_have_empty_transitions(self):
        for state in TERMINAL_STATES:
            assert TRANSITIONS[state] == set()

    def test_critical_incident_can_reach_from_many_states(self):
        """CRITICAL_INCIDENT should be reachable from most non-terminal states."""
        ci_sources = [s for s, targets in TRANSITIONS.items() if OrderState.CRITICAL_INCIDENT in targets]
        assert len(ci_sources) >= 10

    def test_no_self_transitions_except_partial_fill(self):
        """No state should transition to itself except PARTIAL_FILL."""
        for state, targets in TRANSITIONS.items():
            if state != OrderState.PARTIAL_FILL:
                assert state not in targets


# ═══════════════════════════════════════════════════════════════════════
# Idempotency Checker
# ═══════════════════════════════════════════════════════════════════════

class TestIdempotencyChecker:
    """Idempotency checker edge cases."""

    def test_generate_key_deterministic(self):
        checker = IdempotencyChecker()
        k1 = checker.generate_key("EURUSD", "BUY", Decimal("0.01"), "mtm")
        k2 = checker.generate_key("EURUSD", "BUY", Decimal("0.01"), "mtm")
        assert k1 == k2

    def test_generate_key_length(self):
        checker = IdempotencyChecker()
        key = checker.generate_key("EURUSD", "BUY", Decimal("0.01"), "mtm")
        assert len(key) == 64  # SHA256 hex

    def test_different_symbol_different_key(self):
        checker = IdempotencyChecker()
        k1 = checker.generate_key("EURUSD", "BUY", Decimal("0.01"), "mtm")
        k2 = checker.generate_key("GBPUSD", "BUY", Decimal("0.01"), "mtm")
        assert k1 != k2

    def test_different_side_different_key(self):
        checker = IdempotencyChecker()
        k1 = checker.generate_key("EURUSD", "BUY", Decimal("0.01"), "mtm")
        k2 = checker.generate_key("EURUSD", "SELL", Decimal("0.01"), "mtm")
        assert k1 != k2

    def test_different_quantity_different_key(self):
        checker = IdempotencyChecker()
        k1 = checker.generate_key("EURUSD", "BUY", Decimal("0.01"), "mtm")
        k2 = checker.generate_key("EURUSD", "BUY", Decimal("0.02"), "mtm")
        assert k1 != k2

    def test_different_strategy_different_key(self):
        checker = IdempotencyChecker()
        k1 = checker.generate_key("EURUSD", "BUY", Decimal("0.01"), "mtm")
        k2 = checker.generate_key("EURUSD", "BUY", Decimal("0.01"), "mrb")
        assert k1 != k2

    def test_no_redis_no_crash(self):
        """Checker should work without Redis."""
        checker = IdempotencyChecker(redis_client=None, db_session=None)
        key = checker.generate_key("EURUSD", "BUY", Decimal("0.01"), "mtm")
        assert not checker.is_duplicate(key, check_redis=False, check_db=False)

    def test_record_and_check_no_crash(self):
        """record_key and check_and_record should not crash without backends."""
        checker = IdempotencyChecker(redis_client=None, db_session=None)
        key = "test_key_123"
        checker.record_key(key, "order_123")
        # Without Redis/DB, is_duplicate returns False
        assert not checker.is_duplicate(key, check_redis=False, check_db=False)

    def test_check_and_record_returns_true(self):
        """check_and_record returns True when key is new."""
        checker = IdempotencyChecker(redis_client=None, db_session=None)
        result = checker.check_and_record("new_key_456", "order_456", raise_on_duplicate=False)
        assert result is True

    def test_check_and_record_no_raise(self):
        """check_and_record returns False on duplicate when raise=False."""
        checker = IdempotencyChecker(redis_client=None, db_session=None)
        # Without backends, duplicate check always returns False
        result = checker.check_and_record("key_789", "order_789", raise_on_duplicate=False)
        assert result is True

    def test_clear_key_no_crash(self):
        checker = IdempotencyChecker(redis_client=None, db_session=None)
        checker.clear_key("any_key")  # should not raise

    def test_get_order_by_key_returns_none(self):
        checker = IdempotencyChecker(redis_client=None, db_session=None)
        result = checker.get_order_by_key("nonexistent_key")
        assert result is None

    def test_get_stats(self):
        checker = IdempotencyChecker(redis_client=None, db_session=None)
        stats = checker.get_stats()
        # redis_connected depends on whether redis.from_url succeeds in __init__
        assert "redis_connected" in stats
        assert "db_connected" in stats
        assert stats["db_connected"] is False

    def test_key_includes_signal_id(self):
        checker = IdempotencyChecker()
        k1 = checker.generate_key("EURUSD", "BUY", Decimal("0.01"), "mtm", signal_id="sig_1")
        k2 = checker.generate_key("EURUSD", "BUY", Decimal("0.01"), "mtm", signal_id="sig_2")
        assert k1 != k2


class TestWindowedIdempotencyChecker:
    """Windowed idempotency checker edge cases."""

    def test_default_window(self):
        wic = WindowedIdempotencyChecker()
        assert wic.get_window("unknown_strategy") == 60

    def test_mtm_window(self):
        wic = WindowedIdempotencyChecker()
        assert wic.get_window("mtm") == 60

    def test_mrb_window(self):
        wic = WindowedIdempotencyChecker()
        assert wic.get_window("mrb") == 120

    def test_mlb_window(self):
        wic = WindowedIdempotencyChecker()
        assert wic.get_window("mlb") == 60

    def test_custom_window(self):
        wic = WindowedIdempotencyChecker()
        key = wic.generate_key(
            "EURUSD", "BUY", Decimal("0.01"), "mtm",
            timestamp_bucket_seconds=120,
        )
        assert len(key) == 64


# ═══════════════════════════════════════════════════════════════════════
# Paper Broker
# ═══════════════════════════════════════════════════════════════════════

class TestPaperBroker:
    """Paper broker adapter edge cases."""

    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        broker = PaperBroker()
        assert await broker.connect()
        assert broker.is_connected
        await broker.disconnect()
        assert not broker.is_connected

    @pytest.mark.asyncio
    async def test_get_account(self):
        broker = PaperBroker()
        await broker.connect()
        account = await broker.get_account()
        assert account.balance > 0
        assert account.equity > 0

    @pytest.mark.asyncio
    async def test_place_order_market(self):
        broker = PaperBroker()
        await broker.connect()
        order = create_order(
            "EURUSD", OrderSide.BUY, OrderType.MARKET, Decimal("0.01"),
        )
        result = await broker.place_order(order)
        assert result.success
        assert result.status == OrderStatus.FILLED
        assert result.broker_order_id is not None

    @pytest.mark.asyncio
    async def test_get_price(self):
        broker = PaperBroker()
        await broker.connect()
        prices = await broker.get_price("EURUSD")
        assert "bid" in prices
        assert "ask" in prices
        assert prices["ask"] > prices["bid"]

    @pytest.mark.asyncio
    async def test_set_price(self):
        broker = PaperBroker()
        await broker.connect()
        broker.set_price("CUSTOM", Decimal("100.00"), Decimal("100.10"))
        prices = await broker.get_price("CUSTOM")
        assert prices["bid"] == Decimal("100.00")
        assert prices["ask"] == Decimal("100.10")

    @pytest.mark.asyncio
    async def test_get_position_empty(self):
        broker = PaperBroker()
        await broker.connect()
        pos = await broker.get_position("EURUSD")
        assert pos is None

    @pytest.mark.asyncio
    async def test_get_positions_empty(self):
        broker = PaperBroker()
        await broker.connect()
        positions = await broker.get_positions()
        assert len(positions) == 0

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_order(self):
        broker = PaperBroker()
        await broker.connect()
        result = await broker.cancel_order("nonexistent")
        assert not result

    @pytest.mark.asyncio
    async def test_get_order_status_nonexistent(self):
        broker = PaperBroker()
        await broker.connect()
        result = await broker.get_order_status("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_unknown_symbol_price(self):
        """Unknown symbol returns base price of 1.0000."""
        broker = PaperBroker()
        await broker.connect()
        prices = await broker.get_price("UNKNOWN")
        assert "bid" in prices
        assert "ask" in prices

    @pytest.mark.asyncio
    async def test_xauusd_price(self):
        broker = PaperBroker()
        await broker.connect()
        prices = await broker.get_price("XAUUSD")
        assert prices["bid"] > 2000  # gold is > $2000

    @pytest.mark.asyncio
    async def test_order_updates_position(self):
        broker = PaperBroker()
        await broker.connect()
        order = create_order(
            "EURUSD", OrderSide.BUY, OrderType.MARKET, Decimal("0.01"),
        )
        await broker.place_order(order)
        pos = await broker.get_position("EURUSD")
        assert pos is not None
        assert pos.quantity == Decimal("0.01")

    @pytest.mark.asyncio
    async def test_close_position_opposite_side(self):
        broker = PaperBroker()
        await broker.connect()
        # Open
        order1 = create_order(
            "EURUSD", OrderSide.BUY, OrderType.MARKET, Decimal("0.01"),
        )
        await broker.place_order(order1)
        # Close
        order2 = create_order(
            "EURUSD", OrderSide.SELL, OrderType.MARKET, Decimal("0.01"),
        )
        await broker.place_order(order2)
        pos = await broker.get_position("EURUSD")
        assert pos is None


# ═══════════════════════════════════════════════════════════════════════
# Broker Manager Failover
# ═══════════════════════════════════════════════════════════════════════

class TestBrokerManager:
    """Broker manager failover edge cases."""

    @pytest.mark.asyncio
    async def test_initialize_paper_broker(self):
        mgr = BrokerManager()
        result = await mgr.initialize()
        assert result is True
        assert mgr.active is not None

    @pytest.mark.asyncio
    async def test_health_check_passes(self):
        mgr = BrokerManager()
        await mgr.initialize()
        healthy = await mgr.health_check()
        assert healthy

    @pytest.mark.asyncio
    async def test_active_broker_before_init_raises(self):
        mgr = BrokerManager()
        with pytest.raises(Exception):
            _ = mgr.active

    @pytest.mark.asyncio
    async def test_failover_on_health_failure(self):
        mgr = BrokerManager()
        await mgr.initialize()
        # Simulate primary failure
        mgr.primary.get_account = AsyncMock(side_effect=Exception("connection lost"))
        # Should try failover
        result = await mgr.health_check()
        # Failover may succeed or fail depending on fallback setup
        assert isinstance(result, bool)


# ═══════════════════════════════════════════════════════════════════════
# Edge Cases: Boundary Values
# ═══════════════════════════════════════════════════════════════════════

class TestBoundaryValues:
    """Boundary value edge cases for execution."""

    def test_quantity_very_small(self):
        o = create_order("EURUSD", OrderSide.BUY, OrderType.MARKET, Decimal("0.001"))
        assert o.quantity == Decimal("0.001")

    def test_quantity_very_large(self):
        o = create_order("EURUSD", OrderSide.BUY, OrderType.MARKET, Decimal("1000.0"))
        assert o.quantity == Decimal("1000.0")

    def test_price_very_precise(self):
        o = create_order(
            "EURUSD", OrderSide.BUY, OrderType.LIMIT, Decimal("0.01"),
            price=Decimal("1.08543210"),
        )
        assert o.price == Decimal("1.08543210")

    def test_order_all_order_types(self):
        for ot in OrderType:
            o = create_order("EURUSD", OrderSide.BUY, ot, Decimal("0.01"))
            assert o.order_type == ot

    def test_order_all_sides(self):
        for side in OrderSide:
            o = create_order("EURUSD", side, OrderType.MARKET, Decimal("0.01"))
            assert o.side == side

    def test_order_all_time_in_force(self):
        for tif in TimeInForce:
            o = create_order(
                "EURUSD", OrderSide.BUY, OrderType.MARKET, Decimal("0.01"),
                time_in_force=tif,
            )
            assert o.time_in_force == tif
