"""Centralized Kill Switch State Coordinator.

Ensures all 5 kill switch stores remain in sync when any source
activates or deactivates the kill switch.

Architecture:
    When ANY subsystem triggers the kill switch (manual, circuit breaker,
    risk overlay, telegram command), the coordinator propagates the state
    to all 5 stores and publishes a KillSwitchEvent on the EventBus.

Stores coordinated:
    1. SystemState.kill_switch_active (core/state_store.py)
    2. KillSwitch.is_active() (risk/kill_switch.py)
    3. TradingLoop._kill_switch_active (core/trading_loop.py) — via EventBus
    4. RiskOverlay.kill_switch_triggered (regime/risk_overlay.py)
    5. RiskLedger.kill_switch_state (risk/risk_ledger.py)

Thread-safety:
    All mutations are guarded by a lock with a re-entry flag
    to prevent infinite recursion when stores callback to the coordinator.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class StateCoordinator:
    """Coordinates kill switch state across all subsystem stores.

    Usage::

        coordinator = StateCoordinator(
            bus=event_bus,
            state_store=system_state,
            kill_switch=kill_switch,
            risk_overlay=risk_overlay,
            risk_ledger=risk_ledger,
            trading_loop=trading_loop,
        )

        # Wire coordinator into each store:
        kill_switch.set_coordinator(coordinator)
        risk_overlay.set_coordinator(coordinator)
        risk_ledger.set_coordinator(coordinator)

        # Now any store can trigger full sync:
        kill_switch.activate(reason="manual")  # -> syncs all 5 stores
    """

    def __init__(
        self,
        bus: Any = None,
        state_store: Any = None,
        kill_switch: Any = None,
        risk_overlay: Any = None,
        risk_ledger: Any = None,
        trading_loop: Any = None,
    ) -> None:
        self._bus = bus
        self._state_store = state_store
        self._kill_switch = kill_switch
        self._risk_overlay = risk_overlay
        self._risk_ledger = risk_ledger
        self._trading_loop = trading_loop
        self._lock = threading.RLock()
        self._syncing = False

        # Auto-subscribe TradingLoop to KillSwitchEvent if provided
        if self._bus is not None and self._trading_loop is not None:
            from .events import KillSwitchEvent
            self._bus.subscribe(KillSwitchEvent, self._trading_loop.on_kill_switch)

    # ------------------------------------------------------------------
    # Public API — external callers (telegram_commands, tests)
    # ------------------------------------------------------------------

    def activate(self, reason: str, source: str = "unknown") -> None:
        """Activate kill switch across ALL stores and publish event.

        Called externally when no specific store is the trigger.
        """
        self.sync_kill_switch(True, reason, source, triggering_store=None)

    def deactivate(self, reason: str, source: str = "unknown") -> None:
        """Deactivate kill switch across ALL stores."""
        self.sync_kill_switch(False, reason, source, triggering_store=None)

    # ------------------------------------------------------------------
    # Sync API — called by individual stores after state change
    # ------------------------------------------------------------------

    def sync_kill_switch(
        self,
        active: bool,
        reason: str,
        source: str = "unknown",
        triggering_store: str | None = None,
    ) -> None:
        """Propagate kill switch state to all stores.

        Args:
            active: True to activate, False to deactivate.
            reason: Human-readable reason for the change.
            source: Origin identifier (e.g. "telegram:123", "risk_overlay").
            triggering_store: Which store initiated this call (to avoid
                re-triggering it). None means external call — update all.
        """
        with self._lock:
            if self._syncing:
                return
            self._syncing = True
            try:
                self._propagate(active, reason, source, triggering_store)
            finally:
                self._syncing = False

    # ------------------------------------------------------------------
    # Internal propagation
    # ------------------------------------------------------------------

    def _propagate(
        self,
        active: bool,
        reason: str,
        source: str,
        triggering_store: str | None,
    ) -> None:
        """Update all stores except the triggering one, then publish event."""
        if active:
            self._propagate_activate(reason, source, triggering_store)
        else:
            self._propagate_deactivate(reason, source, triggering_store)

    def _propagate_activate(
        self,
        reason: str,
        source: str,
        triggering_store: str | None,
    ) -> None:
        """Set kill switch ACTIVE across all stores."""
        logger.critical(
            "state_coordinator.activate reason=%s source=%s trigger=%s",
            reason,
            source,
            triggering_store,
        )

        # 1. KillSwitch (persistent JSON — authoritative)
        if triggering_store != "kill_switch" and self._kill_switch:
            if hasattr(self._kill_switch, "activate") and not self._kill_switch.is_active():
                self._kill_switch.activate(reason=reason, source=source)

        # 2. SystemState (in-memory, caller persists)
        if triggering_store != "system_state" and self._state_store:
            if hasattr(self._state_store, "kill_switch_active"):
                self._state_store.kill_switch_active = True
                self._state_store.system_state = "HALTED"

        # 3. RiskOverlay (persistent JSON)
        if triggering_store != "risk_overlay" and self._risk_overlay:
            if hasattr(self._risk_overlay, "trigger_kill_switch"):
                if not self._risk_overlay.state.kill_switch_triggered:
                    self._risk_overlay.trigger_kill_switch(reason)

        # 4. RiskLedger (persistent JSON)
        if triggering_store != "risk_ledger" and self._risk_ledger:
            if hasattr(self._risk_ledger, "set_kill_switch_state"):
                self._risk_ledger.set_kill_switch_state("active")

        # 5. EventBus -> TradingLoop and other subscribers
        if self._bus is not None:
            from .events import KillSwitchEvent

            event = KillSwitchEvent(
                trigger=source,
                reason=reason,
                source="state_coordinator",
            )
            self._bus.publish(event)

    def _propagate_deactivate(
        self,
        reason: str,
        source: str,
        triggering_store: str | None,
    ) -> None:
        """Set kill switch INACTIVE across all stores."""
        logger.info(
            "state_coordinator.deactivate reason=%s source=%s trigger=%s",
            reason,
            source,
            triggering_store,
        )

        # 1. KillSwitch
        if triggering_store != "kill_switch" and self._kill_switch:
            if hasattr(self._kill_switch, "deactivate") and self._kill_switch.is_triggered:
                self._kill_switch.deactivate(reason=reason, authorized_by=source)

        # 2. SystemState
        if triggering_store != "system_state" and self._state_store:
            if hasattr(self._state_store, "kill_switch_active"):
                self._state_store.kill_switch_active = False
                self._state_store.system_state = "RUNNING"

        # 3. RiskOverlay
        if triggering_store != "risk_overlay" and self._risk_overlay:
            if hasattr(self._risk_overlay, "release_kill_switch"):
                if self._risk_overlay.state.kill_switch_triggered:
                    self._risk_overlay.release_kill_switch()

        # 4. RiskLedger
        if triggering_store != "risk_ledger" and self._risk_ledger:
            if hasattr(self._risk_ledger, "set_kill_switch_state"):
                self._risk_ledger.set_kill_switch_state("inactive")

        # 5. TradingLoop in-memory reset
        if self._trading_loop and hasattr(self._trading_loop, "reset_kill_switch"):
            self._trading_loop.reset_kill_switch()
