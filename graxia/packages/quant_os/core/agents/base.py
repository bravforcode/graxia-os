"""
Base Agent ABC for multi-agent framework (C1)

All agents follow this interface: observe events, produce actions.
Communication happens exclusively through the EventBus.
"""

from abc import ABC, abstractmethod

from ..events import Event


class Agent(ABC):
    """
    Abstract base agent.

    Lifecycle:
        1. observe(event) — called when relevant events arrive
        2. act() — called to produce an output event (or None)
        3. reset() — clears accumulated state
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._observations: list[Event] = []

    @abstractmethod
    def observe(self, event: Event) -> None:
        """Receive and store relevant event data."""
        ...

    @abstractmethod
    def act(self) -> Event | None:
        """Analyze observations and produce an output event (or None)."""
        ...

    def reset(self) -> None:
        """Clear accumulated observations."""
        self._observations.clear()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r})"
