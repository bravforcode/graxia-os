"""Strategy Runner — runs strategies and collects signals.

Extracted from TradingOrchestrator to follow Single Responsibility Principle.
"""

from __future__ import annotations

import logging

from ..agents.risk_auditor import RiskAuditorAgent
from ..event_bus import EventBus
from ..events import Event, SignalEvent

logger = logging.getLogger(__name__)


class StrategyRunner:
    """Run strategies and collect signals through the two-phase protocol.

    Phase 1 (observe): Agents receive raw events
    Phase 2 (act):     Agents produce output events
    """

    def __init__(self, bus: EventBus, risk_auditor: RiskAuditorAgent) -> None:
        self._bus = bus
        self._risk_auditor = risk_auditor

    def observe(self, event: SignalEvent) -> None:
        """Phase 1: Pass signal to risk auditor for observation."""
        self._risk_auditor.observe(event)

    def act(self) -> Event | None:
        """Phase 2: Risk auditor produces risk-adjusted signal."""
        return self._risk_auditor.act()
