"""
BullBearResearcherAgent (C1)

Combines opinions from multiple analyst agents and emits a consensus signal.
Rule-based voting: majority direction wins, confidence is averaged.
"""

from dataclasses import dataclass

from ..enums import SignalType
from ..events import Event, SignalEvent
from .base import Agent


@dataclass
class AgentVote:
    """One analyst's vote."""

    agent_name: str
    direction: SignalType
    confidence: float


class BullBearResearcherAgent(Agent):
    """
    Combines opinions from analyst agents via simple voting.

    Rules:
        - Collect votes from named agents
        - If majority direction has >= min_votes, emit consensus
        - Confidence = average confidence of agreeing votes
        - NO_TRADE votes count as abstentions
    """

    MIN_VOTES = 2

    def __init__(self, name: str = "bull_bear_researcher") -> None:
        super().__init__(name)
        self._pending_votes: list[AgentVote] = []
        self._consensus_history: list[SignalEvent] = []

    def observe(self, event: Event) -> None:
        if not isinstance(event, SignalEvent):
            return
        source = event.source
        if not source or source == self.name:
            return
        self._pending_votes.append(
            AgentVote(
                agent_name=source,
                direction=event.signal_type,
                confidence=event.confidence,
            )
        )

    def act(self) -> Event | None:
        if len(self._pending_votes) < self.MIN_VOTES:
            return None

        votes = list(self._pending_votes)
        self._pending_votes.clear()

        # Count directions (excluding NO_TRADE)
        direction_votes: dict[SignalType, list[float]] = {}
        for v in votes:
            if v.direction == SignalType.NO_TRADE:
                continue
            direction_votes.setdefault(v.direction, []).append(v.confidence)

        if not direction_votes:
            return None

        # Majority wins
        best_dir = max(direction_votes, key=lambda d: len(direction_votes[d]))
        agreeing = direction_votes[best_dir]
        avg_conf = sum(agreeing) / len(agreeing)

        # Build consensus from agreeing votes — use metadata from first agreeing vote
        consensus = SignalEvent(
            signal_type=best_dir,
            confidence=round(avg_conf, 4),
            source=self.name,
            metadata={
                "vote_count": len(agreeing),
                "total_votes": len(votes),
                "voters": [v.agent_name for v in votes if v.direction == best_dir],
            },
        )
        self._consensus_history.append(consensus)
        return consensus

    def reset(self) -> None:
        super().reset()
        self._pending_votes.clear()
        self._consensus_history.clear()
