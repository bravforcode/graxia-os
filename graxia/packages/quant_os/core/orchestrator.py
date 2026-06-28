"""
Trading Orchestrator — wires all components together on startup.

This is the single entry point that connects:
  EventBus → Agents → TradingLoop → OMS → PositionManager

Usage:
    from core.orchestrator import TradingOrchestrator
    orch = TradingOrchestrator(config=config)
    orch.start()
    # ... later ...
    orch.stop()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .event_bus import EventBus
from .events import (
    FillEvent,
    KillSwitchEvent,
    SignalEvent,
    TradeClosedEvent,
)
from .trading_loop import TradingLoop, PaperExecutor
from .position_manager import PositionManager
from .config import QuantConfig

logger = logging.getLogger(__name__)


class TradingOrchestrator:
    """Single entry point that wires all trading components together.

    Lifecycle:
        1. __init__ — creates all components
        2. start()  — wires EventBus subscriptions, starts background tasks
        3. stop()   — graceful shutdown
    """

    def __init__(self, config: QuantConfig | None = None, oms: Any | None = None) -> None:
        self._config = config or QuantConfig()
        self._bus = EventBus()
        self._oms = oms
        self._paper = PaperExecutor()
        self._position_manager = PositionManager(bus=self._bus)
        self._trading_loop = TradingLoop(
            bus=self._bus,
            oms=self._oms,
            config=self._config,
            paper_executor=self._paper,
        )
        self._running = False
        self._sync_task: asyncio.Task | None = None

    @property
    def bus(self) -> EventBus:
        return self._bus

    @property
    def trading_loop(self) -> TradingLoop:
        return self._trading_loop

    @property
    def position_manager(self) -> PositionManager:
        return self._position_manager

    def wire(self) -> None:
        """Wire all EventBus subscriptions. Call once after creating agents."""
        # Signal flow: PortfolioManager → TradingLoop
        self._bus.subscribe(SignalEvent, self._trading_loop.observe)
        # Execution flow: TradingLoop → PositionManager
        self._bus.subscribe(FillEvent, self._position_manager.on_fill)
        self._bus.subscribe(TradeClosedEvent, self._position_manager.on_close)
        # Safety: KillSwitch → TradingLoop
        self._bus.subscribe(KillSwitchEvent, self._trading_loop.on_kill_switch)
        logger.info(
            "orchestrator.wired bus_subscribers=%d",
            self._bus.subscriber_count(),
        )

    def start(self) -> None:
        """Start the orchestrator."""
        self.wire()
        self._running = True
        logger.info("orchestrator.started mode=%s", self._config.trading_mode.value)

    async def start_async(self) -> None:
        """Start with async background tasks (price sync, etc.)."""
        self.start()
        self._sync_task = asyncio.create_task(self._sync_loop())

    def stop(self) -> None:
        """Stop the orchestrator."""
        self._running = False
        if self._sync_task is not None:
            self._sync_task.cancel()
        logger.info("orchestrator.stopped")

    async def _sync_loop(self) -> None:
        """Background loop: sync prices and account equity every 5 seconds."""
        while self._running:
            try:
                await asyncio.sleep(5.0)
                # Price sync would go here (needs broker tick feed)
                # Account equity sync would go here (needs MT5 account_info)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("orchestrator.sync_error error=%s", exc)

    def get_status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "trading_mode": self._config.trading_mode.value,
            "bus_subscribers": self._bus.subscriber_count(),
            "bus_published": self._bus.published_count,
            "trading_loop": self._trading_loop.get_stats(),
            "open_positions": self._position_manager.get_open_positions_count(),
            "total_exposure": self._position_manager.get_total_exposure(),
        }
