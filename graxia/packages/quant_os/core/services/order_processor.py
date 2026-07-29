"""Order Processor — processes orders through risk engine.

Extracted from TradingOrchestrator to follow Single Responsibility Principle.
"""

from __future__ import annotations

import logging
from typing import Any

from ..events import SignalEvent
from ..trading_loop import TradingLoop

logger = logging.getLogger(__name__)


class OrderProcessor:
    """Process orders through the risk engine and trading loop."""

    def __init__(self, trading_loop: TradingLoop) -> None:
        self._trading_loop = trading_loop

    def process_signal(self, signal: SignalEvent) -> dict[str, Any] | None:
        """Process a signal through the trading loop.

        Returns order result dict or None if signal was rejected.
        """
        self._trading_loop.observe(signal)  # type: ignore[func-returns-value]
        return None

    def get_stats(self) -> dict[str, Any]:
        """Return trading loop statistics."""
        return self._trading_loop.get_stats()
