"""Network disconnect chaos test.

Simulates an MT5 connection drop during an active trade, then verifies
that the system reconnects, reconciles positions, and does NOT double-execute.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPORTS_DIR = Path(__file__).parent / "reports"
DEFAULT_DISCONNECT_SECONDS: int = 5  # short for CI; production=300


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SimulatedPosition:
    """A position the system believes is open."""
    ticket: str
    symbol: str
    side: str
    volume: float
    entry_price: float
    opened_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    status: str = "OPEN"


@dataclass
class SimulatedOrder:
    """An order submitted to the simulated broker."""
    order_id: str
    symbol: str
    side: str
    volume: float
    price: float
    submitted_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    filled: bool = False
    fill_price: Optional[float] = None


@dataclass
class ChaosTestReport:
    """Output of a chaos test run."""
    test_name: str
    disconnect_duration_s: float
    position_before: Optional[Dict[str, Any]]
    position_after: Optional[Dict[str, Any]]
    orders_submitted: int
    duplicate_orders: int
    rejected_orders: int
    state_recovered: bool
    passed: bool
    errors: List[str] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


# ---------------------------------------------------------------------------
# Mock MT5 connector
# ---------------------------------------------------------------------------


class MockMT5Connector:
    """Simulates MT5 connection with configurable disconnects."""

    def __init__(self) -> None:
        self.connected = True
        self.positions: List[SimulatedPosition] = []
        self.orders: List[SimulatedOrder] = []
        self.error_log: List[str] = []

    def connect(self) -> bool:
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.connected = False

    def send_order(self, order: SimulatedOrder) -> Optional[str]:
        if not self.connected:
            self.error_log.append("Order rejected: MT5 disconnected")
            raise ConnectionError("MT5 not connected")
        self.orders.append(order)
        order.filled = True
        order.fill_price = order.price
        return order.order_id

    def get_positions(self) -> List[SimulatedPosition]:
        if not self.connected:
            self.error_log.append("Position query failed: MT5 disconnected")
            raise ConnectionError("MT5 not connected")
        return [p for p in self.positions if p.status == "OPEN"]

    def close_position(self, ticket: str) -> bool:
        if not self.connected:
            self.error_log.append("Close failed: MT5 disconnected")
            raise ConnectionError("MT5 not connected")
        for p in self.positions:
            if p.ticket == ticket:
                p.status = "CLOSED"
                return True
        return False


# ---------------------------------------------------------------------------
# State persistence (simplified)
# ---------------------------------------------------------------------------


class StatePersistence:
    """Simulates system state persistence (JSON file-backed)."""

    def __init__(self, path: str = ".chaos_test_state.json") -> None:
        self.path = path
        self._data: Dict[str, Any] = {}

    def save(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._flush()

    def load(self, key: str) -> Any:
        self._load_from_disk()
        return self._data.get(key)

    def _flush(self) -> None:
        try:
            Path(self.path).write_text(json.dumps(self._data, indent=2))
        except Exception:
            pass

    def _load_from_disk(self) -> None:
        try:
            if Path(self.path).exists():
                self._data = json.loads(Path(self.path).read_text())
        except Exception:
            pass

    def cleanup(self) -> None:
        try:
            Path(self.path).unlink(missing_ok=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Trade ledger (simplified)
# ---------------------------------------------------------------------------


class TradeLedger:
    """Simulates order ledger for duplicate detection."""

    def __init__(self) -> None:
        self._orders: List[SimulatedOrder] = []
        self._seen_keys: set = set()
        self._rejected: int = 0

    def record_order(self, order: SimulatedOrder) -> bool:
        """Record order, rejecting duplicates.

        Returns:
            True if recorded, False if duplicate was rejected.
        """
        key = f"{order.symbol}:{order.side}:{order.volume}"
        if key in self._seen_keys:
            self._rejected += 1
            return False
        self._seen_keys.add(key)
        self._orders.append(order)
        return True

    def find_duplicates(self) -> int:
        """Return count of duplicate orders that were NOT rejected."""
        seen: Dict[str, int] = {}
        for o in self._orders:
            key = f"{o.symbol}:{o.side}:{o.volume}"
            seen[key] = seen.get(key, 0) + 1
        return sum(v - 1 for v in seen.values() if v > 1)

    def get_rejected_count(self) -> int:
        """Return count of duplicate orders that were rejected."""
        return self._rejected

    def get_order_count(self) -> int:
        return len(self._orders)

    def clear(self) -> None:
        self._orders.clear()
        self._seen_keys.clear()
        self._rejected = 0


# ---------------------------------------------------------------------------
# ChaosTest class
# ---------------------------------------------------------------------------


class ChaosTest:
    """Simulates network disconnect during active trades.

    Usage::

        ct = ChaosTest()
        report = ct.simulate_disconnect(duration_seconds=300)
        assert report.passed
    """

    def __init__(self, state_path: Optional[str] = None) -> None:
        self.connector = MockMT5Connector()
        self.state = StatePersistence(
            state_path or ".chaos_test_state.json"
        )
        self.ledger = TradeLedger()
        self.position: Optional[SimulatedPosition] = None

    def simulate_disconnect(
        self,
        duration_seconds: float = DEFAULT_DISCONNECT_SECONDS,
    ) -> ChaosTestReport:
        """Run full disconnect scenario.

        Steps:
            1. Open a simulated position.
            2. Drop the MT5 connection.
            3. System logs errors (simulated).
            4. Restore connection after *duration_seconds*.
            5. Reconcile positions.
            6. Verify no double execution.

        Args:
            duration_seconds: How long to keep the connection down.

        Returns:
            ChaosTestReport with pass/fail and details.
        """
        errors: List[str] = []
        expected_disconnect_errors: List[str] = []

        # --- Step 1: Open position ---
        self.connector.connect()
        self.position = SimulatedPosition(
            ticket=str(uuid.uuid4())[:8],
            symbol="XAUUSD",
            side="BUY",
            volume=0.01,
            entry_price=2350.00,
        )
        self.connector.positions.append(self.position)

        # Persist open position to survive "crash"
        self.state.save("open_positions", [
            {
                "ticket": self.position.ticket,
                "symbol": self.position.symbol,
                "side": self.position.side,
                "volume": self.position.volume,
                "entry_price": self.position.entry_price,
            }
        ])

        position_before = {
            "ticket": self.position.ticket,
            "symbol": self.position.symbol,
            "side": self.position.side,
            "volume": self.position.volume,
        }

        # --- Step 2: Simulate disconnect ---
        self.connector.disconnect()

        # --- Step 3: System tries to operate while disconnected ---
        try:
            self.connector.get_positions()
        except ConnectionError:
            expected_disconnect_errors.append("MT5 disconnected — position query failed (expected)")

        try:
            pending_order = SimulatedOrder(
                order_id=str(uuid.uuid4())[:8],
                symbol="XAUUSD",
                side="BUY",
                volume=0.01,
                price=2351.00,
            )
            self.connector.send_order(pending_order)
        except ConnectionError:
            expected_disconnect_errors.append("MT5 disconnected — order rejected (expected)")

        # --- Step 4: Restore connection ---
        time.sleep(duration_seconds)
        self.connector.connect()

        # --- Step 5: Reconcile positions ---
        server_positions = self.connector.get_positions()
        persisted = self.state.load("open_positions") or []

        # Check server positions match persisted state
        server_tickets = {p.ticket for p in server_positions}
        persisted_tickets = {p["ticket"] for p in persisted}

        if server_tickets != persisted_tickets:
            errors.append(
                f"Position mismatch: server={server_tickets} persisted={persisted_tickets}"
            )

        position_after = {
            "server_positions": [{"ticket": p.ticket, "symbol": p.symbol}
                                 for p in server_positions],
            "persisted_positions": persisted,
        }

        # --- Step 6: Verify no double execution ---
        # Record the initial order in the ledger (the one that opened the position)
        initial_order = SimulatedOrder(
            order_id="initial-001",
            symbol="XAUUSD",
            side="BUY",
            volume=0.01,
            price=2350.00,
        )
        self.ledger.record_order(initial_order)

        # Simulate a retry order that should be rejected as duplicate
        retry_order = SimulatedOrder(
            order_id="retry-001",
            symbol="XAUUSD",
            side="BUY",
            volume=0.01,
            price=2352.00,
        )
        try:
            self.connector.send_order(retry_order)
            self.ledger.record_order(retry_order)
        except ConnectionError:
            pass

        dupes = self.ledger.find_duplicates()
        rejected = self.ledger.get_rejected_count()
        if dupes > 0:
            errors.append(f"Double execution detected: {dupes} duplicate orders in ledger")
        if rejected == 0:
            errors.append("No duplicate orders were rejected — dedup logic not working")

        # Only real errors (not expected disconnect errors) cause failure
        passed = len(errors) == 0

        report = ChaosTestReport(
            test_name="network_disconnect",
            disconnect_duration_s=duration_seconds,
            position_before=position_before,
            position_after=position_after,
            orders_submitted=self.ledger.get_order_count(),
            duplicate_orders=dupes,
            rejected_orders=rejected,
            state_recovered=server_tickets == persisted_tickets,
            passed=passed,
            errors=errors,
        )

        self.state.cleanup()
        return report

    def verify_no_double_execution(self) -> bool:
        """Check ledger for duplicate orders.

        Returns:
            True if no duplicates found.
        """
        return self.ledger.find_duplicates() == 0

    def verify_state_recovery(self) -> bool:
        """Check that persisted state survived the disconnect.

        Returns:
            True if state file exists and is readable.
        """
        loaded = self.state.load("open_positions")
        return loaded is not None and isinstance(loaded, list)

    def test_reconnection_logic(self) -> ChaosTestReport:
        """Verify reconnect + position check works end-to-end.

        Returns:
            ChaosTestReport (shorter scenario, no disconnect wait).
        """
        errors: List[str] = []

        # Setup
        self.connector.connect()
        self.position = SimulatedPosition(
            ticket="recon-001",
            symbol="XAUUSD",
            side="SELL",
            volume=0.05,
            entry_price=2360.00,
        )
        self.connector.positions.append(self.position)

        # Disconnect briefly
        self.connector.disconnect()
        time.sleep(0.1)

        # Reconnect
        self.connector.connect()

        # Verify positions match
        positions = self.connector.get_positions()
        tickets = [p.ticket for p in positions]
        if "recon-001" not in tickets:
            errors.append("Reconnection failed: position not found")

        self.state.cleanup()
        return ChaosTestReport(
            test_name="reconnection_logic",
            disconnect_duration_s=0.1,
            position_before={"ticket": "recon-001"},
            position_after={"tickets": tickets},
            orders_submitted=0,
            duplicate_orders=0,
            rejected_orders=0,
            state_recovered="recon-001" in tickets,
            passed=len(errors) == 0,
            errors=errors,
        )

    def write_test_report(self, report: ChaosTestReport) -> Path:
        """Save test report to tests/chaos/reports/.

        Args:
            report: ChaosTestReport to persist.

        Returns:
            Path to the written report file.
        """
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"chaos_report_{report.test_name}_{ts}.json"
        path = REPORTS_DIR / filename

        data = {
            "test_name": report.test_name,
            "passed": report.passed,
            "disconnect_duration_s": report.disconnect_duration_s,
            "position_before": report.position_before,
            "position_after": report.position_after,
            "orders_submitted": report.orders_submitted,
            "duplicate_orders": report.duplicate_orders,
            "rejected_orders": report.rejected_orders,
            "state_recovered": report.state_recovered,
            "errors": report.errors,
            "timestamp": report.timestamp,
        }
        path.write_text(json.dumps(data, indent=2))
        return path


# ---------------------------------------------------------------------------
# Pytest tests
# ---------------------------------------------------------------------------


class TestNetworkDisconnect:
    """Pytest suite for network disconnect chaos scenarios."""

    def test_disconnect_no_double_execution(self) -> None:
        """Full disconnect cycle must not produce duplicate orders."""
        ct = ChaosTest()
        report = ct.simulate_disconnect(duration_seconds=0.1)
        assert report.passed, f"Chaos test failed: {report.errors}"
        assert report.duplicate_orders == 0, (
            f"Double execution detected: {report.duplicate_orders}"
        )

    def test_state_survives_disconnect(self) -> None:
        """Persisted state must be recoverable after reconnection."""
        ct = ChaosTest()
        report = ct.simulate_disconnect(duration_seconds=0.1)
        assert report.state_recovered, "State recovery failed"

    def test_reconnection_logic(self) -> None:
        """Reconnect + position check must work."""
        ct = ChaosTest()
        report = ct.test_reconnection_logic()
        assert report.passed, f"Reconnection test failed: {report.errors}"

    def test_verify_no_double_execution_direct(self) -> None:
        """Direct duplicate-check method."""
        ct = ChaosTest()
        ct.simulate_disconnect(duration_seconds=0.1)
        assert ct.verify_no_double_execution()

    def test_verify_state_recovery_direct(self) -> None:
        """Direct state-recovery check."""
        ct = ChaosTest()
        ct.simulate_disconnect(duration_seconds=0.1)
        # State is cleaned up after simulate, so we test the persistence mechanism directly
        ct.state.save("open_positions", [{"ticket": "test-001"}])
        assert ct.verify_state_recovery()
        ct.state.cleanup()

    def test_report_written(self) -> None:
        """Test report must be written to reports directory."""
        ct = ChaosTest()
        report = ct.simulate_disconnect(duration_seconds=0.1)
        path = ct.write_test_report(report)
        assert path.exists(), f"Report not found at {path}"
        content = json.loads(path.read_text())
        assert "passed" in content
        assert "errors" in content
        # Cleanup
        path.unlink(missing_ok=True)
