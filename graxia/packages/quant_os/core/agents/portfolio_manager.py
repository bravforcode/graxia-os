"""
PortfolioManagerAgent (C1)

Final signal assembly. Receives consensus from researcher and risk approval
from auditor, then emits the final SignalEvent for execution.
"""

from dataclasses import dataclass

from ..enums import SignalType
from ..events import Event, RiskEvent, SignalEvent
from .base import Agent


@dataclass
class PositionState:
    """Tracks current exposure per symbol."""

    symbol: str = ""
    side: SignalType = SignalType.NO_TRADE
    quantity: float = 0.0


class PortfolioManagerAgent(Agent):
    """
    Final signal assembly agent.

    Rules:
        - Wait for consensus signal from researcher
        - Verify risk approval (RiskEvent with passed=True)
        - Apply position limits: max 1 position per symbol
        - Emit final SignalEvent with risk-adjusted confidence
    """

    MAX_POSITIONS = 5

    def __init__(self, name: str = "portfolio_manager") -> None:
        super().__init__(name)
        self._positions: dict[str, PositionState] = {}
        self._pending_consensus: SignalEvent | None = None
        self._pending_risk_pass: bool = False
        self._final_signals: list[SignalEvent] = []

    def observe(self, event: Event) -> None:
        if isinstance(event, SignalEvent) and event.source == "bull_bear_researcher":
            self._pending_consensus = event
        elif isinstance(event, RiskEvent):
            self._pending_risk_pass = event.passed

    def act(self) -> Event | None:
        consensus = self._pending_consensus
        if consensus is None:
            return None

        # Reset after processing
        self._pending_consensus = None
        risk_ok = self._pending_risk_pass
        self._pending_risk_pass = False

        if not risk_ok:
            return None

        sym = consensus.symbol

        # Position limit check
        active_count = sum(1 for p in self._positions.values() if p.quantity > 0)
        if active_count >= self.MAX_POSITIONS and sym not in self._positions:
            return None

        # Reduce confidence slightly for portfolio risk
        adjusted_conf = round(consensus.confidence * 0.9, 4)

        final = SignalEvent(
            symbol=sym,
            signal_type=consensus.signal_type,
            confidence=adjusted_conf,
            entry_price=consensus.entry_price,
            stop_loss=consensus.stop_loss,
            take_profit=consensus.take_profit,
            source=self.name,
            metadata={
                "final": True,
                "original_confidence": consensus.confidence,
                "position_limit_applied": active_count >= self.MAX_POSITIONS,
            },
        )
        self._final_signals.append(final)
        return final

    def get_positions(self) -> dict[str, PositionState]:
        return dict(self._positions)

    def reset(self) -> None:
        super().reset()
        self._positions.clear()
        self._pending_consensus = None
        self._pending_risk_pass = False
        self._final_signals.clear()
