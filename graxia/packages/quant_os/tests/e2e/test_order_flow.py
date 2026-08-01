"""E2E tests for order flow lifecycle."""

from __future__ import annotations

import pytest

from ...core.enums import SignalType
from ...core.events import SignalEvent
from ...core.orchestrator import TradingOrchestrator


@pytest.mark.e2e
class TestOrderFlow:
    """Test complete order lifecycle."""

    def test_orchestrator_initialization(self, orchestrator: TradingOrchestrator) -> None:
        """Test orchestrator initializes all components correctly."""
        assert orchestrator is not None
        assert orchestrator.bus is not None
        assert orchestrator.kill_switch is not None
        assert orchestrator.trading_loop is not None
        assert orchestrator.position_manager is not None
        assert orchestrator.strategy_runner is not None
        assert orchestrator.order_processor is not None
        assert orchestrator.portfolio_service is not None

    def test_orchestrator_wiring(self, orchestrator: TradingOrchestrator) -> None:
        """Test orchestrator wires event bus correctly."""
        orchestrator.wire()
        assert orchestrator.bus.subscriber_count() > 0

    def test_orchestrator_lifecycle(self, orchestrator: TradingOrchestrator) -> None:
        """Test orchestrator start/stop lifecycle."""
        orchestrator.start()
        assert orchestrator._running is True

        orchestrator.stop()
        assert orchestrator._running is False

    def test_kill_switch_activation(self, orchestrator: TradingOrchestrator) -> None:
        """Test kill switch stops all trading."""
        orchestrator.start()

        # Activate kill switch
        orchestrator.trigger_kill_switch(reason="Test kill switch", source="test")

        # Verify kill switch is active
        assert orchestrator.kill_switch.is_triggered is True

        orchestrator.stop()

    def test_kill_switch_reset(self, orchestrator: TradingOrchestrator) -> None:
        """Test kill switch can be reset."""
        orchestrator.start()

        # Activate kill switch
        orchestrator.trigger_kill_switch(reason="Test", source="test")
        assert orchestrator.kill_switch.is_triggered is True

        # Reset kill switch
        orchestrator.reset_kill_switch(reason="Test reset", authorized_by="test")
        assert orchestrator.kill_switch.is_triggered is False

        orchestrator.stop()

    def test_status_reporting(self, orchestrator: TradingOrchestrator) -> None:
        """Test orchestrator status reporting."""
        orchestrator.start()
        status = orchestrator.get_status()

        assert "running" in status
        assert "trading_mode" in status
        assert "bus_subscribers" in status
        assert "bus_published" in status
        assert "trading_loop" in status
        assert "open_positions" in status
        assert "total_exposure" in status
        assert "risk_auditor" in status
        assert "portfolio_manager" in status
        assert "portfolio_positions" in status

        orchestrator.stop()


@pytest.mark.e2e
class TestSignalProcessing:
    """Test signal processing through the orchestrator."""

    def test_signal_event_creation(self, sample_signal: SignalEvent) -> None:
        """Test signal event can be created."""
        assert sample_signal.symbol == "EURUSD"
        assert sample_signal.signal_type == SignalType.BUY
        assert sample_signal.confidence == 0.85

    def test_signal_publishing(self, orchestrator: TradingOrchestrator, sample_signal: SignalEvent) -> None:
        """Test signal can be published to event bus."""
        orchestrator.wire()
        orchestrator.start()

        # Publish signal
        orchestrator.bus.publish(sample_signal)

        # Verify signal was published
        assert orchestrator.bus.published_count > 0

        orchestrator.stop()
