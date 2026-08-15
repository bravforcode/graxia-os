"""
Regression coverage for execution/manager.py::OrderManager._submit_to_broker's
missing-stop-loss guard.

Flagged in LIVE_TRADING_READINESS_VERIFIED_20260725.md (Category B item #3)
as "STILL OPEN ... manager.py:310-312 hard-blocks and raises on missing
stop_price; no retry path; no test." This file adds the missing test
coverage that locks down the existing fail-closed behavior (Golden Rule:
every trade must have a stop-loss).

Deliberately does NOT add a "retry with a synthesized stop-loss" mechanism.
Inventing a fallback stop-loss without a defined policy (ATR multiple?
fixed %? something else?) would attach an arbitrary, possibly-wrong-for-
current-volatility SL just to avoid a rejection -- that would be a new
safety risk, not a fix. If a real fallback-SL policy is defined elsewhere,
retry logic belongs on top of that policy, not invented here.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from graxia.packages.quant_os.core.enums import OrderSide
from graxia.packages.quant_os.core.exceptions import RiskViolationError
from graxia.packages.quant_os.execution.manager import OrderManager
from graxia.packages.quant_os.execution.order import Order, OrderStateMachine


def _bare_manager():
    """OrderManager with mocked dependencies.

    The stop-loss guard in _submit_to_broker raises before touching any
    dependency fields, so Mock objects are safe for initialization.
    """
    mocks = patch.multiple(
        "graxia.packages.quant_os.execution.manager",
        IdempotencyChecker=MagicMock(),
        get_config=MagicMock(return_value=MagicMock()),
    )
    with mocks:
        return OrderManager(
            db_session=MagicMock(),
            broker_manager=MagicMock(),
        )


def _order(stop_price) -> Order:
    return Order(symbol="XAUUSD", side=OrderSide.BUY, quantity=Decimal("0.1"), stop_price=stop_price)


class TestSubmitToBrokerStopLossGuard:
    """Every submission path must fail closed when stop_price is missing,
    zero, or negative -- never silently submit an unprotected order."""

    def test_missing_stop_price_raises_before_broker_contact(self):
        order = _order(None)
        sm = OrderStateMachine(order)
        manager = _bare_manager()

        with pytest.raises(RiskViolationError) as exc_info:
            asyncio.run(manager._submit_to_broker(order, sm))

        assert exc_info.value.violation_type == "MISSING_STOP_LOSS"
        # State machine must not have advanced -- order was never sent.
        assert order.status.value != "SENT_TO_BROKER"

    def test_zero_stop_price_raises_before_broker_contact(self):
        order = _order(Decimal("0"))
        sm = OrderStateMachine(order)
        manager = _bare_manager()

        with pytest.raises(RiskViolationError) as exc_info:
            asyncio.run(manager._submit_to_broker(order, sm))

        assert exc_info.value.violation_type == "MISSING_STOP_LOSS"

    def test_negative_stop_price_raises_before_broker_contact(self):
        order = _order(Decimal("-5"))
        sm = OrderStateMachine(order)
        manager = _bare_manager()

        with pytest.raises(RiskViolationError) as exc_info:
            asyncio.run(manager._submit_to_broker(order, sm))

        assert exc_info.value.violation_type == "MISSING_STOP_LOSS"
