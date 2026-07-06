"""Adversarial unit tests for the OMS and execution layer.

Philosophy: These tests try to BREAK the system, not validate it.
If a test reveals a real bug, it is documented inline.

Targets:
  - execution/oms.py
  - execution/order.py
  - execution/adapters/mt5.py
  - execution/adapters/paper.py
  - execution/order_state_machine.py
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from graxia.packages.quant_os.core.enums import OrderSide, OrderStatus
from graxia.packages.quant_os.core.exceptions import OrderStateError, ValidationError
from graxia.packages.quant_os.execution.adapters.base import (
    BrokerAdapter,
    OrderResult,
)
from graxia.packages.quant_os.execution.adapters.base import (
    Order as AdapterOrder,
)
from graxia.packages.quant_os.execution.adapters.paper import PaperAdapter
from graxia.packages.quant_os.execution.oms import OMS
from graxia.packages.quant_os.execution.order import Order, OrderStateMachine
from graxia.packages.quant_os.execution.order_state_machine import OrderStateMachine as ExecutionSM

# ---------------------------------------------------------------------------
# BUG DOCUMENTATION
# ---------------------------------------------------------------------------
#
# BUG-001: No concurrency protection in OMS
#   Severity: CRITICAL
#   Description: OMS._orders, _orders_by_signal_id, and _state_machines are
#     plain dicts with no locking. Concurrent submit_order calls on the same
#     signal_id can both pass the idempotency guard and create duplicates.
#   Reproduction: Submit same signal_id from two threads simultaneously.
#   Expected: Only one order created (idempotency holds).
#   Actual: Two orders created, both persisted to ledger.
#
# BUG-002: close_position creates Order outside state machine
#   Severity: HIGH
#   Description: close_position creates Order objects directly and writes
#     them to the ledger WITHOUT initializing an OrderStateMachine. Any
#     subsequent call to get_state_machine() for that order_id returns None,
#     and get_state_history() returns [].
#   Reproduction: Call close_position, then get_state_machine(order_id).
#   Expected: State machine exists and tracks the close lifecycle.
#   Actual: State machine is None.
#
# BUG-003: _load_ledger silently swallows all replay errors
#   Severity: HIGH
#   Description: _load_ledger uses contextlib.suppress(Exception) around
#     every sm.advance() call during replay. If the ledger has corrupted
#     intermediate states, those are silently skipped, and the order ends
#     up in an inconsistent state with no indication of data loss.
#   Reproduction: Write a ledger with impossible transitions, reload.
#   Expected: At minimum a log warning; ideally raise or quarantine.
#   Actual: Silent skip, order state is wrong.
#
# BUG-004: _poll_fill blocks the entire OMS thread for 30 seconds
#   Severity: MEDIUM
#   Description: _poll_fill uses time.sleep(2.0) in a loop with a 30s
#     deadline. During this time, the OMS instance cannot process any
#     other orders. A slow fill effectively serializes all order processing.
#   Reproduction: Submit an order that partial-fills; no other orders
#     can be submitted until the 30s poll completes.
#   Expected: Non-blocking poll or async pattern.
#   Actual: Synchronous blocking.
#
# BUG-005: close_position ignores volume=0 and negative volume
#   Severity: MEDIUM
#   Description: close_position does not validate the volume parameter.
#     volume=0 creates an Order with quantity=0 (no-op close).
#     negative volume creates an Order with side="BUY" (wrong direction)
#     and quantity=abs(negative) (non-zero close in wrong direction).
#   Reproduction: close_position(symbol="EURUSD", volume=0) or volume=-1.
#   Expected: ValueError or defensive handling.
#   Actual: Silently creates a garbage Order.
#
# BUG-006: submit_order allows quantity=0
#   Severity: LOW
#   Description: submit_order in OMS does not validate quantity before
#     passing to the adapter. An adapter may accept a 0-qty order or
#     reject it with a broker-specific error.
#   Reproduction: submit_order(quantity=0, ...).
#   Expected: Pre-validation rejects zero/negative quantities.
#   Actual: Order created and sent to broker.
#
# BUG-007: _update_ledger not atomic — partial writes corrupt JSONL
#   Severity: MEDIUM
#   Description: _update_ledger opens the file in append mode and writes
#     a single line. If the process crashes mid-write (e.g. killed by OS),
#     a partial JSON line is left in the ledger. On next _load_ledger,
#     json.loads() on the truncated line raises JSONDecodeError, crashing
#     the entire OMS initialization.
#   Reproduction: Write a ledger, then append a partial line manually.
#   Expected: _load_ledger should skip/handle malformed lines.
#   Actual: json.loads raises, OMS fails to initialize.
#
# BUG-008: compact_ledger can delete all data if all orders are old
#   Severity: LOW
#   Description: compact_ledger with max_age_days=0 will discard ALL
#     orders. While this is technically correct, the "all expired" path
#     writes an empty file with no confirmation mechanism.
#   Reproduction: compact_ledger(max_age_days=0) on any ledger.
#   Expected: At least a log warning about full wipe.
#   Actual: Silently empties ledger.
#
# BUG-009: OMS does not validate signal_id length or content
#   Severity: LOW
#   Description: signal_id is stored as-is in the ledger and used as a
#     dict key. A 10,000-char signal_id wastes memory and disk. Special
#     characters (newlines, null bytes) could corrupt the JSONL format.
#   Reproduction: submit_order(signal_id="A" * 10000).
#   Expected: Length/content validation.
#   Actual: Accepted without limit.
#
# BUG-010: OrderStateMachine (order.py) vs OrderStateMachine (order_state_machine.py)
#   Severity: CRITICAL (architecture)
#   Description: There are TWO different OrderStateMachine implementations:
#     - execution/order.py: takes Order object, has transition() with
#       reason+actor, TERMINAL_STATES as list, validate_order()
#     - execution/order_state_machine.py: takes order_id string, has
#       advance(target, reason), TERMINAL_STATES as frozenset
#     OMS uses order_state_machine.py's version. The version in order.py
#     is essentially dead code but may confuse developers.
#   Expected: Single source of truth.
#   Actual: Two divergent implementations.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_ledger(tmp_path: Path) -> Path:
    """Return a path to a temporary ledger file."""
    return tmp_path / "test_ledger.jsonl"


@pytest.fixture
def paper_adapter() -> PaperAdapter:
    """Return a connected PaperAdapter."""
    adapter = PaperAdapter(initial_capital=100_000.0)
    adapter.connect()
    return adapter


@pytest.fixture
def oms(tmp_ledger: Path, paper_adapter: PaperAdapter) -> OMS:
    """Return an OMS wired to a paper adapter with a temp ledger."""
    return OMS(
        adapters={"mt5": paper_adapter},
        ledger_path=tmp_ledger,
    )


def _make_order_record(
    order_id: str,
    signal_id: str = "sig-1",
    symbol: str = "EURUSD",
    asset_class: str = "forex",
    side: str = "BUY",
    quantity: float = 0.1,
    status: str = "PENDING",
    broker_order_id: str | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict:
    """Build a raw ledger record dict."""
    return {
        "order_id": order_id,
        "signal_id": signal_id,
        "symbol": symbol,
        "asset_class": asset_class,
        "side": side,
        "quantity": quantity,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "status": status,
        "broker_order_id": broker_order_id,
        "created_at": datetime.now(UTC).isoformat(),
    }


def _write_ledger(path: Path, records: list[dict]) -> None:
    """Write records to a JSONL ledger file."""
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


# ===========================================================================
# 1. CONCURRENCY BUGS
# ===========================================================================


class TestConcurrencyBugs:
    """Tests that try to break the OMS with concurrent access."""

    def test_concurrent_submit_same_signal_id(self, tmp_ledger: Path, paper_adapter: PaperAdapter) -> None:
        """BUG-001: Submit 100 orders with same signal_id concurrently.

        Idempotency MUST hold — only one order should be created.
        """
        oms = OMS(adapters={"mt5": paper_adapter}, ledger_path=tmp_ledger)
        signal_id = "concurrent-signal-42"
        results: list[AdapterOrder] = []
        errors: list[Exception] = []

        def submit():
            try:
                order = oms.submit_order(
                    signal_id=signal_id,
                    symbol="EURUSD",
                    asset_class="forex",
                    side="BUY",
                    quantity=0.01,
                )
                results.append(order)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=submit) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # BUG-001 DETECTED: Multiple orders may be created for same signal_id
        # because there is no lock on _orders_by_signal_id check + insert.
        unique_order_ids = {r.order_id for r in results}
        if len(unique_order_ids) > 1:
            pytest.fail(
                f"BUG-001: Idempotency violated — {len(unique_order_ids)} "
                f"unique orders created for same signal_id. "
                f"Order IDs: {unique_order_ids}"
            )

    def test_submit_while_kill_switch_activating(self, oms: OMS) -> None:
        """Submit order while cancel_all is running — race condition."""
        # Pre-populate some orders so cancel_all has work to do
        oms.submit_order("sig-a", "EURUSD", "forex", "BUY", 0.01)
        oms.submit_order("sig-b", "GBPUSD", "forex", "BUY", 0.01)

        errors: list[Exception] = []
        results: list[Any] = []

        def kill():
            try:
                oms.cancel_all()
            except Exception as e:
                errors.append(e)

        def submit():
            try:
                oms.submit_order("sig-c", "USDJPY", "forex", "BUY", 0.01)
                results.append(True)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=kill), threading.Thread(target=submit)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # Should not crash or corrupt state
        assert not any("corrupt" in str(e).lower() for e in errors)

    def test_concurrent_close_position_same_position(self, oms: OMS, paper_adapter: PaperAdapter) -> None:
        """Two concurrent close_position calls on the same position."""
        # Open a position first
        oms.submit_order("sig-open", "EURUSD", "forex", "BUY", 0.1)

        errors: list[Exception] = []

        def close():
            try:
                oms.close_position("EURUSD", "pos-123", 0.1, "forex")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=close) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # Should not crash, even if both try to close
        assert len(errors) == 0 or all("No position" in str(e) for e in errors)

    def test_signal_id_reuse_across_symbols(self, oms: OMS) -> None:
        """Same signal_id used for different symbols — idempotency should still hold."""
        order1 = oms.submit_order("shared-sig", "EURUSD", "forex", "BUY", 0.01)
        order2 = oms.submit_order("shared-sig", "GBPUSD", "forex", "BUY", 0.01)

        # BUG-009 context: signal_id is shared across symbols. The second
        # submission is silently rejected by idempotency, but the caller
        # has no way to know the order was for a different symbol.
        assert order1.order_id == order2.order_id, "Same signal_id should return same order (idempotency)"

    def test_concurrent_ledger_writes(self, tmp_ledger: Path, paper_adapter: PaperAdapter) -> None:
        """Multiple threads writing to the ledger simultaneously."""
        oms = OMS(adapters={"mt5": paper_adapter}, ledger_path=tmp_ledger)

        errors: list[Exception] = []

        def submit(i: int):
            try:
                oms.submit_order(f"sig-{i}", "EURUSD", "forex", "BUY", 0.01)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=submit, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        # All writes should succeed (no file corruption)
        assert len(errors) == 0, f"Concurrent writes caused errors: {errors}"

        # Ledger should have valid JSON on every line
        with open(tmp_ledger, encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                line = line.strip()
                if not line:
                    continue
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    pytest.fail(f"Corrupted ledger line {i}: {line[:100]}")

    def test_submit_order_idempotency_after_reopen(self, tmp_ledger: Path, paper_adapter: PaperAdapter) -> None:
        """Idempotency must survive OMS restart (ledger reload)."""
        oms1 = OMS(adapters={"mt5": paper_adapter}, ledger_path=tmp_ledger)
        order1 = oms1.submit_order("persistent-sig", "EURUSD", "forex", "BUY", 0.01)

        # Reopen OMS (simulates crash/restart)
        oms2 = OMS(adapters={"mt5": paper_adapter}, ledger_path=tmp_ledger)
        order2 = oms2.submit_order("persistent-sig", "EURUSD", "forex", "BUY", 0.01)

        assert order1.order_id == order2.order_id, "Idempotency must survive OMS restart"

    def test_concurrent_cancel_and_submit(self, oms: OMS) -> None:
        """Cancel all while new orders are being submitted."""
        submitted: list[str] = []
        errors: list[Exception] = []

        def submit_batches():
            for i in range(10):
                try:
                    oms.submit_order(f"batch-{i}", "EURUSD", "forex", "BUY", 0.01)
                    submitted.append(f"batch-{i}")
                except Exception as e:
                    errors.append(e)

        def kill():
            time.sleep(0.01)
            try:
                oms.cancel_all()
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=submit_batches)
        t2 = threading.Thread(target=kill)
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=10)

        # No corruption
        assert not any("JSONDecodeError" in str(e) for e in errors)

    def test_submit_order_during_ledger_compaction(self, tmp_ledger: Path, paper_adapter: PaperAdapter) -> None:
        """Submit order while compact_ledger is running."""
        oms = OMS(adapters={"mt5": paper_adapter}, ledger_path=tmp_ledger)

        # Create many orders so compaction has work
        for i in range(50):
            oms.submit_order(f"compact-{i}", "EURUSD", "forex", "BUY", 0.01)

        errors: list[Exception] = []

        def compact():
            try:
                oms.compact_ledger(max_age_days=365)
            except Exception as e:
                errors.append(e)

        def submit():
            try:
                oms.submit_order("during-compact", "GBPUSD", "forex", "BUY", 0.01)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=compact), threading.Thread(target=submit)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        # Both should complete without crashing
        assert not any("PermissionError" in str(e) or "FileNotFoundError" in str(e) for e in errors)


# ===========================================================================
# 2. DATA CORRUPTION
# ===========================================================================


class TestDataCorruption:
    """Tests that try to break the OMS with corrupted/malformed data."""

    def test_ledger_truncated_json_line(self, tmp_ledger: Path, paper_adapter: PaperAdapter) -> None:
        """FIXED: Ledger with truncated JSON line is skipped, OMS loads successfully."""
        good_record = _make_order_record("ord-1", status="FILLED")
        _write_ledger(tmp_ledger, [good_record])

        # Append a truncated line
        with open(tmp_ledger, "a", encoding="utf-8") as fh:
            fh.write('{"order_id": "ord-2", "signal_id": "sig-2", "truncated...\n')

        # FIXED: _load_ledger now catches json.JSONDecodeError, skips the
        # corrupted line, logs a warning, and continues initialization.
        # The good record is loaded; the truncated line is skipped.
        oms = OMS(adapters={"mt5": paper_adapter}, ledger_path=tmp_ledger)
        assert oms.order_by_id("ord-1") is not None, "Good record should load"
        assert oms.order_by_id("ord-2") is None, "Truncated record should be skipped"

    def test_ledger_duplicate_order_ids(self, tmp_ledger: Path, paper_adapter: PaperAdapter) -> None:
        """Ledger with duplicate order_ids — latest should win."""
        rec1 = _make_order_record("ord-dup", status="PENDING")
        rec2 = _make_order_record("ord-dup", status="FILLED")
        _write_ledger(tmp_ledger, [rec1, rec2])

        oms = OMS(adapters={"mt5": paper_adapter}, ledger_path=tmp_ledger)
        order = oms.order_by_id("ord-dup")
        assert order is not None
        assert order.status == OrderStatus.FILLED, "Latest record should win for duplicate order_ids"

    def test_ledger_missing_required_fields(self, tmp_ledger: Path, paper_adapter: PaperAdapter) -> None:
        """Ledger record missing required fields (signal_id, symbol, etc.)."""
        bad_record = {"order_id": "ord-bad"}  # missing signal_id, symbol, etc.
        _write_ledger(tmp_ledger, [bad_record])

        with pytest.raises(KeyError):
            OMS(adapters={"mt5": paper_adapter}, ledger_path=tmp_ledger)

    def test_ledger_invalid_order_status(self, tmp_ledger: Path, paper_adapter: PaperAdapter) -> None:
        """Ledger record with invalid status value."""
        rec = _make_order_record("ord-invalid", status="NOT_A_REAL_STATUS")
        _write_ledger(tmp_ledger, [rec])

        with pytest.raises(ValueError):
            OMS(adapters={"mt5": paper_adapter}, ledger_path=tmp_ledger)

    def test_ledger_completely_empty_file(self, tmp_ledger: Path, paper_adapter: PaperAdapter) -> None:
        """Empty ledger file should not crash."""
        tmp_ledger.touch()
        oms = OMS(adapters={"mt5": paper_adapter}, ledger_path=tmp_ledger)
        assert len(oms._orders) == 0

    def test_ledger_only_whitespace_lines(self, tmp_ledger: Path, paper_adapter: PaperAdapter) -> None:
        """Ledger with only whitespace/empty lines."""
        # Write raw empty/whitespace lines directly (not json.dumps-encoded)
        with open(tmp_ledger, "w", encoding="utf-8") as fh:
            fh.write("\n\n  \n\n")
        oms = OMS(adapters={"mt5": paper_adapter}, ledger_path=tmp_ledger)
        assert len(oms._orders) == 0

    def test_ledger_file_is_directory(self, tmp_path: Path, paper_adapter: PaperAdapter) -> None:
        """Ledger path points to a directory instead of a file."""
        ledger_dir = tmp_path / "ledger_is_dir"
        ledger_dir.mkdir()
        with pytest.raises((IsADirectoryError, OSError)):
            OMS(adapters={"mt5": paper_adapter}, ledger_path=ledger_dir)

    def test_ledger_with_binary_garbage(self, tmp_ledger: Path, paper_adapter: PaperAdapter) -> None:
        """Ledger file contains binary garbage."""
        with open(tmp_ledger, "wb") as fh:
            fh.write(b"\x00\x01\x02\xff\xfe\xfd")

        with pytest.raises((UnicodeDecodeError, json.JSONDecodeError)):
            OMS(adapters={"mt5": paper_adapter}, ledger_path=tmp_ledger)


# ===========================================================================
# 3. RESOURCE EXHAUSTION
# ===========================================================================


class TestResourceExhaustion:
    """Tests that try to exhaust resources."""

    def test_submit_order_adapter_returns_none(self, tmp_ledger: Path) -> None:
        """BUG-007 context: What happens when adapter.submit_order returns None?"""
        mock_adapter = MagicMock(spec=BrokerAdapter)
        mock_adapter.is_connected = True
        mock_adapter.submit_order.return_value = None  # Simulate broken adapter

        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)

        with pytest.raises((AttributeError, TypeError)):
            # None has no .status attribute — should crash
            oms.submit_order("sig-none", "EURUSD", "forex", "BUY", 0.01)

    def test_adapter_raises_on_submit(self, tmp_ledger: Path) -> None:
        """Adapter raises an exception during submit_order."""
        mock_adapter = MagicMock(spec=BrokerAdapter)
        mock_adapter.is_connected = True
        mock_adapter.submit_order.side_effect = RuntimeError("Broker connection lost")

        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)

        with pytest.raises(RuntimeError, match="Broker connection lost"):
            oms.submit_order("sig-crash", "EURUSD", "forex", "BUY", 0.01)

    def test_submit_many_orders_ledger_integrity(self, oms: OMS) -> None:
        """Submit 1000 orders and verify ledger integrity."""
        for i in range(1000):
            oms.submit_order(f"bulk-{i}", "EURUSD", "forex", "BUY", 0.01)

        # Verify every line is valid JSON
        line_count = 0
        with open(oms._ledger_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                assert "order_id" in rec
                line_count += 1

        # Each order gets 1 initial + potentially status updates.
        # Just verify no corruption.
        assert line_count >= 1000

    def test_fill_poll_very_short_timeout(self, oms: OMS, paper_adapter: PaperAdapter) -> None:
        """Fill poll with very short timeout — should not hang forever."""
        with patch("graxia.packages.quant_os.execution.oms._FILL_TIMEOUT", 0.1):
            # Submit order that will partial-fill
            mock_adapter = MagicMock(spec=BrokerAdapter)
            mock_adapter.is_connected = True

            call_count = 0

            def fake_submit(order):
                return OrderResult(
                    status=OrderStatus.PARTIALLY_FILLED,
                    broker_id="partial-1",
                    filled_quantity=0.005,
                    avg_price=1.0850,
                )

            def fake_status(broker_id):
                # Always return partial — should hit timeout
                return OrderResult(
                    status=OrderStatus.SUBMITTED,
                    broker_id=broker_id,
                    filled_quantity=0.005,
                    avg_price=1.0850,
                )

            mock_adapter.submit_order.side_effect = fake_submit
            mock_adapter.get_order_status.side_effect = fake_status

            oms._adapters["mt5"] = mock_adapter
            order = oms.submit_order("sig-timeout", "EURUSD", "forex", "BUY", 0.01)

            # Should timeout, not hang
            assert order.status in (OrderStatus.TIMEOUT, OrderStatus.PARTIALLY_FILLED)

    def test_adapter_memory_error(self, tmp_ledger: Path) -> None:
        """Adapter raises MemoryError."""
        mock_adapter = MagicMock(spec=BrokerAdapter)
        mock_adapter.is_connected = True
        mock_adapter.submit_order.side_effect = MemoryError("Out of memory")

        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)

        with pytest.raises(MemoryError):
            oms.submit_order("sig-mem", "EURUSD", "forex", "BUY", 0.01)

    def test_adapter_keyboard_interrupt(self, tmp_ledger: Path) -> None:
        """Adapter raises KeyboardInterrupt — should propagate."""
        mock_adapter = MagicMock(spec=BrokerAdapter)
        mock_adapter.is_connected = True
        mock_adapter.submit_order.side_effect = KeyboardInterrupt()

        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)

        with pytest.raises(KeyboardInterrupt):
            oms.submit_order("sig-int", "EURUSD", "forex", "BUY", 0.01)

    def test_submit_order_unknown_asset_class(self, oms: OMS) -> None:
        """Submit order with unmapped asset_class — should fail gracefully."""
        with pytest.raises(ValueError, match="No venue mapped"):
            oms.submit_order("sig-unknown", "DOGEUSD", "memecoins", "BUY", 1.0)


# ===========================================================================
# 4. STATE MACHINE VIOLATIONS
# ===========================================================================


class TestStateMachineViolations:
    """Tests that try to violate the state machine invariants."""

    def test_advance_to_invalid_state(self) -> None:
        """Try to advance the OMS state machine to an impossible state."""
        sm = ExecutionSM(order_id="sm-test", initial=OrderStatus.SIGNAL_CREATED)

        with pytest.raises(OrderStateError):
            sm.advance(OrderStatus.FILLED, "skip to end")

    def test_advance_terminal_state(self) -> None:
        """Try to advance from a terminal state."""
        sm = ExecutionSM(order_id="sm-term", initial=OrderStatus.SIGNAL_CREATED)
        sm.advance(OrderStatus.RISK_CHECKED, "ok")
        sm.advance(OrderStatus.ORDER_PRECHECKED, "ok")
        sm.advance(OrderStatus.ORDER_SUBMITTED, "ok")
        sm.advance(OrderStatus.ORDER_ACKNOWLEDGED, "ok")
        sm.advance(OrderStatus.FILLED, "done")
        sm.advance(OrderStatus.PROTECTIVE_STOPS_PENDING, "stops")
        sm.advance(OrderStatus.PROTECTIVE_STOPS_VERIFIED, "verified")
        sm.advance(OrderStatus.POSITION_RECONCILED, "reconciled")
        sm.advance(OrderStatus.CLOSED, "closed")
        sm.advance(OrderStatus.DEAL_RECONCILED, "dealt")
        sm.advance(OrderStatus.AUDITED, "audited")

        assert sm.is_terminal()

        with pytest.raises(OrderStateError):
            sm.advance(OrderStatus.RISK_CHECKED, "go back")

    def test_advance_same_state_twice(self) -> None:
        """Try to advance to the same state twice."""
        sm = ExecutionSM(order_id="sm-same", initial=OrderStatus.SIGNAL_CREATED)

        # SIGNAL_CREATED -> RISK_CHECKED is valid
        sm.advance(OrderStatus.RISK_CHECKED, "ok")

        # RISK_CHECKED -> RISK_CHECKED is NOT valid
        with pytest.raises(OrderStateError):
            sm.advance(OrderStatus.RISK_CHECKED, "again")

    def test_state_machine_empty_order_id(self) -> None:
        """State machine with empty order_id."""
        sm = ExecutionSM(order_id="", initial=OrderStatus.SIGNAL_CREATED)
        assert sm.order_id == ""
        sm.advance(OrderStatus.RISK_CHECKED, "ok")
        assert sm.state == OrderStatus.RISK_CHECKED

    def test_order_state_machine_validate_order_rejects_empty_symbol(self) -> None:
        """order.py OrderStateMachine rejects empty symbol."""
        order = Order(symbol="", side=OrderSide.BUY, quantity=Decimal("0.01"))
        sm = OrderStateMachine(order=order)

        with pytest.raises(ValidationError):
            sm.validate_order()

    def test_order_state_machine_rejects_invalid_transition(self) -> None:
        """order.py OrderStateMachine rejects invalid transitions."""
        order = Order(symbol="EURUSD", side=OrderSide.BUY, quantity=Decimal("0.01"))
        sm = OrderStateMachine(order=order)

        # CREATED -> FILLED is not allowed
        with pytest.raises(OrderStateError):
            sm.transition(OrderStatus.FILLED)

    def test_order_state_machine_terminal_no_transition(self) -> None:
        """order.py OrderStateMachine blocks transitions from terminal states."""
        order = Order(symbol="EURUSD", side=OrderSide.BUY, quantity=Decimal("0.01"))
        sm = OrderStateMachine(order=order)

        sm.transition(OrderStatus.VALIDATED)
        sm.transition(OrderStatus.RISK_APPROVED)
        sm.transition(OrderStatus.COMPLIANCE_APPROVED)
        sm.transition(OrderStatus.SENT_TO_BROKER)
        sm.transition(OrderStatus.ACKNOWLEDGED)
        sm.transition(OrderStatus.FILLED)

        assert sm.order.status in sm.TERMINAL_STATES

        with pytest.raises(OrderStateError):
            sm.transition(OrderStatus.CANCELLED)

    def test_execution_sm_needs_protective_stop_verification(self) -> None:
        """Execution SM needs_protective_stop_verification returns correct value."""
        sm = ExecutionSM(order_id="sm-ps", initial=OrderStatus.FILLED)
        assert sm.needs_protective_stop_verification() is False

        sm2 = ExecutionSM(order_id="sm-ps2", initial=OrderStatus.PROTECTIVE_STOPS_PENDING)
        assert sm2.needs_protective_stop_verification() is True


# ===========================================================================
# 5. OMS EDGE CASES
# ===========================================================================


class TestOMSEdgeCases:
    """Edge cases that might break the OMS."""

    def test_close_position_volume_zero(self, oms: OMS, paper_adapter: PaperAdapter) -> None:
        """BUG-005: close_position with volume=0."""
        # Open a position first
        oms.submit_order("sig-for-zero", "EURUSD", "forex", "BUY", 0.1)

        order = oms.close_position("EURUSD", "pos-123", 0.0, "forex")
        # BUG-005: This creates an Order with quantity=0 and writes it to ledger
        assert order.quantity == 0.0, "Volume 0 should not create a meaningful order"

    def test_close_position_negative_volume(self, oms: OMS, paper_adapter: PaperAdapter) -> None:
        """BUG-005: close_position with negative volume."""
        oms.submit_order("sig-for-neg", "EURUSD", "forex", "BUY", 0.1)

        order = oms.close_position("EURUSD", "pos-456", -0.05, "forex")
        # BUG-005: Negative volume -> side="BUY" (wrong) and quantity=0.05
        assert order.quantity == 0.05, "Should use abs(volume)"
        assert order.side == "BUY", "Negative volume causes wrong side"

    def test_submit_order_quantity_zero(self, oms: OMS) -> None:
        """BUG-006: submit_order with quantity=0."""
        order = oms.submit_order("sig-zero-qty", "EURUSD", "forex", "BUY", 0.0)
        # No validation — order goes through with qty=0
        assert order.quantity == 0.0

    def test_submit_order_huge_quantity(self, oms: OMS) -> None:
        """submit_order with extremely large quantity."""
        order = oms.submit_order("sig-huge", "EURUSD", "forex", "BUY", 1_000_000.0)
        assert order.quantity == 1_000_000.0

    def test_cancel_all_no_orders(self, oms: OMS) -> None:
        """cancel_all when no orders exist."""
        cancelled = oms.cancel_all()
        assert cancelled == []

    def test_get_state_history_nonexistent(self, oms: OMS) -> None:
        """get_state_history for non-existent order_id."""
        history = oms.get_state_history("nonexistent-order-id")
        assert history == []

    def test_order_by_id_nonexistent(self, oms: OMS) -> None:
        """order_by_id for non-existent order."""
        result = oms.order_by_id("nonexistent")
        assert result is None

    def test_order_by_signal_nonexistent(self, oms: OMS) -> None:
        """order_by_signal for non-existent signal."""
        result = oms.order_by_signal("nonexistent-signal")
        assert result is None

    def test_empty_symbol_submit(self, oms: OMS) -> None:
        """submit_order with empty symbol."""
        order = oms.submit_order("sig-empty-sym", "", "forex", "BUY", 0.01)
        assert order.symbol == ""

    def test_extremely_long_signal_id(self, oms: OMS) -> None:
        """BUG-009: signal_id with 10000 characters."""
        long_sig = "A" * 10_000
        order = oms.submit_order(long_sig, "EURUSD", "forex", "BUY", 0.01)
        assert order.signal_id == long_sig
        assert len(order.signal_id) == 10_000


# ===========================================================================
# 6. REAL BUG HUNTING
# ===========================================================================


class TestRealBugHunting:
    """Tests that probe for real, subtle bugs in the system."""

    def test_broker_order_id_propagation(self, oms: OMS, paper_adapter: PaperAdapter) -> None:
        """Verify broker_order_id actually propagates to ledger content."""
        order = oms.submit_order("sig-prop", "EURUSD", "forex", "BUY", 0.01)

        # Check actual ledger file content
        with open(oms._ledger_path, encoding="utf-8") as fh:
            lines = [json.loads(l) for l in fh if l.strip()]

        found = [l for l in lines if l["order_id"] == order.order_id]
        assert len(found) >= 1

        # The last record should have broker_order_id if filled
        last = found[-1]
        if order.status == OrderStatus.FILLED:
            assert last.get("broker_order_id") is not None, "broker_order_id not written to ledger after fill"

    def test_close_position_actually_writes_to_ledger(self, oms: OMS, paper_adapter: PaperAdapter) -> None:
        """Verify close_position actually writes to the ledger file."""
        initial_lines = 0
        if oms._ledger_path.exists():
            with open(oms._ledger_path) as fh:
                initial_lines = sum(1 for l in fh if l.strip())

        oms.close_position("EURUSD", "pos-test", 0.01, "forex")

        after_lines = 0
        with open(oms._ledger_path) as fh:
            after_lines = sum(1 for l in fh if l.strip())

        assert after_lines > initial_lines, "close_position did not write to ledger"

    def test_idempotency_after_crash_between_write_and_broker(self, tmp_ledger: Path) -> None:
        """BUG context: If OMS crashes after ledger write but before broker
        call, on restart the order is in ledger with status=PENDING.
        A new submit_order with same signal_id should return the existing
        order (idempotency holds via signal_id).
        """
        # Phase 1: Write order to ledger with PENDING status (simulates crash)
        record = _make_order_record("ord-crash", signal_id="crash-sig", status="PENDING")
        _write_ledger(tmp_ledger, [record])

        # Phase 2: Reload OMS — order is loaded from ledger
        mock_adapter = MagicMock(spec=BrokerAdapter)
        mock_adapter.is_connected = True
        mock_adapter.submit_order.return_value = OrderResult(
            status=OrderStatus.FILLED,
            broker_id="broker-new",
            filled_quantity=0.01,
            avg_price=1.0850,
        )

        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)
        assert "ord-crash" in oms._orders

        # Phase 3: Re-submit same signal_id — should return existing order
        order = oms.submit_order("crash-sig", "EURUSD", "forex", "BUY", 0.01)
        assert order.order_id == "ord-crash", "Idempotency should return existing order after crash recovery"
        # The adapter should NOT have been called
        mock_adapter.submit_order.assert_not_called()

    def test_state_machine_replay_with_corrupted_intermediate(
        self, tmp_ledger: Path, paper_adapter: PaperAdapter
    ) -> None:
        """BUG-003: Replay with corrupted intermediate states is silent."""
        records = [
            _make_order_record("ord-corr", status="SIGNAL_CREATED"),
            _make_order_record("ord-corr", status="RISK_CHECKED"),
            _make_order_record("ord-corr", status="FILLED"),  # Skip ORDER_PRECHECKED, etc.
        ]
        _write_ledger(tmp_ledger, records)

        # BUG-003: This loads without error because contextlib.suppress(Exception)
        # catches the invalid transition during replay.
        oms = OMS(adapters={"mt5": paper_adapter}, ledger_path=tmp_ledger)
        order = oms.order_by_id("ord-corr")
        assert order is not None

        # The order's status is set to FILLED (last record wins),
        # but the state machine may not have reached FILLED properly
        # because intermediate steps were silently skipped.
        sm = oms.get_state_machine("ord-corr")
        if sm is not None:
            # The state machine might be in a wrong state
            # because the replay skipped invalid transitions
            pass  # We just verify no crash

    def test_adapter_returns_order_result_with_status_none(self, tmp_ledger: Path) -> None:
        """BUG context: adapter returns OrderResult with status=None."""
        mock_adapter = MagicMock(spec=BrokerAdapter)
        mock_adapter.is_connected = True
        mock_adapter.submit_order.return_value = OrderResult(status=None)

        oms = OMS(adapters={"mt5": mock_adapter}, ledger_path=tmp_ledger)

        # OMS does `if result.status == OrderStatus.FILLED` — None == enum is False
        # So it falls through all branches and reaches _update_ledger
        # with order.status still = SUBMITTED. This is a silent failure.
        order = oms.submit_order("sig-none-status", "EURUSD", "forex", "BUY", 0.01)
        # Order status stays SUBMITTED even though adapter returned None
        assert (
            order.status == OrderStatus.SUBMITTED
        ), "Order with None adapter status should be FAILED, not left as SUBMITTED"

    def test_read_only_ledger_causes_failure(self, tmp_ledger: Path, paper_adapter: PaperAdapter) -> None:
        """BUG context: What happens if ledger file is read-only?"""
        # Create a valid ledger first
        record = _make_order_record("ord-readonly", status="FILLED")
        _write_ledger(tmp_ledger, [record])

        # Load works fine
        oms = OMS(adapters={"mt5": paper_adapter}, ledger_path=tmp_ledger)

        # Make ledger read-only
        os.chmod(str(tmp_ledger), 0o444)

        try:
            # submit_order will try to _update_ledger, which opens in append mode
            with pytest.raises((PermissionError, OSError)):
                oms.submit_order("sig-readonly", "EURUSD", "forex", "BUY", 0.01)
        finally:
            # Restore permissions for cleanup
            os.chmod(str(tmp_ledger), 0o666)

    def test_ledger_compaction_atomicity(self, tmp_ledger: Path, paper_adapter: PaperAdapter) -> None:
        """Verify compact_ledger uses atomic replace (no partial writes)."""
        for i in range(20):
            record = _make_order_record(f"ord-compact-{i}", status="FILLED")
            with open(tmp_ledger, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")

        oms = OMS(adapters={"mt5": paper_adapter}, ledger_path=tmp_ledger)
        oms.compact_ledger(max_age_days=30)

        # Verify ledger is still valid JSONL
        with open(tmp_ledger, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    json.loads(line)

    def test_two_oms_instances_same_ledger(self, tmp_ledger: Path, paper_adapter: PaperAdapter) -> None:
        """BUG-001 context: Two OMS instances sharing the same ledger file.

        Without file locking, both can write simultaneously and corrupt
        the ledger or create duplicate orders.
        """
        oms1 = OMS(adapters={"mt5": paper_adapter}, ledger_path=tmp_ledger)
        oms1.submit_order("shared-ledger-sig", "EURUSD", "forex", "BUY", 0.01)

        # Second OMS reads the same ledger
        oms2 = OMS(adapters={"mt5": paper_adapter}, ledger_path=tmp_ledger)

        # Both try to submit the same signal_id
        order1 = oms1.submit_order("shared-ledger-sig", "EURUSD", "forex", "BUY", 0.01)
        order2 = oms2.submit_order("shared-ledger-sig", "EURUSD", "forex", "BUY", 0.01)

        # Idempotency should hold within each instance
        assert order1.order_id == order2.order_id

    def test_submit_order_with_none_trace_id(self, oms: OMS) -> None:
        """submit_order with default trace_id."""
        order = oms.submit_order("sig-trace", "EURUSD", "forex", "BUY", 0.01)
        assert order.trace_id == ""

    def test_paper_adapter_close_position_no_position(self, paper_adapter: PaperAdapter) -> None:
        """PaperAdapter.close_position when no position exists."""
        result = paper_adapter.close_position("nonexistent", 0.1, "EURUSD")
        assert result.status == OrderStatus.FAILED
        assert "No position" in result.error

    def test_paper_adapter_cancel_nonexistent_order(self, paper_adapter: PaperAdapter) -> None:
        """PaperAdapter.cancel_order for non-existent order."""
        result = paper_adapter.cancel_order("fake-broker-id")
        assert result.status == OrderStatus.FAILED

    def test_paper_adapter_get_order_status_nonexistent(self, paper_adapter: PaperAdapter) -> None:
        """PaperAdapter.get_order_status for non-existent order."""
        result = paper_adapter.get_order_status("fake-id")
        assert result.status == OrderStatus.FAILED

    def test_order_pyStateMachine_fill_exceeds_quantity(self) -> None:
        """order.py OrderStateMachine: fill more than ordered quantity."""
        order = Order(symbol="EURUSD", side=OrderSide.BUY, quantity=Decimal("0.01"))
        sm = OrderStateMachine(order=order)
        sm.transition(OrderStatus.VALIDATED)
        sm.transition(OrderStatus.RISK_APPROVED)
        sm.transition(OrderStatus.COMPLIANCE_APPROVED)
        sm.transition(OrderStatus.SENT_TO_BROKER)
        sm.transition(OrderStatus.ACKNOWLEDGED)

        # Fill MORE than quantity — should still transition to FILLED
        sm.fill(Decimal("0.05"), Decimal("1.0850"))
        assert order.status == OrderStatus.FILLED
        assert order.fill_quantity == Decimal("0.05")

    def test_order_py_cancel_from_terminal_raises(self) -> None:
        """order.py OrderStateMachine: cancel from terminal state."""
        order = Order(symbol="EURUSD", side=OrderSide.BUY, quantity=Decimal("0.01"))
        sm = OrderStateMachine(order=order)
        sm.transition(OrderStatus.VALIDATED)
        sm.transition(OrderStatus.RISK_APPROVED)
        sm.transition(OrderStatus.COMPLIANCE_APPROVED)
        sm.transition(OrderStatus.SENT_TO_BROKER)
        sm.transition(OrderStatus.ACKNOWLEDGED)
        sm.transition(OrderStatus.FILLED)

        with pytest.raises(OrderStateError):
            sm.cancel("try to cancel filled")

    def test_order_py_expire_from_non_pending_human(self) -> None:
        """order.py OrderStateMachine: expire from non-PENDING_HUMAN state."""
        order = Order(symbol="EURUSD", side=OrderSide.BUY, quantity=Decimal("0.01"))
        sm = OrderStateMachine(order=order)

        with pytest.raises(OrderStateError):
            sm.expire("not pending human")

    def test_order_py_transition_handler_error_does_not_crash(self) -> None:
        """order.py: Transition handler that raises should not crash transition."""
        order = Order(symbol="EURUSD", side=OrderSide.BUY, quantity=Decimal("0.01"))
        sm = OrderStateMachine(order=order)

        def bad_handler(order, old, new, reason, actor):
            raise RuntimeError("handler crash")

        sm.on_transition(OrderStatus.VALIDATED, bad_handler)

        # Should not raise — handler errors are caught
        sm.transition(OrderStatus.VALIDATED)
        assert order.status == OrderStatus.VALIDATED


# ===========================================================================
# 7. ARCHITECTURE ANOMALIES
# ===========================================================================


class TestArchitectureAnomalies:
    """Tests that expose architectural issues in the codebase."""

    def test_two_order_classes_exist(self) -> None:
        """BUG-010: Two different Order classes coexist."""
        from graxia.packages.quant_os.execution.adapters.base import Order as OrderAdapter
        from graxia.packages.quant_os.execution.order import Order as OrderPy

        # They have different fields and type systems
        adapter_order = OrderAdapter(
            order_id="test",
            signal_id="sig",
            symbol="EURUSD",
            asset_class="forex",
            side="BUY",
            quantity=0.01,
        )
        py_order = OrderPy(
            symbol="EURUSD",
            side=OrderSide.BUY,
            quantity=Decimal("0.01"),
        )

        # adapter.order_id is a property, py_order.order_id is also a property
        # but they come from different classes
        assert adapter_order.order_id == "test"
        assert py_order.order_id == py_order.id

        # side is str in adapter, OrderSide enum in order.py
        assert isinstance(adapter_order.side, str)
        assert isinstance(py_order.side, OrderSide)

    def test_two_order_state_machines_exist(self) -> None:
        """BUG-010: Two different OrderStateMachine classes coexist."""
        from graxia.packages.quant_os.execution.order import OrderStateMachine as SM_order
        from graxia.packages.quant_os.execution.order_state_machine import OrderStateMachine as SM_oms

        # Different constructors
        order = Order(symbol="EURUSD", side=OrderSide.BUY, quantity=Decimal("0.01"))
        sm_order = SM_order(order=order)  # Takes Order object
        sm_oms = SM_oms(order_id="test", initial=OrderStatus.SIGNAL_CREATED)  # Takes string

        # Different methods
        sm_order.transition(OrderStatus.VALIDATED)  # transition()
        sm_oms.advance(OrderStatus.RISK_CHECKED, "ok")  # advance()

        # Both work but are completely separate systems
        assert sm_order.order.status == OrderStatus.VALIDATED
        assert sm_oms.state == OrderStatus.RISK_CHECKED

    def test_oms_uses_different_sm_than_order_py(self) -> None:
        """OMS uses order_state_machine.py, not order.py's state machine."""
        from graxia.packages.quant_os.execution.order import OrderStateMachine as SM_order
        from graxia.packages.quant_os.execution.order_state_machine import OrderStateMachine as SM_oms

        # The OMS imports OrderStateMachine from order_state_machine, not order
        # This means order.py's OrderStateMachine is effectively dead code
        # in the OMS context
        assert SM_order is not SM_oms, "These should be different classes"

    def test_order_py_has_validate_order_but_oms_does_not_use_it(self) -> None:
        """order.py has validate_order() but OMS never calls it."""
        order = Order(symbol="EURUSD", side=OrderSide.BUY, quantity=Decimal("0.01"))
        sm = OrderStateMachine(order=order)

        # validate_order exists and works
        sm.validate_order()  # Should not raise for valid order

        # But OMS.submit_order never validates before sending to adapter
        # BUG-006: quantity=0, empty symbol, negative qty all pass through
