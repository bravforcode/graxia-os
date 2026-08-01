"""
Integration tests — E2E kill switch sync + position reconciliation.

Covers:
  - StateCoordinator.activate() syncs all 5 stores
  - StateCoordinator.deactivate() restores all stores
  - PositionReconciler detects drift with mismatched positions
  - PositionReconciler reports no drift with matching positions
  - PositionReconciler auto_close_drift → action=CLOSE_DRIFT
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from graxia.packages.quant_os.core.event_bus import EventBus
from graxia.packages.quant_os.core.state_coordinator import StateCoordinator
from graxia.packages.quant_os.execution.position_reconciler import (
    BrokerPosition,
    InternalPosition,
    PositionReconciler,
    ReconciliationConfig,
)

# ---------------------------------------------------------------------------
# Helpers — mock stores for StateCoordinator
# ---------------------------------------------------------------------------


def _make_mock_kill_switch() -> MagicMock:
    """Mock KillSwitch with activate/deactivate/is_active/is_triggered."""
    ks = MagicMock()
    ks.is_active.return_value = False
    ks.is_triggered = False
    return ks


def _make_mock_state_store() -> MagicMock:
    """Mock SystemState with kill_switch_active attribute."""
    store = MagicMock()
    store.kill_switch_active = False
    store.system_state = "RUNNING"
    return store


def _make_mock_risk_overlay() -> MagicMock:
    """Mock RiskOverlay with state.kill_switch_triggered."""
    overlay = MagicMock()
    overlay.state.kill_switch_triggered = False
    return overlay


def _make_mock_risk_ledger() -> MagicMock:
    """Mock RiskLedger with set_kill_switch_state."""
    ledger = MagicMock()
    return ledger


def _make_mock_trading_loop() -> MagicMock:
    """Mock TradingLoop with reset_kill_switch."""
    loop = MagicMock()
    return loop


def _build_coordinator() -> tuple[StateCoordinator, dict[str, MagicMock]]:
    """Build a StateCoordinator wired to 5 mock stores."""
    stores = {
        "bus": MagicMock(spec=EventBus),
        "state_store": _make_mock_state_store(),
        "kill_switch": _make_mock_kill_switch(),
        "risk_overlay": _make_mock_risk_overlay(),
        "risk_ledger": _make_mock_risk_ledger(),
        "trading_loop": _make_mock_trading_loop(),
    }
    coordinator = StateCoordinator(
        bus=stores["bus"],
        state_store=stores["state_store"],
        kill_switch=stores["kill_switch"],
        risk_overlay=stores["risk_overlay"],
        risk_ledger=stores["risk_ledger"],
        trading_loop=stores["trading_loop"],
    )
    return coordinator, stores


# ---------------------------------------------------------------------------
# E2E: StateCoordinator — activate
# ---------------------------------------------------------------------------


class TestE2EKillSwitchCoordinatorSync:
    """StateCoordinator.activate() must propagate to all 5 stores."""

    def test_activate_syncs_all_stores(self):
        """activate() sets kill switch active on all 5 stores."""
        coordinator, stores = _build_coordinator()

        coordinator.activate(reason="test activate", source="e2e_test")

        # 1. KillSwitch.activate called
        stores["kill_switch"].activate.assert_called_once()
        call_kwargs = stores["kill_switch"].activate.call_args
        assert call_kwargs.kwargs.get("reason") == "test activate" or call_kwargs[1].get("reason") == "test activate"

        # 2. SystemState.kill_switch_active = True
        assert stores["state_store"].kill_switch_active is True
        assert stores["state_store"].system_state == "HALTED"

        # 3. RiskOverlay.trigger_kill_switch called
        stores["risk_overlay"].trigger_kill_switch.assert_called_once()

        # 4. RiskLedger.set_kill_switch_state("active")
        stores["risk_ledger"].set_kill_switch_state.assert_called_once_with("active")

        # NOTE: EventBus event publication is handled by the orchestrator,
        # not the StateCoordinator (to avoid duplicate events and allow
        # the orchestrator's bounded retry + fail-closed fallback).
        # The coordinator only syncs store state.


# ---------------------------------------------------------------------------
# E2E: StateCoordinator — deactivate
# ---------------------------------------------------------------------------


class TestE2EKillSwitchResume:
    """StateCoordinator.deactivate() must restore all 5 stores."""

    def test_deactivate_restores_all_stores(self):
        """deactivate() sets kill switch inactive on all 5 stores."""
        coordinator, stores = _build_coordinator()

        # First activate so stores are in active state
        coordinator.activate(reason="test", source="test")

        # Reset mocks to track only deactivate calls
        for store in stores.values():
            store.reset_mock()

        # Make kill_switch.is_triggered return True for deactivate path
        stores["kill_switch"].is_triggered = True
        stores["risk_overlay"].state.kill_switch_triggered = True

        coordinator.deactivate(reason="resume trading", source="e2e_test")

        # 1. KillSwitch.deactivate called
        stores["kill_switch"].deactivate.assert_called_once()

        # 2. SystemState.kill_switch_active = False
        assert stores["state_store"].kill_switch_active is False
        assert stores["state_store"].system_state == "RUNNING"

        # 3. RiskOverlay.release_kill_switch called
        stores["risk_overlay"].release_kill_switch.assert_called_once()

        # 4. RiskLedger.set_kill_switch_state("inactive")
        stores["risk_ledger"].set_kill_switch_state.assert_called_once_with("inactive")

        # 5. TradingLoop.reset_kill_switch called
        stores["trading_loop"].reset_kill_switch.assert_called_once()


# ---------------------------------------------------------------------------
# E2E: PositionReconciler — drift detection
# ---------------------------------------------------------------------------


class TestE2EReconciliationDrift:
    """PositionReconciler must detect drift between internal and broker."""

    def test_reconciliation_detects_drift(self):
        """Mismatched positions → drift_detected=True."""
        reconciler = PositionReconciler()

        internal = [
            InternalPosition("EURUSD", "LONG", Decimal("0.10"), Decimal("1.0850")),
            InternalPosition("GBPUSD", "SHORT", Decimal("0.05"), Decimal("1.2700")),
        ]
        broker = [
            BrokerPosition("EURUSD", "LONG", Decimal("0.10"), Decimal("1.0850")),
            # GBPUSD missing from broker
        ]

        result = reconciler.reconcile(internal, broker, timestamp=1000.0)

        assert result.drift_detected is True
        assert result.matched is False
        assert len(result.mismatches) == 1
        assert result.mismatches[0]["type"] == "MISSING_FROM_BROKER"
        assert result.mismatches[0]["symbol"] == "GBPUSD"

    def test_reconciliation_no_drift(self):
        """Matching positions → drift_detected=False."""
        reconciler = PositionReconciler()

        internal = [
            InternalPosition("EURUSD", "LONG", Decimal("0.10"), Decimal("1.0850")),
        ]
        broker = [
            BrokerPosition("EURUSD", "LONG", Decimal("0.10"), Decimal("1.0850")),
        ]

        result = reconciler.reconcile(internal, broker, timestamp=1000.0)

        assert result.drift_detected is False
        assert result.matched is True
        assert result.mismatches == []
        assert result.action_required == "NONE"

    def test_reconciliation_auto_close_drift(self):
        """drift with auto_close_drift=True → action=CLOSE_DRIFT."""
        config = ReconciliationConfig(auto_close_drift=True)
        reconciler = PositionReconciler(config=config)

        internal = [
            InternalPosition("XAUUSD", "LONG", Decimal("1.0"), Decimal("2350.0")),
        ]
        broker = [
            BrokerPosition("XAUUSD", "LONG", Decimal("2.0"), Decimal("2350.0")),
        ]

        result = reconciler.reconcile(internal, broker, timestamp=1000.0)

        assert result.drift_detected is True
        assert result.action_required == "CLOSE_DRIFT"


# ---------------------------------------------------------------------------
# E2E: StateCoordinator — re-entrancy guard
# ---------------------------------------------------------------------------


class TestE2ECoordinatorReentrancy:
    """sync_kill_switch must not recurse infinitely."""

    def test_reentrant_call_is_ignored(self):
        """If a store callback triggers sync during propagation, it's a no-op."""
        coordinator, stores = _build_coordinator()

        # Make kill_switch.activate call sync_kill_switch back (re-entrant)
        def side_effect_activate(reason, source="manual"):
            coordinator.sync_kill_switch(True, reason, source, triggering_store="kill_switch")

        stores["kill_switch"].activate.side_effect = side_effect_activate

        # Should not raise or infinite-loop
        coordinator.activate(reason="reentrant test", source="test")

        # activate was called exactly once despite re-entry
        stores["kill_switch"].activate.assert_called_once()
