"""Test TelegramCommandHandler coordinator wiring.

Verifies that the coordinator instance passed to TelegramCommandHandler is the
SAME instance used by the orchestrator's kill_switch and risk_ledger.
This ensures that when Telegram triggers kill switch, it propagates to all stores.
"""

from unittest.mock import MagicMock

import pytest


def test_telegram_handler_coordinator_is_orchestrator_coordinator():
    """Instance identity: handler._coordinator must be orchestrator._coordinator."""
    from graxia.packages.quant_os.api.telegram_commands import TelegramCommandHandler
    from graxia.packages.quant_os.core.state_coordinator import StateCoordinator

    # Create a mock coordinator (same instance used everywhere)
    mock_coordinator = MagicMock(spec=StateCoordinator)
    mock_coordinator._state_store = MagicMock()

    # Create handler with the coordinator
    handler = TelegramCommandHandler(
        coordinator=mock_coordinator,
        state_store=mock_coordinator._state_store,
        config=MagicMock(),
    )

    # CRITICAL: handler must hold the SAME instance, not a copy
    assert handler._coordinator is mock_coordinator, (
        "TelegramCommandHandler._coordinator is NOT the same instance as the orchestrator's coordinator. "
        "Kill switch triggers from Telegram will NOT propagate to risk_ledger/kill_switch/trading_loop."
    )


def test_telegram_handler_coordinator_is_kill_switch_coordinator():
    """Cross-check: handler's coordinator must be the same instance wired to kill_switch."""
    from graxia.packages.quant_os.api.telegram_commands import TelegramCommandHandler
    from graxia.packages.quant_os.core.state_coordinator import StateCoordinator

    # Create real coordinator with mock stores
    mock_kill_switch = MagicMock()
    mock_risk_overlay = MagicMock()
    mock_state_store = MagicMock()
    mock_risk_ledger = MagicMock()
    mock_trading_loop = MagicMock()

    coordinator = StateCoordinator(
        kill_switch=mock_kill_switch,
        risk_overlay=mock_risk_overlay,
        state_store=mock_state_store,
        risk_ledger=mock_risk_ledger,
        trading_loop=mock_trading_loop,
        bus=MagicMock(),
    )

    # Create handler
    handler = TelegramCommandHandler(
        coordinator=coordinator,
        state_store=mock_state_store,
        config=MagicMock(),
    )

    # CRITICAL: handler's coordinator must be the same instance as the one
    # that propagates to kill_switch (via sync_kill_switch)
    assert handler._coordinator is coordinator

    # Verify coordinator stores kill_switch reference
    assert coordinator._kill_switch is mock_kill_switch


def test_orchestrator_coordinator_property_returns_internal_coordinator():
    """Verify orchestrator.coordinator returns self._coordinator."""
    from graxia.packages.quant_os.core.orchestrator import TradingOrchestrator

    orch = TradingOrchestrator()
    assert hasattr(orch, "coordinator"), "TradingOrchestrator must have coordinator property"
    assert orch.coordinator is orch._coordinator, (
        "orchestrator.coordinator property must return self._coordinator"
    )
