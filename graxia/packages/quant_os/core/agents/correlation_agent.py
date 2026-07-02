"""
CorrelationAgent — Monitors cross-symbol correlation, adjusts sizing.

Subscribes to BarEvent, feeds prices into CorrelationFilter,
and exposes a position multiplier based on live correlation.

Usage:
    agent = CorrelationAgent()
    bus.subscribe(BarEvent, agent.observe)
    mult = agent.get_adjustment()  # 0.0-1.0

    # Custom symbols:
    agent = CorrelationAgent(symbols=["XAUUSD", "EURUSD", "GBPUSD"])
"""

from __future__ import annotations

from ..correlation import CorrelationFilter
from ..events import BarEvent, Event
from .base import Agent

DEFAULT_SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD"]


class CorrelationAgent(Agent):
    """
    Monitors correlation between tracked symbols and returns a
    position multiplier (1.0 = no concern, 0.0 = block).
    """

    def __init__(
        self,
        name: str = "correlation_agent",
        symbols: list[str] | None = None,
        lookback: int = 100,
        threshold: float = 0.7,
        window: int = 50,
    ) -> None:
        super().__init__(name)
        self.TRACKED_SYMBOLS = tuple(symbols or DEFAULT_SYMBOLS)
        self._filter = CorrelationFilter(
            lookback=lookback,
            high_correlation=threshold,
        )
        self._window = window
        self._open_symbols: list[str] = []

    def observe(self, event: Event) -> None:
        if not isinstance(event, BarEvent):
            return
        if event.symbol in self.TRACKED_SYMBOLS:
            self._filter.update(event.symbol, event.close)

    def set_open_symbols(self, symbols: list[str]) -> None:
        self._open_symbols = symbols
        self._filter.set_open(symbols)

    def get_adjustment(self) -> float:
        """Return position multiplier 0.0-1.0 across all tracked pairs."""
        if not self._open_symbols:
            return 1.0

        worst = 1.0
        for sym in self._open_symbols:
            if sym not in self.TRACKED_SYMBOLS:
                continue
            mult = self._filter.get_multiplier(sym, self._open_symbols)
            worst = min(worst, mult)
        return worst

    def act(self) -> None:
        return None

    def reset(self) -> None:
        super().reset()
        self._filter = CorrelationFilter(
            lookback=self._filter._lookback,
            high_correlation=self._filter._high_correlation,
            very_high_correlation=self._filter._very_high_correlation,
        )
        self._open_symbols = []
