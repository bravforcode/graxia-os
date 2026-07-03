"""
Kill Switch Close-Mode Tests — CLOSE_ALL, idempotency, reconciliation.

Tests the KillSwitch.enforce() method from risk/kill_switch.py with
mock broker adapters to verify:
  - CLOSE_ALL closes every position
  - Calling enforce twice is idempotent (second call is a no-op)
  - Reconciliation verifies broker state after close
"""

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from risk.kill_switch import CloseMode, KillSwitch, KillSwitchState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def state_file(tmp_path: Path) -> str:
    """Return a temporary kill-switch state file path."""
    return str(tmp_path / "kill_switch_state.json")


@pytest.fixture
def ks(state_file: str) -> KillSwitch:
    """Return a fresh INACTIVE KillSwitch."""
    return KillSwitch(state_file=state_file)


def _make_positions(n: int = 3) -> list[dict]:
    """Generate *n* mock broker positions."""
    return [
        {"ticket": 1000 + i, "symbol": f"SYM{i}", "pnl": float(i - 1), "volume": 0.1}
        for i in range(n)
    ]


def _mock_broker(positions: list[dict]) -> MagicMock:
    """Return a mock BrokerAdapterLike backed by *positions*.

    get_positions() always returns the current state of the list
    (reflecting close_position mutations).
    """
    broker = MagicMock()
    broker.get_positions.side_effect = lambda: list(positions)

    def _close(ticket: int) -> None:
        positions[:] = [p for p in positions if p["ticket"] != ticket]

    broker.close_position.side_effect = _close
    return broker


def _mock_readonly(positions: list[dict]) -> MagicMock:
    """Return a mock ReadonlyClientLike reflecting current *positions*."""
    client = MagicMock()
    client.get_positions.return_value = positions
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCloseAllMode:
    """CLOSE_ALL must close every open position."""

    def test_close_all_closes_everything(self, ks: KillSwitch):
        positions = _make_positions(5)
        broker = _mock_broker(positions)
        readonly = _mock_readonly(positions)

        result = ks.enforce(CloseMode.CLOSE_ALL, broker_adapter=broker, readonly_client=readonly)

        assert len(result["closed"]) == 5, "All 5 positions must be closed"
        assert result["failed"] == [], "No failures expected"
        assert broker.close_position.call_count == 5

    def test_close_all_with_empty_positions(self, ks: KillSwitch):
        broker = _mock_broker([])
        result = ks.enforce(CloseMode.CLOSE_ALL, broker_adapter=broker)

        assert result["closed"] == []
        assert result["remaining"] == []

    def test_close_all_with_failing_broker(self, ks: KillSwitch):
        """If close_position raises, the ticket lands in 'failed'."""
        broker = MagicMock()
        broker.get_positions.return_value = _make_positions(2)
        broker.close_position.side_effect = RuntimeError("connection lost")

        result = ks.enforce(CloseMode.CLOSE_ALL, broker_adapter=broker)

        assert len(result["failed"]) == 2
        assert result["closed"] == []


class TestIdempotentClose:
    """Calling enforce twice must not crash or double-close."""

    def test_second_call_is_noop(self, ks: KillSwitch):
        positions = _make_positions(3)
        broker = _mock_broker(positions)
        readonly = _mock_readonly(positions)

        # First call: closes all
        r1 = ks.enforce(CloseMode.CLOSE_ALL, broker_adapter=broker, readonly_client=readonly)
        assert len(r1["closed"]) == 3

        # Second call: no positions left
        r2 = ks.enforce(CloseMode.CLOSE_ALL, broker_adapter=broker, readonly_client=readonly)
        assert r2["closed"] == [], "No positions to close on second call"
        assert r2["remaining"] == []

    def test_no_broker_adapter_returns_empty(self, ks: KillSwitch):
        result = ks.enforce(CloseMode.CLOSE_ALL, broker_adapter=None)
        assert result["closed"] == []
        assert result["reconciled"] is False


class TestReconciliationAfterClose:
    """Reconciliation must verify broker state matches expected close result."""

    def test_reconciliation_success(self, ks: KillSwitch):
        """When all closes succeed, reconciliation must pass."""
        positions = _make_positions(3)
        broker = _mock_broker(positions)
        # After close, readonly sees no positions
        readonly = _mock_readonly([])

        result = ks.enforce(CloseMode.CLOSE_ALL, broker_adapter=broker, readonly_client=readonly)
        assert result["reconciled"] is True

    def test_reconciliation_failure_when_positions_remain(self, ks: KillSwitch):
        """If broker still shows closed tickets, reconciliation must fail."""
        positions = _make_positions(3)
        broker = _mock_broker(positions)
        # Readonly still sees the original positions (close didn't actually work)
        readonly = _mock_readonly(_make_positions(3))

        result = ks.enforce(CloseMode.CLOSE_ALL, broker_adapter=broker, readonly_client=readonly)
        # Closed tickets are {1000, 1001, 1002} but readonly still shows them
        assert result["reconciled"] is False

    def test_reconciliation_trivially_passes_when_nothing_closed(self, ks: KillSwitch):
        """If nothing was supposed to close, reconciliation is trivially True."""
        broker = _mock_broker(_make_positions(2))

        result = ks.enforce(CloseMode.NO_NEW_ORDERS_ONLY, broker_adapter=broker)
        assert result["reconciled"] is True
        assert result["closed"] == []
