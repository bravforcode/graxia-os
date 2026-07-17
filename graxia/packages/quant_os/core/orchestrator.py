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
from ..risk.kill_switch import KillSwitch
from ..risk.risk_ledger import RiskLedger
from ..risk.risk_policy import RiskPolicy
from ..regime.risk_overlay import RiskOverlay
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
from .state_coordinator import StateCoordinator
from .state_store import SystemState
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
        self._risk_policy = RiskPolicy()
        self._risk_ledger = RiskLedger()
        self._kill_switch = KillSwitch()
        self._risk_overlay = RiskOverlay(
            initial_balance=self._config.paper_initial_capital,
            max_risk_pct=self._config.max_risk_per_trade_pct / 100,
            max_daily_loss_pct=self._config.max_daily_loss_pct / 100,
            max_weekly_loss_pct=self._config.max_weekly_loss_pct / 100,
        )
        self._state_store = SystemState.default(
            environment=self._config.trading_mode.value,
        )
        self._trading_loop = TradingLoop(
            bus=self._bus,
            oms=self._oms,
            config=self._config,
            paper_executor=self._paper,
            risk_policy=self._risk_policy,
            risk_ledger=self._risk_ledger,
            account_equity=self._config.paper_initial_capital,
        )
        self._coordinator = StateCoordinator(
            bus=self._bus,
            state_store=self._state_store,
            kill_switch=self._kill_switch,
            risk_overlay=self._risk_overlay,
            risk_ledger=self._risk_ledger,
            trading_loop=self._trading_loop,
        )
        self._kill_switch.set_coordinator(self._coordinator)
        self._risk_ledger.set_coordinator(self._coordinator)
        self._risk_overlay.set_coordinator(self._coordinator)
        self._running = False
        self._sync_task: asyncio.Task | None = None
        self._last_heartbeat: float = 0.0

    @property
    def bus(self) -> EventBus:
        return self._bus

    @property
    def coordinator(self) -> StateCoordinator:
        return self._coordinator

    @property
    def kill_switch(self) -> KillSwitch:
        return self._kill_switch

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

    @property
    def risk_ledger(self) -> RiskLedger:
        return self._risk_ledger

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
                self._sync_live_market_state()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("orchestrator.sync_error error=%s", exc)

    def _sync_live_market_state(self) -> None:
        """Sync live market state: account equity + position prices.

        Called periodically by _sync_loop. Queries broker adapter for:
        1. Account equity → TradingLoop + PositionManager
        2. Tick prices for open positions → PositionManager.update_prices()

        Graceful degradation: if broker is disconnected or adapter lacks
        get_tick(), only equity is synced.
        """
        if self._broker_adapter is None or not self._broker_adapter.is_connected:
            return

        # 1. Account equity sync
        try:
            info = self._broker_adapter.get_account_info()
            if info.equity > 0:
                self._trading_loop.update_account_equity(info.equity)
                self._position_manager.sync_account_state(
                    equity=info.equity,
                    balance=getattr(info, "balance", 0.0),
                    margin_level=getattr(info, "margin_level", 0.0),
                )
        except Exception as exc:
            logger.warning("orchestrator.equity_sync_failed error=%s", exc)

        # 2. Price sync for open positions (if adapter supports get_tick)
        if not hasattr(self._broker_adapter, "get_tick"):
            return
        open_positions = list(self._position_manager.get_positions().values())
        if not open_positions:
            return
        prices: dict[str, float] = {}
        for pos in open_positions:
            try:
                tick = self._broker_adapter.get_tick(pos.symbol)
                if tick is not None:
                    # get_tick returns dict with 'bid'/'ask' or similar
                    bid = tick.get("bid") if isinstance(tick, dict) else getattr(tick, "bid", None)
                    if bid is not None and bid > 0:
                        prices[pos.symbol] = bid
            except Exception as exc:
                logger.debug("orchestrator.tick_fetch_failed symbol=%s error=%s", pos.symbol, exc)
        if prices:
            self._position_manager.update_prices(prices)

    # ── Kill Switch Public API ──────────────────────────────────────

    def trigger_kill_switch(self, reason: str, source: str = "unknown") -> None:
        """Activate kill switch with fail-closed retry + direct fallback.

        1. Syncs state to all stores directly (KillSwitch, SystemState, RiskLedger).
        2. Publishes KillSwitchEvent on the bus with bounded retry (3 attempts).
        3. If all bus deliveries fail (handler_errors increment), falls back
           to directly calling trading_loop.on_kill_switch() to ensure halt
           is never skipped.

        Note: State is set directly (not via kill_switch.activate) to avoid
        the coordinator cascade that would re-publish on the bus and break
        the bounded-retry counting.
        """
        from ..risk.kill_switch import KillSwitchState

        MAX_RETRIES = 3
        event = KillSwitchEvent(trigger=source, reason=reason, source="orchestrator")

        # 1. Sync state directly to all stores (no cascade, no bus re-publish)
        self._kill_switch._set_state(KillSwitchState.ACTIVE, reason=reason, authorized_by=source)
        self._state_store.kill_switch_active = True
        self._state_store.system_state = "HALTED"
        if self._risk_ledger is not None and hasattr(self._risk_ledger, "_state"):
            # Set directly to avoid coordinator cascade that re-publishes on bus
            self._risk_ledger._state["kill_switch_state"] = "active"
            if hasattr(self._risk_ledger, "_save"):
                self._risk_ledger._save()

        # 2. Publish on bus with bounded retry + direct fallback
        for attempt in range(1, MAX_RETRIES + 1):
            errors_before = self._bus.handler_errors
            self._bus.publish(event)
            if self._bus.handler_errors == errors_before:
                return

        # All bus attempts failed — direct synchronous fallback
        logger.warning(
            "orchestrator.kill_switch_fallback reason=%s attempts=%d",
            reason,
            MAX_RETRIES,
        )
        self._trading_loop.on_kill_switch(event)

    def reset_kill_switch(self, reason: str, authorized_by: str = "unknown") -> None:
        """Deactivate kill switch via StateCoordinator.

        Reset is a safe operation that always succeeds — it goes through
        the coordinator directly, not the EventBus. A broken subscriber
        cannot prevent the system from resuming.
        """
        self._coordinator.deactivate(reason=reason, source=authorized_by)

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
