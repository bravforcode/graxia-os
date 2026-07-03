"""
PortfolioManagerAgent — Hierarchical Veto Protocol (Pillar 3)

Signal flow:
    Initiator (XGBoost/Technical) produces signal
    Modifier (Sentiment/Researcher) adjusts confidence multiplier
    Vetoer (RiskAuditor) can KILL the signal (binary gate)

    Final = Initiator_signal * Sentiment_modifier * Risk_gate

Risk_gate in {0, 1}:
    1 = approved (trade proceeds)
    0 = VETOED (trade is killed, confidence becomes 0)

FAIL-CLOSED: _risk_gate defaults to False. No trade until explicitly approved.
"""

from dataclasses import dataclass

from ..enums import SignalType
from ..events import Event, FillEvent, RiskEvent, SignalEvent
from .base import Agent


@dataclass
class PositionState:
    symbol: str = ""
    side: SignalType = SignalType.NO_TRADE
    quantity: float = 0.0


INITIATOR_SOURCES = ("xgboost", "technical_analyst", "ml_model", "bull_bear_researcher")
MODIFIER_SOURCES = ("sentiment_agent", "bull_bear_researcher")
BLOCKED_SOURCES = ("risk_auditor",)


class PortfolioManagerAgent(Agent):
    """
    Hierarchical Veto Protocol:
    GROUP 1 - INITIATOR: XGBoost + TechnicalAnalyst + Researcher
    GROUP 2 - MODIFIER: Sentiment + Researcher
    GROUP 3 - VETOER: RiskAuditor (ABSOLUTE VETO)

    FAIL-CLOSED: No trade until RiskEvent(passed=True) is received.
    """

    MAX_POSITIONS = 5

    def __init__(self, name: str = "portfolio_manager") -> None:
        super().__init__(name)
        self._positions: dict[str, PositionState] = {}
        self._pending_consensus: SignalEvent | None = None
        self._pending_risk_pass: bool = False
        self._final_signals: list[SignalEvent] = []
        self._sentiment_modifier: float = 1.0
        self._sentiment_source: str = ""
        self._veto_reason: str = ""

    def observe(self, event: Event) -> None:
        if isinstance(event, FillEvent):
            sym = event.symbol
            if sym not in self._positions:
                self._positions[sym] = PositionState(
                    symbol=sym,
                    side=SignalType.BUY if event.side == "BUY" else SignalType.SELL,
                    quantity=event.fill_quantity,
                )
            else:
                self._positions[sym].quantity += event.fill_quantity
            return

        if hasattr(event, "trade_id") and hasattr(event, "pnl"):
            # TradeClosedEvent
            sym = getattr(event, "symbol", "")
            if sym in self._positions:
                self._positions[sym].quantity = 0
            return

        if not isinstance(event, (SignalEvent, RiskEvent)):
            return

        # BLOCK dead signals from risk_auditor
        if isinstance(event, SignalEvent) and event.source in BLOCKED_SOURCES:
            self._pending_risk_pass = False
            self._veto_reason = "dead_signal_from_risk_auditor"
            return

        # GROUP 3 - VETOER
        if isinstance(event, RiskEvent):
            self._pending_risk_pass = event.passed
            if not event.passed:
                self._veto_reason = event.reason
            if event.details:
                verdict = event.details.get("risk_verdict")
                if verdict is not None:
                    self._pending_risk_pass = verdict.is_approved
                    if not verdict.is_approved:
                        self._veto_reason = getattr(verdict, "veto_detail", "") or getattr(
                            verdict.veto_reason, "value", str(verdict.veto_reason)
                        )
            return

        # GROUP 1 - INITIATOR
        if event.source in INITIATOR_SOURCES:
            self._pending_consensus = event

        # GROUP 2 - MODIFIER
        if event.source in MODIFIER_SOURCES:
            if hasattr(event, "metadata") and event.metadata:
                self._sentiment_modifier = event.metadata.get("position_multiplier", 1.0)
            else:
                self._sentiment_modifier = min(event.confidence, 1.0)
            self._sentiment_source = event.source

    def act(self) -> Event | None:
        consensus = self._pending_consensus
        if consensus is None:
            return None

        if not self._pending_risk_pass:
            return None

        sentiment_mod = self._sentiment_modifier
        raw_confidence = consensus.confidence
        final_confidence = raw_confidence * sentiment_mod

        # Position sizing: risk_budget / risk_per_unit
        equity = consensus.metadata.get("equity", 10000.0)
        risk_pct = consensus.metadata.get("risk_pct", 0.01)
        risk_budget = equity * risk_pct
        risk_per_unit = abs(consensus.entry_price - consensus.stop_loss) if consensus.stop_loss else 0
        approved_quantity = round(risk_budget / risk_per_unit, 6) if risk_per_unit > 0 else 0.0

        self._pending_consensus = None
        self._pending_risk_pass = False
        self._sentiment_modifier = 1.0
        self._sentiment_source = ""
        self._veto_reason = ""

        sym = consensus.symbol
        active_count = sum(1 for p in self._positions.values() if p.quantity > 0)
        if active_count >= self.MAX_POSITIONS and sym not in self._positions:
            return None

        final = SignalEvent(
            symbol=sym,
            signal_type=consensus.signal_type,
            confidence=final_confidence,
            entry_price=consensus.entry_price,
            stop_loss=consensus.stop_loss,
            take_profit=consensus.take_profit,
            source=self.name,
            metadata={
                "final": True,
                "hierarchical_veto": True,
                "raw_confidence": raw_confidence,
                "sentiment_modifier": sentiment_mod,
                "risk_gate": 1.0,
                "final_confidence": final_confidence,
                "approved_quantity": approved_quantity,
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
        self._sentiment_modifier = 1.0
        self._sentiment_source = ""
        self._veto_reason = ""
        self._final_signals.clear()
