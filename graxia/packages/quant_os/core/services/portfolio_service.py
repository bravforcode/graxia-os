"""Portfolio Service — manages positions and P&L.

Extracted from TradingOrchestrator to follow Single Responsibility Principle.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from ..agents.portfolio_manager import PortfolioManagerAgent
from ..events import FillEvent, TradeClosedEvent
from ..position_manager import PositionManager

logger = logging.getLogger(__name__)


class PortfolioService:
    """Manage positions and P&L through PositionManager and PortfolioManagerAgent."""

    def __init__(
        self,
        position_manager: PositionManager,
        portfolio_manager: PortfolioManagerAgent,
    ) -> None:
        self._position_manager = position_manager
        self._portfolio_manager = portfolio_manager

    def on_fill(self, event: FillEvent) -> None:
        """Handle fill events."""
        self._position_manager.on_fill(event)

    def on_close(self, event: TradeClosedEvent) -> None:
        """Handle trade closed events."""
        self._position_manager.on_close(event)

    def get_positions(self) -> dict[str, Any]:
        """Return open positions."""
        return self._position_manager.get_positions()

    def get_open_positions_count(self) -> int:
        """Return count of open positions."""
        return self._position_manager.get_open_positions_count()

    def get_total_exposure(self) -> Decimal:
        """Return total portfolio exposure."""
        return Decimal(str(self._position_manager.get_total_exposure()))

    def get_portfolio_positions(self) -> list[Any]:
        """Return portfolio manager positions."""
        return list(self._portfolio_manager.get_positions().values())

    @property
    def portfolio_manager_name(self) -> str:
        """Return portfolio manager agent name."""
        return self._portfolio_manager.name
