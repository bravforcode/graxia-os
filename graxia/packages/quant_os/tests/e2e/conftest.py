"""Shared fixtures for E2E tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from ...core.config import QuantConfig
from ...core.enums import SignalType
from ...core.event_bus import EventBus
from ...core.events import SignalEvent
from ...core.orchestrator import TradingOrchestrator


@pytest.fixture
def config() -> QuantConfig:
    """Create a test configuration."""
    return QuantConfig(
        trading_mode="paper",
        paper_initial_capital=Decimal("100000"),
    )


@pytest.fixture
def event_bus() -> EventBus:
    """Create an event bus."""
    return EventBus()


@pytest.fixture
def orchestrator(config: QuantConfig) -> TradingOrchestrator:
    """Create a test orchestrator."""
    orch = TradingOrchestrator(config=config)
    return orch


@pytest.fixture
def sample_signal() -> SignalEvent:
    """Create a sample signal event."""
    return SignalEvent(
        symbol="EURUSD",
        signal_type=SignalType.BUY,
        confidence=0.85,
        entry_price=1.0850,
        stop_loss=1.0820,
        take_profit=1.0910,
    )
