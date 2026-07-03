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
import time
from typing import Any

from ..execution.adapters.base import BrokerAdapter
from ..execution.adapters.mt5 import MT5Adapter
from ..execution.oms import OMS
from .agents.portfolio_manager import PortfolioManagerAgent
from .agents.risk_auditor import RiskAuditorAgent
from .config import QuantConfig
from .event_bus import EventBus
from .events import (
    FillEvent,
    KillSwitchEvent,
    SignalEvent,
    TradeClosedEvent,
)
from .position_manager import PositionManager
from .trading_loop import PaperExecutor, TradingLoop

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
        self._broker_adapter: BrokerAdapter | None = None
        if self._oms is None and self._config.live_trading_enabled:
            # Create OMS with MT5 adapter for live trading
            self._broker_adapter = MT5Adapter(
                login=self._config.mt5_login,
                password=self._config.mt5_password,
                server=self._config.mt5_server,
            )
            self._oms = OMS(adapters={"mt5": self._broker_adapter})
        elif self._oms is None:
            # Paper mode: OMS not needed (PaperExecutor handles it)
            pass
        self._paper = PaperExecutor()
        self._risk_auditor = RiskAuditorAgent()
        self._portfolio_manager = PortfolioManagerAgent()
        self._position_manager = PositionManager(bus=self._bus)
        self._trading_loop = TradingLoop(
            bus=self._bus,
            oms=self._oms,
            config=self._config,
            paper_executor=self._paper,
        )
        self._running = False
        self._sync_task: asyncio.Task | None = None
        self._last_heartbeat: float = 0.0

    @property
    def bus(self) -> EventBus:
        return self._bus

    @property
    def trading_loop(self) -> TradingLoop:
        return self._trading_loop

    @property
    def position_manager(self) -> PositionManager:
        return self._position_manager

    @property
    def risk_auditor(self) -> RiskAuditorAgent:
        return self._risk_auditor

    @property
    def portfolio_manager(self) -> PortfolioManagerAgent:
        return self._portfolio_manager

    def wire(self) -> None:
        """Wire all EventBus subscriptions and register the two-phase signal processor.

        The agent chain uses a two-phase protocol:
          Phase 1 (observe): Agents receive raw events
          Phase 2 (act):     Agents produce output events

        EventBus only handles Phase 1. The manual processor handles Phase 2.
        """
        # Register the two-phase processor for SignalEvent
        self._bus.subscribe(SignalEvent, self._on_signal_event)

        # TradingLoop subscribes to final signals (published by _on_signal_event)
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

    def _on_signal_event(self, event: Event) -> None:
        """Two-phase signal processor: observe → act → produce final signal.

        This replaces the pure EventBus approach which couldn't handle the
        observe→act lifecycle that RiskAuditor and PortfolioManager require.

        Guard: skip signals that already have final=True (they come from act()).
        """
        if not isinstance(event, SignalEvent):
            return
        # Prevent recursion: skip signals that are already final
        if event.metadata.get("final"):
            return

        # Phase 1: Agents observe the raw signal
        self._risk_auditor.observe(event)
        self._portfolio_manager.observe(event)

        # Phase 2: RiskAuditor produces a verdict
        risk_event = self._risk_auditor.act()
        if risk_event is not None:
            self._portfolio_manager.observe(risk_event)

        # Phase 3: PortfolioManager produces the final signal (with approved_quantity)
        final_signal = self._portfolio_manager.act()
        if final_signal is not None:
            # Publish final signal to EventBus (TradingLoop subscribes)
            self._bus.publish(final_signal)

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
        if self._broker_adapter is not None and self._broker_adapter.is_connected:
            try:
                self._broker_adapter.disconnect()
            except Exception as exc:
                logger.warning("orchestrator.disconnect_error error=%s", exc)
        logger.info("orchestrator.stopped")

    def _beat(self) -> None:
        """Write heartbeat timestamp (called in sync loop)."""
        self._last_heartbeat = time.time()

    async def _sync_loop(self) -> None:
        """Background loop: sync prices and account equity every 5 seconds."""
        while self._running:
            try:
                await asyncio.sleep(5.0)
                self._beat()
                # Price sync: update position unrealized PnL
                # This would connect to MT5 tick feed in production
                # For now, positions track their own entry prices

                # Account equity sync: would call MT5 account_info() in production
                # self._position_manager.sync_account_state(equity, balance, margin_level)
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
            "risk_auditor": self._risk_auditor.name,
            "portfolio_manager": self._portfolio_manager.name,
            "portfolio_positions": len(self._portfolio_manager.get_positions()),
        }
