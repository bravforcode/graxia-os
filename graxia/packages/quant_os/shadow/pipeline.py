from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
import hashlib
import json

class ShadowSignalOutcome(Enum):
    ACCEPTED = "accepted"
    REJECTED_EVENT_BLOCK = "rejected_event_block"
    REJECTED_MARKET_HEALTH = "rejected_market_health"
    REJECTED_RISK = "rejected_risk"
    REJECTED_DATA_STALE = "rejected_data_stale"
    REJECTED_INVALID_SL = "rejected_invalid_sl"
    REJECTED_DUPLICATE = "rejected_duplicate"

@dataclass
class ShadowSignal:
    signal_id: str
    timestamp: datetime
    symbol: str
    direction: str  # "BUY" or "SELL"
    entry_price: float
    stop_loss: float
    take_profit: Optional[float]
    outcome: ShadowSignalOutcome
    rejection_reason: str = ""
    event_risk_state: str = "CLEAR"
    market_health_state: str = "HEALTHY"
    sized_volume: float = 0.0
    hypothetical_fill_price: float = 0.0
    hypothetical_spread_cost: float = 0.0
    hypothetical_slippage_cost: float = 0.0

    def to_dict(self) -> dict:
        return {
            "signal_id": self.signal_id,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "outcome": self.outcome.value,
            "rejection_reason": self.rejection_reason,
            "event_risk_state": self.event_risk_state,
            "market_health_state": self.market_health_state,
            "sized_volume": self.sized_volume,
            "hypothetical_fill_price": self.hypothetical_fill_price,
            "hypothetical_spread_cost": self.hypothetical_spread_cost,
            "hypothetical_slippage_cost": self.hypothetical_slippage_cost,
        }

    def fingerprint(self) -> str:
        data = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()

@dataclass
class ShadowSession:
    session_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    signals: list[ShadowSignal] = field(default_factory=list)

    def add_signal(self, signal: ShadowSignal) -> None:
        self.signals.append(signal)

    def summary(self) -> dict:
        total = len(self.signals)
        accepted = sum(1 for s in self.signals if s.outcome == ShadowSignalOutcome.ACCEPTED)
        rejected = total - accepted
        return {
            "session_id": self.session_id,
            "total_signals": total,
            "accepted": accepted,
            "rejected": rejected,
            "acceptance_rate": accepted / total if total > 0 else 0,
        }

    def export(self) -> str:
        return json.dumps({
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "signals": [s.to_dict() for s in self.signals],
        }, indent=2)

class ShadowPipeline:
    """Shadow trading pipeline — no order submission, no execution function imports."""

    def __init__(self):
        self._sessions: dict[str, ShadowSession] = {}
        self._current_session: Optional[ShadowSession] = None

    def start_session(self, session_id: str) -> ShadowSession:
        session = ShadowSession(
            session_id=session_id,
            started_at=datetime.utcnow(),
        )
        self._sessions[session_id] = session
        self._current_session = session
        return session

    def end_session(self) -> None:
        if self._current_session:
            self._current_session.ended_at = datetime.utcnow()
            self._current_session = None

    def process_signal(self, signal: ShadowSignal) -> ShadowSignal:
        """Process a signal through shadow pipeline. Never submits to broker."""
        if self._current_session is None:
            raise ValueError("No active session")

        # Block 1: Stale data
        if signal.outcome == ShadowSignalOutcome.REJECTED_DATA_STALE:
            self._current_session.add_signal(signal)
            return signal

        # Block 2: Event risk
        if signal.event_risk_state != "CLEAR":
            signal.outcome = ShadowSignalOutcome.REJECTED_EVENT_BLOCK
            signal.rejection_reason = f"EVENT_BLOCK:{signal.event_risk_state}"
            self._current_session.add_signal(signal)
            return signal

        # Block 3: Market health
        if signal.market_health_state != "HEALTHY":
            signal.outcome = ShadowSignalOutcome.REJECTED_MARKET_HEALTH
            signal.rejection_reason = f"MARKET_UNHEALTHY:{signal.market_health_state}"
            self._current_session.add_signal(signal)
            return signal

        # Block 4: Invalid SL
        if signal.stop_loss <= 0:
            signal.outcome = ShadowSignalOutcome.REJECTED_INVALID_SL
            signal.rejection_reason = "INVALID_SL"
            self._current_session.add_signal(signal)
            return signal

        # Signal accepted (shadow only — no order submitted)
        signal.outcome = ShadowSignalOutcome.ACCEPTED
        self._current_session.add_signal(signal)
        return signal

    def get_session(self, session_id: str) -> Optional[ShadowSession]:
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[ShadowSession]:
        return list(self._sessions.values())
