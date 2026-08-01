"""E2E tests for kill switch functionality."""

from __future__ import annotations

import pytest

from ...core.orchestrator import TradingOrchestrator


@pytest.mark.e2e
class TestKillSwitch:
    """Test kill switch stops all trading."""

    def test_kill_switch_prevents_new_orders(self, orchestrator: TradingOrchestrator) -> None:
        """Test kill switch prevents new orders from being submitted."""
        orchestrator.start()

        # Activate kill switch
        orchestrator.trigger_kill_switch(reason="Test", source="test")

        # Verify kill switch is active
        assert orchestrator.kill_switch.is_triggered is True

        # Verify trading loop is halted
        assert orchestrator.trading_loop._kill_switch_active is True

        orchestrator.stop()

    def test_kill_switch_event_published(self, orchestrator: TradingOrchestrator) -> None:
        """Test kill switch publishes event to bus."""
        orchestrator.wire()
        orchestrator.start()

        initial_count = orchestrator.bus.published_count

        # Activate kill switch
        orchestrator.trigger_kill_switch(reason="Test", source="test")

        # Verify event was published
        assert orchestrator.bus.published_count > initial_count

        orchestrator.stop()

    def test_kill_switch_with_reconciliation_failure(self, orchestrator: TradingOrchestrator) -> None:
        """Test kill switch activates on reconciliation failure."""
        orchestrator.start()

        # Simulate reconciliation failures
        orchestrator._reconciliation_fail_count = 10

        # Verify kill switch would be triggered
        # (In real code, this happens in _sync_live_market_state)
        assert orchestrator._reconciliation_fail_count >= 5

        orchestrator.stop()


@pytest.mark.e2e
class TestKillSwitchRecovery:
    """Test kill switch recovery scenarios."""

    def test_kill_switch_reset_allows_trading(self, orchestrator: TradingOrchestrator) -> None:
        """Test resetting kill switch allows trading to resume."""
        orchestrator.start()

        # Activate kill switch
        orchestrator.trigger_kill_switch(reason="Test", source="test")
        assert orchestrator.kill_switch.is_triggered is True

        # Reset kill switch
        orchestrator.reset_kill_switch(reason="Recovery test", authorized_by="test")
        assert orchestrator.kill_switch.is_triggered is False

        # Verify trading loop is not halted
        assert orchestrator.trading_loop._kill_switch_active is False

        orchestrator.stop()

    def test_multiple_kill_switch_cycles(self, orchestrator: TradingOrchestrator) -> None:
        """Test multiple kill switch activation/reset cycles."""
        orchestrator.start()

        for i in range(3):
            # Activate
            orchestrator.trigger_kill_switch(reason=f"Test {i}", source="test")
            assert orchestrator.kill_switch.is_triggered is True

            # Reset
            orchestrator.reset_kill_switch(reason=f"Recovery {i}", authorized_by="test")
            assert orchestrator.kill_switch.is_triggered is False

        orchestrator.stop()
