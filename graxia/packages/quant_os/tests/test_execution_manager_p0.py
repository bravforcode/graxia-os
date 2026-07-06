"""Regression tests for two P0/P1 bugs in execution/manager.py:

BUG-001 (P0, safety-critical): ``_submit_to_broker`` used to call an
undefined ``logger`` right before raising ``RiskViolationError`` for an
order with no stop-loss, so the safety rejection crashed with
``NameError`` instead of cleanly raising ``RiskViolationError``.

BUG-002 (P1): the MICRO-mode expiry timer was scheduled with
``asyncio.create_task(...)`` and the task object was never referenced,
so it could be silently garbage-collected and any exception raised
inside it would be lost. ``OrderManager`` now keeps a strong reference
in ``self._background_tasks`` and attaches a done-callback
(``_on_expiry_task_done``) that logs any exception.
"""

from decimal import Decimal

import pytest

from graxia.packages.quant_os.core.enums import OrderSide, OrderType
from graxia.packages.quant_os.core.exceptions import RiskViolationError
from graxia.packages.quant_os.execution.manager import OrderManager
from graxia.packages.quant_os.execution.order import OrderStateMachine, create_order


def _manager_without_init() -> OrderManager:
    """Build an OrderManager without running __init__.

    ``_submit_to_broker`` and ``_on_expiry_task_done`` only touch
    ``self._background_tasks`` / raise before touching the broker, db, or
    config, so a full constructor (which needs a real db session and
    broker manager) isn't needed for these two regression tests.
    """
    manager = OrderManager.__new__(OrderManager)
    manager._background_tasks = set()
    return manager


class TestMissingStopLossRejection:
    """BUG-001: missing stop-loss must raise RiskViolationError, not NameError."""

    async def test_submit_to_broker_raises_risk_violation_not_name_error(self):
        manager = _manager_without_init()
        order = create_order(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1000"),
            stop_price=None,
        )
        state_machine = OrderStateMachine(order)

        with pytest.raises(RiskViolationError) as exc_info:
            await manager._submit_to_broker(order, state_machine)

        assert exc_info.value.violation_type == "MISSING_STOP_LOSS"

    async def test_submit_to_broker_raises_risk_violation_for_non_positive_stop(self):
        manager = _manager_without_init()
        order = create_order(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1000"),
            stop_price=Decimal("0"),
        )
        state_machine = OrderStateMachine(order)

        with pytest.raises(RiskViolationError):
            await manager._submit_to_broker(order, state_machine)

    def test_logger_module_attribute_exists(self):
        """Guards directly against the NameError regression: manager.logger must exist."""
        from graxia.packages.quant_os.execution import manager as manager_module

        assert hasattr(manager_module, "logger")


class TestExpiryTaskDoneCallback:
    """BUG-002: exceptions from the fire-and-forget expiry task must surface, not vanish."""

    def test_done_callback_logs_exception_and_drops_reference(self, caplog):
        manager = _manager_without_init()

        class _FakeTask:
            def __init__(self, exc: Exception):
                self._exc = exc

            def cancelled(self):
                return False

            def exception(self):
                return self._exc

        boom = RuntimeError("db exploded during expiry")
        fake_task = _FakeTask(boom)
        manager._background_tasks.add(fake_task)

        with caplog.at_level("ERROR", logger="graxia.packages.quant_os.execution.manager"):
            manager._on_expiry_task_done(fake_task)

        assert fake_task not in manager._background_tasks
        assert any("db exploded during expiry" in record.getMessage() for record in caplog.records)

    def test_done_callback_ignores_cancelled_task(self, caplog):
        manager = _manager_without_init()

        class _CancelledTask:
            def cancelled(self):
                return True

            def exception(self):  # pragma: no cover - must not be called
                raise AssertionError("exception() should not be called on a cancelled task")

        cancelled_task = _CancelledTask()
        manager._background_tasks.add(cancelled_task)

        with caplog.at_level("ERROR", logger="graxia.packages.quant_os.execution.manager"):
            manager._on_expiry_task_done(cancelled_task)

        assert cancelled_task not in manager._background_tasks
        assert not caplog.records

    async def test_real_asyncio_task_exception_reaches_done_callback(self, caplog):
        """End-to-end sanity check with a real asyncio.Task (not just a fake)."""
        import asyncio

        manager = _manager_without_init()

        async def _boom():
            raise RuntimeError("real task failure")

        task = asyncio.create_task(_boom())
        manager._background_tasks.add(task)
        task.add_done_callback(manager._on_expiry_task_done)

        with caplog.at_level("ERROR", logger="graxia.packages.quant_os.execution.manager"):
            # Let the task run to completion and its done-callback fire —
            # don't `await task` directly, that would just re-raise here.
            for _ in range(10):
                if task.done():
                    break
                await asyncio.sleep(0)
            # A task's done-callbacks are scheduled (not run) the instant it
            # completes, so give the loop a couple more turns to run them.
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        assert task.done()
        assert task not in manager._background_tasks
        assert any("real task failure" in record.getMessage() for record in caplog.records)
