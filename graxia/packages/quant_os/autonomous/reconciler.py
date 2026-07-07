"""Trade Reconciler — compares execution log against broker state.

Periodically checks whether the autonomous loop's execution records
match the broker's actual positions.  Flags discrepancies such as
missing fills (order sent but not reflected) and phantom positions
(broker has a position with no matching execution record).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

from ..execution.adapters.manager import BrokerManager
from .persistence import TradeStore

logger = structlog.get_logger(__name__)


@dataclass
class ReconciliationResult:
    """Outcome of a reconciliation pass."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    total_executions: int = 0
    total_positions: int = 0
    missing_fills: list[dict[str, Any]] = field(default_factory=list)
    phantom_positions: list[dict[str, Any]] = field(default_factory=list)
    is_clean: bool = True


class TradeReconciler:
    """Reconciles autonomous loop execution log with broker state."""

    def __init__(self, broker_manager: BrokerManager, trade_store: TradeStore) -> None:
        self._broker = broker_manager
        self._store = trade_store

    async def reconcile(self) -> ReconciliationResult:
        """Run reconciliation: compare execution log vs broker positions.

        Returns a ``ReconciliationResult`` indicating whether the two
        sources agree or listing discrepancies.
        """
        try:
            positions = self._broker.active.get_positions()
        except Exception as exc:
            logger.error("reconciler.broker_fetch_failed", error=str(exc))
            positions = []

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        executions = self._store.get_execution_log(limit=500)

        successful = [e for e in executions if e.get("success")]
        missing = self._check_missing_fills(successful, positions)
        phantom = self._check_phantom_positions(successful, positions)

        result = ReconciliationResult(
            total_executions=len(successful),
            total_positions=len(positions),
            missing_fills=missing,
            phantom_positions=phantom,
            is_clean=(not missing and not phantom),
        )

        if not result.is_clean:
            logger.warning(
                "reconciler_discrepancies_found",
                missing_fills=len(missing),
                phantom_positions=len(phantom),
            )
        else:
            logger.debug("reconciler_clean", executions=len(successful), positions=len(positions))

        return result

    def _check_missing_fills(
        self, executions: list[dict[str, Any]], positions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Find orders that were submitted but not reflected in broker positions."""
        broker_symbols = {p.get("symbol", "") for p in positions}
        missing: list[dict[str, Any]] = []

        for exec_row in executions:
            symbol = exec_row.get("symbol", "")
            order_id = exec_row.get("order_id", "")
            broker_order_id = exec_row.get("broker_order_id", "")

            if not symbol:
                continue

            has_position = symbol in broker_symbols
            has_broker_id = bool(broker_order_id)

            if not has_position and not has_broker_id:
                missing.append(
                    {
                        "order_id": order_id,
                        "symbol": symbol,
                        "direction": exec_row.get("direction", ""),
                        "entry": exec_row.get("entry", 0.0),
                        "timestamp": exec_row.get("timestamp", ""),
                        "reason": "No matching broker position and no broker order ID",
                    }
                )

        return missing

    def _check_phantom_positions(
        self, executions: list[dict[str, Any]], positions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Find positions that exist on the broker with no matching execution record."""
        executed_symbols = {e.get("symbol", "") for e in executions if e.get("symbol")}
        phantoms: list[dict[str, Any]] = []

        for pos in positions:
            symbol = pos.get("symbol", "")
            if symbol and symbol not in executed_symbols:
                phantoms.append(
                    {
                        "symbol": symbol,
                        "volume": pos.get("volume", 0.0),
                        "price_open": pos.get("price_open", 0.0),
                        "reason": "Broker position has no matching autonomous execution record",
                    }
                )

        return phantoms
