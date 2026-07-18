"""End-to-end kill switch integration test.

Verifies the FULL chain from trigger to all 5 stores + EventBus delivery.
This is the test that was missing from the master status document.
"""

from graxia.packages.quant_os.core.config import QuantConfig
from graxia.packages.quant_os.core.events import KillSwitchEvent
from graxia.packages.quant_os.core.orchestrator import TradingOrchestrator


def _make_orchestrator() -> TradingOrchestrator:
    return TradingOrchestrator(config=QuantConfig())


class TestKillSwitchE2E:
    """Full-chain kill switch: trigger → 5 stores + EventBus."""

    def test_trigger_syncs_all_five_stores(self):
        """trigger_kill_switch must sync KillSwitch, SystemState, RiskOverlay,
        RiskLedger, and deliver to TradingLoop via EventBus."""
        orch = _make_orchestrator()
        orch.bus.subscribe(KillSwitchEvent, orch.trading_loop.on_kill_switch)

        orch.trigger_kill_switch(reason="e2e-test", source="test")

        # Store 1: KillSwitch
        assert orch.kill_switch.is_active(), "KillSwitch not active"

        # Store 2: SystemState
        assert orch.coordinator._state_store.kill_switch_active is True
        assert orch.coordinator._state_store.system_state == "HALTED"

        # Store 3: RiskOverlay
        assert orch.coordinator._risk_overlay.state.kill_switch_triggered is True

        # Store 4: RiskLedger
        assert orch.coordinator._risk_ledger._state["kill_switch_state"] == "active"

        # Store 5: TradingLoop (via EventBus)
        assert orch.trading_loop.get_stats()["kill_switch_active"] is True

    def test_reset_syncs_all_five_stores(self):
        """reset_kill_switch must deactivate all 5 stores."""
        orch = _make_orchestrator()
        orch.bus.subscribe(KillSwitchEvent, orch.trading_loop.on_kill_switch)

        # Activate first
        orch.trigger_kill_switch(reason="e2e-activate", source="test")
        assert orch.kill_switch.is_active()

        # Reset
        orch.reset_kill_switch(reason="e2e-reset", authorized_by="test")

        # All stores must be inactive
        assert not orch.kill_switch.is_active()
        assert orch.coordinator._state_store.kill_switch_active is False
        assert orch.coordinator._state_store.system_state == "RUNNING"
        assert orch.coordinator._risk_overlay.state.kill_switch_triggered is False
        assert orch.coordinator._risk_ledger._state["kill_switch_state"] == "inactive"
        assert orch.trading_loop.get_stats()["kill_switch_active"] is False

    def test_coordinator_activate_syncs_all_stores(self):
        """coordinator.activate() (Telegram path) must sync all stores."""
        orch = _make_orchestrator()
        orch.bus.subscribe(KillSwitchEvent, orch.trading_loop.on_kill_switch)

        orch.coordinator.activate(reason="telegram-e2e", source="telegram:123")

        assert orch.kill_switch.is_active()
        assert orch.coordinator._state_store.kill_switch_active is True
        assert orch.coordinator._risk_overlay.state.kill_switch_triggered is True
        assert orch.coordinator._risk_ledger._state["kill_switch_state"] == "active"
        assert orch.trading_loop.get_stats()["kill_switch_active"] is True

    def test_coordinator_deactivate_syncs_all_stores(self):
        """coordinator.deactivate() (Telegram /resume path) must clear all stores."""
        orch = _make_orchestrator()
        orch.bus.subscribe(KillSwitchEvent, orch.trading_loop.on_kill_switch)

        orch.coordinator.activate(reason="e2e", source="test")
        assert orch.kill_switch.is_active()

        orch.coordinator.deactivate(reason="resume-e2e", source="telegram:123")

        assert not orch.kill_switch.is_active()
        assert orch.coordinator._state_store.kill_switch_active is False
        assert orch.coordinator._risk_overlay.state.kill_switch_triggered is False
        assert orch.coordinator._risk_ledger._state["kill_switch_state"] == "inactive"
        assert orch.trading_loop.get_stats()["kill_switch_active"] is False
