"""Regression tests for Phase 0 item 4: kill-switch event delivery must be
fail-closed even when EventBus dispatch to a subscriber fails silently.

EventBus.publish() swallows per-handler exceptions internally (see
core/event_bus.py), so a naive try/except around bus.publish() cannot detect
a subscriber (e.g. TradingLoop.on_kill_switch) crashing mid-dispatch. These
tests exercise core/orchestrator.py::_publish_kill_switch_event's retry +
handler_errors-delta detection + direct-fallback-call mechanism.
"""

from graxia.packages.quant_os.core.config import QuantConfig
from graxia.packages.quant_os.core.events import KillSwitchEvent
from graxia.packages.quant_os.core.orchestrator import TradingOrchestrator


def _make_orchestrator() -> TradingOrchestrator:
    return TradingOrchestrator(config=QuantConfig())


class TestKillSwitchEventDelivery:
    def test_normal_publish_reaches_trading_loop(self):
        orch = _make_orchestrator()
        orch.bus.subscribe(KillSwitchEvent, orch.trading_loop.on_kill_switch)

        orch.trigger_kill_switch(reason="test-trip", source="unit-test")

        assert orch.trading_loop.get_stats()["kill_switch_active"] is True

    def test_bus_delivery_failure_triggers_direct_fallback(self):
        """If every bus-side subscriber fails (handler_errors increments on
        each attempt), the trading loop must still be halted via the
        synchronous direct-call fallback — not left in an unknown state."""
        orch = _make_orchestrator()
        calls = {"n": 0}

        def always_broken(event):
            calls["n"] += 1
            raise RuntimeError("simulated subscriber crash")

        # trading_loop.on_kill_switch is intentionally NOT subscribed here —
        # only a persistently-broken handler is. The direct fallback inside
        # _publish_kill_switch_event is what must reach the trading loop.
        orch.bus.subscribe(KillSwitchEvent, always_broken)

        orch.trigger_kill_switch(reason="test-trip", source="unit-test")

        assert calls["n"] == 3  # bounded retry: 3 attempts, all failed
        assert orch.bus.handler_errors == 3
        assert orch.trading_loop.get_stats()["kill_switch_active"] is True

    def test_reset_does_not_publish_event(self):
        """Reset goes through StateCoordinator directly, not via EventBus.
        This means a broken subscriber cannot prevent the trading loop from
        being reset — the coordinator calls trading_loop.reset_kill_switch()
        synchronously. This is the correct behavior: reset is a safe operation
        that should always succeed (unlike activate, which needs fail-closed
        retry)."""
        orch = _make_orchestrator()
        orch.bus.subscribe(KillSwitchEvent, orch.trading_loop.on_kill_switch)

        orch.trigger_kill_switch(reason="test-trip", source="unit-test")
        assert orch.trading_loop.get_stats()["kill_switch_active"] is True

        # Replace with broken handler — reset should still work because
        # it goes through coordinator, not the bus.
        orch.bus.unsubscribe(KillSwitchEvent, orch.trading_loop.on_kill_switch)

        def always_broken(event):
            raise RuntimeError("simulated subscriber crash")

        orch.bus.subscribe(KillSwitchEvent, always_broken)

        orch.reset_kill_switch(reason="test-reset", authorized_by="unit-test")

        # Reset succeeds because coordinator calls trading_loop directly
        assert orch.trading_loop.get_stats()["kill_switch_active"] is False

    def test_transient_handler_failure_recovers_within_retry_budget(self):
        """A handler that fails once then succeeds should be delivered
        within the retry budget, without needing the fallback path."""
        orch = _make_orchestrator()
        calls = {"n": 0}

        def flaky_then_ok(event):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient failure")

        orch.bus.subscribe(KillSwitchEvent, flaky_then_ok)

        orch.trigger_kill_switch(reason="test-trip", source="unit-test")

        assert calls["n"] == 2  # 1 failed attempt, 1 successful retry
        assert orch.bus.handler_errors == 1


class TestStateCoordinatorWiring:
    """Verify StateCoordinator syncs kill switch across all stores."""

    def test_coordinator_is_wired(self):
        """Orchestrator creates and exposes a StateCoordinator."""
        orch = _make_orchestrator()
        assert orch.coordinator is not None
        assert orch.coordinator._kill_switch is orch.kill_switch
        assert orch.coordinator._trading_loop is orch.trading_loop

    def test_kill_switch_has_coordinator(self):
        """KillSwitch.set_coordinator was called with the orchestrator's coordinator."""
        orch = _make_orchestrator()
        assert orch.kill_switch._coordinator is orch.coordinator

    def test_trigger_activates_coordinator(self):
        """trigger_kill_switch routes through StateCoordinator.activate()."""
        orch = _make_orchestrator()
        orch.bus.subscribe(KillSwitchEvent, orch.trading_loop.on_kill_switch)

        orch.trigger_kill_switch(reason="coordinator-test", source="unit-test")

        # KillSwitch is active
        assert orch.kill_switch.is_active()
        # TradingLoop received the event
        assert orch.trading_loop.get_stats()["kill_switch_active"] is True
        # SystemState synced
        assert orch.coordinator._state_store.kill_switch_active is True
        assert orch.coordinator._state_store.system_state == "HALTED"
        # RiskLedger synced
        assert orch.coordinator._risk_ledger._state["kill_switch_state"] == "active"

    def test_reset_deactivates_coordinator(self):
        """reset_kill_switch routes through StateCoordinator.deactivate()."""
        orch = _make_orchestrator()
        orch.bus.subscribe(KillSwitchEvent, orch.trading_loop.on_kill_switch)

        orch.trigger_kill_switch(reason="test", source="unit-test")
        assert orch.kill_switch.is_active()

        orch.reset_kill_switch(reason="resume-test", authorized_by="unit-test")

        assert not orch.kill_switch.is_active()
        assert orch.trading_loop.get_stats()["kill_switch_active"] is False
        assert orch.coordinator._state_store.kill_switch_active is False
        assert orch.coordinator._state_store.system_state == "RUNNING"
        assert orch.coordinator._risk_ledger._state["kill_switch_state"] == "inactive"
