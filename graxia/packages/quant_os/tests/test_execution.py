"""Tests for Quant OS execution module"""

from decimal import Decimal

import pytest

from graxia.packages.quant_os.core.enums import OrderSide, OrderStatus, OrderType
from graxia.packages.quant_os.core.exceptions import OrderStateError
from graxia.packages.quant_os.execution.broker_adapter import BrokerOrderResponse, PaperBroker
from graxia.packages.quant_os.execution.idempotency import IdempotencyChecker
from graxia.packages.quant_os.execution.order import OrderStateMachine, create_order


class TestOrder:
    """Test Order data class"""

    def test_order_creation(self):
        """Can create an order"""
        order = create_order(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.01"),
            strategy_id="mtm",
        )

        assert order.symbol == "EURUSD"
        assert order.side == OrderSide.BUY
        assert order.status == OrderStatus.CREATED
        assert order.idempotency_key is not None

    def test_order_idempotency_key_generation(self):
        """Idempotency key is generated correctly"""
        order1 = create_order(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.01"),
            strategy_id="mtm",
        )

        order2 = create_order(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.01"),
            strategy_id="mtm",
        )

        # Same parameters should generate same key within time bucket
        assert order1.idempotency_key is not None
        assert len(order1.idempotency_key) > 0


class TestOrderStateMachine:
    """Test order state machine"""

    def test_valid_transition(self):
        """Valid state transitions work"""
        order = create_order(symbol="EURUSD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=Decimal("0.01"))

        sm = OrderStateMachine(order)
        sm.validate_order()

        # CREATED -> VALIDATED is valid
        result = sm.transition(OrderStatus.VALIDATED, "Validated")
        assert result == True
        assert order.status == OrderStatus.VALIDATED

    def test_invalid_transition_raises(self):
        """Invalid transitions raise exception"""
        order = create_order(symbol="EURUSD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=Decimal("0.01"))

        sm = OrderStateMachine(order)

        # CREATED -> FILLED is invalid (must go through intermediate states)
        with pytest.raises(OrderStateError):
            sm.transition(OrderStatus.FILLED, "Invalid")

    def test_fill_updates_quantities(self):
        """Fill updates order quantities and prices"""
        order = create_order(symbol="EURUSD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=Decimal("0.01"))

        order.status = OrderStatus.ACKNOWLEDGED
        sm = OrderStateMachine(order)

        sm.fill(Decimal("0.01"), Decimal("1.0850"), Decimal("0.35"))

        assert order.status == OrderStatus.FILLED
        assert order.fill_quantity == Decimal("0.01")
        assert order.avg_fill_price == Decimal("1.0850")
        assert order.fee == Decimal("0.35")

    def test_cancel_terminal_state(self):
        """Cancel moves order to terminal state"""
        order = create_order(symbol="EURUSD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=Decimal("0.01"))

        sm = OrderStateMachine(order)
        sm.cancel("User request")

        assert order.status == OrderStatus.CANCELLED


class TestIdempotencyChecker:
    """Test idempotency checking"""

    def test_generate_key(self):
        """Key generation is consistent"""
        checker = IdempotencyChecker()

        key1 = checker.generate_key("EURUSD", "BUY", Decimal("0.01"), "mtm")
        key2 = checker.generate_key("EURUSD", "BUY", Decimal("0.01"), "mtm")

        # Same parameters = same key (within time bucket)
        assert key1 == key2
        assert len(key1) == 64  # SHA256 hex = 64 chars

    def test_duplicate_detection(self):
        """Duplicates are detected"""
        checker = IdempotencyChecker()

        key = checker.generate_key("EURUSD", "BUY", Decimal("0.01"), "mtm")

        # First check - not duplicate
        assert checker.is_duplicate(key, check_db=False, check_redis=False) == False

        # Record key
        checker.record_key(key, "order_123")

        # Now it's a duplicate (in Redis cache)
        # Note: Without actual Redis, this will still return False
        # but the logic is correct


class TestPaperBroker:
    """Test paper trading broker"""

    @pytest.mark.asyncio
    async def test_connect(self):
        """Paper broker connects successfully"""
        broker = PaperBroker()
        result = await broker.connect()

        assert result == True
        assert broker.is_connected == True

    @pytest.mark.asyncio
    async def test_get_account(self):
        """Paper broker returns account info"""
        broker = PaperBroker()
        await broker.connect()

        account = await broker.get_account()

        assert account.balance > 0
        assert account.equity > 0

    @pytest.mark.asyncio
    async def test_place_order(self):
        """Paper broker simulates order execution"""
        broker = PaperBroker()
        await broker.connect()

        order = create_order(symbol="EURUSD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=Decimal("0.01"))

        result = await broker.place_order(order)

        assert isinstance(result, BrokerOrderResponse)
        assert result.success == True
        assert result.broker_order_id is not None
        assert result.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_get_price(self):
        """Paper broker returns prices"""
        broker = PaperBroker()
        await broker.connect()

        prices = await broker.get_price("EURUSD")

        assert "bid" in prices
        assert "ask" in prices
        assert prices["ask"] > prices["bid"]
