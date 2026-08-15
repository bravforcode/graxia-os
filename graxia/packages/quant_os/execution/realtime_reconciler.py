"""Real-time Position Reconciler — wires PositionReconciler to live trading loop.

Runs reconciliation on a configurable interval (every N bars or every N seconds).
On drift detection:
  - Sends alert via AlertManager
  - Auto-closes drifted positions if configured
  - Logs to audit trail

Usage:
    reconciler = RealtimeReconciler(
        reconciler=PositionReconciler(config),
        broker_adapter=mt5_adapter,
        alert_manager=alert_manager,
        interval_bars=1,
    )
    reconciler.on_bar(bar)  # called by trading loop
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from ..core.enums import IncidentSeverity
from ..core.events import BarEvent
from ..core.position_manager import Position
from ..monitoring.alerts import Alert, AlertManager
from .adapters.base import BrokerAdapter
from .position_reconciler import (
    BrokerPosition,
    InternalPosition,
    PositionReconciler,
    ReconciliationConfig,
    ReconciliationResult,
)

logger = logging.getLogger(__name__)


class RealtimeReconciler:
    """Wires PositionReconciler into the live trading loop.

    Calls reconciliation every N bars (or N seconds) and handles drift
    by alerting and optionally auto-closing drifted positions.
    """

    def __init__(
        self,
        reconciler: PositionReconciler,
        broker_adapter: BrokerAdapter,
        alert_manager: AlertManager,
        engine: Any | None = None,
        interval_bars: int = 1,
        interval_seconds: float = 0.0,
    ):
        self._reconciler = reconciler
        self._broker_adapter = broker_adapter
        self._alert_manager = alert_manager
        self._engine = engine  # PositionManager or TradingLoop with get_positions()
        self._interval_bars = interval_bars
        self._interval_seconds = interval_seconds

        self._bar_count: int = 0
        self._last_reconcile_time: float = 0.0
        self._running: bool = False
        self._lock = threading.Lock()

        # Audit trail
        self._reconciliation_log: list[ReconciliationResult] = []

    # ── Public API ────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """Return True if the reconciler is active."""
        return self._running

    def start(self) -> None:
        """Start accepting bars for reconciliation."""
        with self._lock:
            self._running = True
            self._bar_count = 0
            self._last_reconcile_time = time.time()
        logger.info("realtime_reconciler.started interval_bars=%d interval_sec=%.1f",
                     self._interval_bars, self._interval_seconds)

    def stop(self) -> None:
        """Stop accepting bars for reconciliation."""
        with self._lock:
            self._running = False
        logger.info("realtime_reconciler.stopped total_reconciliations=%d",
                     len(self._reconciliation_log))

    def reconcile_now(self) -> ReconciliationResult:
        """Run reconciliation immediately, regardless of bar/time interval.

        P0-B11 fix (2026-07-28): this is the crash-recovery entry point —
        call once at process/session startup, before accepting any new
        signals, to detect positions that drifted while the process was
        down (broker fills that arrived during a crash, orphaned
        positions from an ungraceful shutdown, etc.). Unlike ``on_bar``,
        this does not require the reconciler to be ``started`` first and
        always runs (there is no interval to be "not due" for a startup check).
        """
        result = self._run_reconciliation(time.time())
        if result.drift_detected:
            self._handle_drift(result)
        self._reconciliation_log.append(result)
        return result

    def on_bar(self, bar: BarEvent) -> ReconciliationResult | None:
        """Called every bar by the trading loop.

        Returns ReconciliationResult if reconciliation ran, None otherwise.
        """
        with self._lock:
            if not self._running:
                return None

            self._bar_count += 1

            # Check bar interval
            bar_due = self._bar_count % self._interval_bars == 0

            # Check time interval
            time_due = False
            if self._interval_seconds > 0:
                elapsed = time.time() - self._last_reconcile_time
                time_due = elapsed >= self._interval_seconds

            if not bar_due and not time_due:
                return None

            self._last_reconcile_time = time.time()

        # Run reconciliation outside lock (broker call may block)
        try:
            result = self._run_reconciliation(bar.timestamp.timestamp() if hasattr(bar.timestamp, 'timestamp') else time.time())
        except Exception:
            logger.exception("realtime_reconciler.error bar_index=%d", bar.bar_index)
            return None

        if result.drift_detected:
            self._handle_drift(result)

        self._reconciliation_log.append(result)
        return result

    # ── Internal ──────────────────────────────────────────────────────

    def _run_reconciliation(self, timestamp: float = 0.0) -> ReconciliationResult:
        """Get positions from broker + internal, then reconcile."""
        internal = self._get_internal_positions()
        broker = self._get_broker_positions()
        result = self._reconciler.reconcile(internal, broker, timestamp)

        logger.info(
            "realtime_reconciler.run matched=%s drift=%s internal=%d broker=%d mismatches=%d",
            result.matched,
            result.drift_detected,
            result.position_count_internal,
            result.position_count_broker,
            len(result.mismatches),
        )
        return result

    def _handle_drift(self, result: ReconciliationResult) -> None:
        """Send alert and auto-close drifted positions if configured."""
        mismatch_summary = "; ".join(
            m.get("message", str(m)) for m in result.mismatches[:5]
        )

        severity = IncidentSeverity.P1 if result.action_required == "CLOSE_DRIFT" else IncidentSeverity.P2

        alert = Alert(
            severity=severity,
            title="Position Drift Detected",
            message=(
                f"Internal={result.position_count_internal} "
                f"Broker={result.position_count_broker} "
                f"Mismatches={len(result.mismatches)}: {mismatch_summary}"
            ),
            timestamp=datetime.now(UTC),
            context={
                "action_required": result.action_required,
                "mismatches": result.mismatches,
            },
        )

        # Fire alert async (best-effort from sync context)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._alert_manager.send_alert(alert))
        except RuntimeError:
            # No running loop — log and move on
            logger.warning("realtime_reconciler.alert_skip reason=no_event_loop")

        # Auto-close drifted positions if configured
        if result.action_required == "CLOSE_DRIFT":
            self._close_drifted_positions(result)

    def _close_drifted_positions(self, result: ReconciliationResult) -> None:
        """Attempt to close positions that have drifted from broker state."""
        drift_positions = self._reconciler.get_drift_positions()
        for pos in drift_positions:
            symbol = pos.get("symbol", "")
            broker_qty = pos.get("broker_qty", Decimal("0"))
            logger.warning(
                "realtime_reconciler.close_drift symbol=%s broker_qty=%s type=%s",
                symbol,
                broker_qty,
                pos.get("type"),
            )
            # Actual close delegated to broker adapter if it exposes close_position
            if hasattr(self._broker_adapter, "close_position") and symbol:
                try:
                    # Close by symbol — adapter resolves ticket
                    self._broker_adapter.close_position(
                        broker_position_id=symbol,
                        volume=float(broker_qty),
                        symbol=symbol,
                    )
                except Exception:
                    logger.exception("realtime_reconciler.close_drift_failed symbol=%s", symbol)

    def _get_internal_positions(self) -> list[InternalPosition]:
        """Convert engine positions to InternalPosition list."""
        if self._engine is None:
            return []

        positions: dict[str, Position] = {}
        if hasattr(self._engine, "get_positions"):
            positions = self._engine.get_positions()

        result = []
        for pos in positions.values():
            result.append(InternalPosition(
                symbol=pos.symbol,
                side="LONG" if pos.side == "BUY" else "SHORT",
                quantity=Decimal(str(pos.quantity)),
                entry_price=Decimal(str(pos.entry_price)),
                strategy_id=getattr(pos, "strategy_id", ""),
            ))
        return result

    def _get_broker_positions(self) -> list[BrokerPosition]:
        """Convert broker adapter dict positions to BrokerPosition list."""
        try:
            raw: list[dict] = self._broker_adapter.get_positions()
        except Exception:
            logger.exception("realtime_reconciler.broker_error")
            return []

        result = []
        for p in raw:
            result.append(BrokerPosition(
                symbol=p.get("symbol", ""),
                side="LONG" if p.get("side", "").upper() in ("BUY", "LONG") else "SHORT",
                quantity=Decimal(str(p.get("volume", p.get("quantity", 0)))),
                avg_price=Decimal(str(p.get("avg_price", p.get("price", 0)))),
                unrealized_pnl=Decimal(str(p.get("unrealized_pnl", 0))),
            ))
        return result
