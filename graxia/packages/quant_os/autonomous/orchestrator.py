"""Orchestrator — 24/7 main loop for the autonomous trading system.

Ties ChartMonitor → DecisionEngine → OrderExecutor into a continuous
cycle with health monitoring, exponential backoff, and kill-switch
integration.  This is the single entry point for autonomous trading.
"""

from __future__ import annotations

import asyncio
import signal
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog

from ..core.enums import TradingMode
from ..execution.adapters.manager import BrokerManager
from ..risk.circuit_breaker import CircuitBreaker
from ..risk.engine import RiskEngine
from ..risk.kill_switch import KillSwitch
from .chart_monitor import ChartMonitor, ChartSnapshot
from .config import (
    CHART_POLL_SECONDS,
    HEALTH_CHECK_SECONDS,
    LLM_MIN_CONFIDENCE,
    MAX_CONSECUTIVE_ERRORS,
    RESTART_DELAY_SECONDS,
    SYMBOLS,
    TIMEFRAMES,
    TRADING_MODE,
)
from .decision_engine import DecisionEngine
from .news_gate import NewsBlackoutGate
from .notifications import TradeNotifier
from .order_executor import OrderExecutor
from .persistence import TradeStore
from .symbol_registry import SymbolRegistry

logger = structlog.get_logger(__name__)


@dataclass
class SystemHealth:
    """Snapshot of orchestrator health — returned by get_status()."""

    uptime_seconds: float = 0.0
    total_decisions: int = 0
    total_trades: int = 0
    errors: int = 0
    last_snapshot_time: datetime | None = None
    last_trade_time: datetime | None = None
    kill_switch_active: bool = False
    consecutive_errors: int = 0
    is_running: bool = False


class AutonomousOrchestrator:
    """Main entry point for the autonomous trading loop.

    Lifecycle::

        orch = AutonomousOrchestrator()
        await orch.start()   # blocks until stop()
        # or
        await orch.start()   # background; call orch.stop() later
    """

    def __init__(
        self,
        symbols: list[str] | None = None,
        timeframes: list[str] | None = None,
        trading_mode: str | None = None,
        kill_switch: KillSwitch | None = None,
        risk_engine: RiskEngine | None = None,
        decision_engine: DecisionEngine | None = None,
        order_executor: OrderExecutor | None = None,
        chart_monitor: ChartMonitor | None = None,
        notifier: TradeNotifier | None = None,
    ) -> None:
        self._symbols = symbols or SYMBOLS
        self._timeframes = timeframes or TIMEFRAMES
        mode_str = (trading_mode or TRADING_MODE).upper()
        if mode_str == "LIVE":
            mode_str = "LIVE_MICRO"
        self._trading_mode = TradingMode(mode_str)

        self._chart_monitor = chart_monitor or ChartMonitor(
            symbols=self._ymbols,
            timeframes=self._timeframes,
        )
        self._decision_engine = decision_engine or DecisionEngine()
        self._kill_switch = kill_switch or KillSwitch()
        self._circuit_breaker = CircuitBreaker()
        self._news_gate = NewsBlackoutGate()
        self._risk_engine = risk_engine or RiskEngine(
            kill_switch=self._kill_switch,
            circuit_breaker=self._circuit_breaker,
            news_blackout=self._news_gate,
        )
        self._symbol_registry = SymbolRegistry()
        self._notifier = notifier or TradeNotifier()

        if order_executor is not None:
            self._order_executor = order_executor
        else:
            broker_manager = self._create_broker_manager()
            self._order_executor = OrderExecutor(
                broker_manager=broker_manager,
                risk_engine=self._risk_engine,
                kill_switch=self._kill_switch,
                mode=self._trading_mode.value,
                symbol_registry=self._symbol_registry,
            )

        self._health = SystemHealth()
        self._start_time: datetime | None = None
        self._running = False
        self._main_task: asyncio.Task[None] | None = None
        self._health_task: asyncio.Task[None] | None = None
        self._kill_switch_notified: bool = False
        self._last_daily_summary_date: str | None = None
        self._trade_store = TradeStore()

        self._consecutive_errors: dict[str, int] = {
            "chart_monitor": 0,
            "decision_engine": 0,
            "order_executor": 0,
        }

    def _create_broker_manager(self) -> BrokerManager:
        """Build a BrokerManager with the adapter matching the current mode."""
        if self._trading_mode == TradingMode.LIVE_MICRO:
            from ..core.config import get_config
            from ..execution.adapters.mt5 import MT5Adapter

            config = get_config()
            adapter = MT5Adapter(
                login=config.mt5_login,
                password=config.mt5_password,
                server=config.mt5_server,
                timeout=config.mt5_timeout_ms,
            )
            manager = BrokerManager(primary=adapter)
        else:
            from ..execution.adapters.paper import PaperAdapter

            manager = BrokerManager(primary=PaperAdapter())

        return manager

    # -- public api ----------------------------------------------------------

    async def start(self) -> None:
        """Start the full autonomous loop.

        Registers snapshot callbacks, wires signal handlers, and launches
        the main loop and health-check tasks.  Returns immediately so the
        caller can await other work or call stop().
        """
        if self._running:
            logger.warning("orchestrator_already_running")
            return

        self._running = True
        self._start_time = datetime.now(tz=UTC)
        self._health.is_running = True

        self._load_previous_state()
        self._chart_monitor.on_snapshot(self._on_snapshot)

        self._wire_signals()

        await self._chart_monitor.start()

        if hasattr(self._order_executor, "_broker_manager"):
            await self._order_executor._broker_manager.initialize()

        self._main_task = asyncio.create_task(self._main_loop())
        self._health_task = asyncio.create_task(self._health_loop())

        logger.info(
            "orchestrator_started",
            symbols=self._symbols,
            timeframes=self._timeframes,
            trading_mode=self._trading_mode.value,
        )

    async def stop(self) -> None:
        """Gracefully shut down all components."""
        if not self._running:
            return

        logger.info("orchestrator_stopping")
        self._running = False
        self._health.is_running = False

        await self._chart_monitor.stop()

        for task in (self._main_task, self._health_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._main_task = None
        self._health_task = None

        self._save_state()
        logger.info("orchestrator_stopped")

    def get_status(self) -> SystemHealth:
        """Return current system health snapshot."""
        if self._start_time is not None:
            self._health.uptime_seconds = (datetime.now(tz=UTC) - self._start_time).total_seconds()
        self._health.kill_switch_active = self._kill_switch.is_triggered
        return self._health

    # -- main loop -----------------------------------------------------------

    async def _main_loop(self) -> None:
        """Core loop: poll for snapshots that arrived via callback.

        The ChartMonitor pushes snapshots to _on_snapshot; this loop
        only needs to keep the process alive and run periodic tasks.
        """
        while self._running:
            try:
                await asyncio.sleep(CHART_POLL_SECONDS)
            except asyncio.CancelledError:
                return

    async def _on_snapshot(self, snapshot: ChartSnapshot) -> None:
        """Callback invoked by ChartMonitor for every new snapshot."""
        if not self._running:
            return

        self._health.last_snapshot_time = datetime.now(tz=UTC)

        if self._circuit_breaker.is_blocked:
            logger.warning(
                "orchestrator_circuit_breaker_open",
                reason=self._circuit_breaker.reason,
                symbol=snapshot.symbol,
            )
            return

        if self._news_gate.is_blocked():
            logger.warning(
                "orchestrator_news_blackout",
                symbol=snapshot.symbol,
            )
            return

        try:
            decision = await self._decision_engine.analyze(snapshot)
            self._consecutive_errors["decision_engine"] = 0
        except Exception as exc:
            self._handle_error("decision_engine", exc)
            return

        self._health.total_decisions += 1

        self._trade_store.save_decision(
            {
                "symbol": decision.symbol,
                "direction": decision.direction.value,
                "confidence": decision.confidence,
                "entry": decision.entry,
                "sl": decision.stop_loss,
                "tp": decision.take_profit,
                "reasoning": decision.reasoning,
                "red_flags": ",".join(decision.red_flags),
                "timestamp": decision.timestamp.isoformat(),
                "timeframe": decision.timeframe,
                "snapshot_ts": decision.snapshot_ts.isoformat() if decision.snapshot_ts else "",
                "latency_ms": decision.latency_ms,
                "llm_provider": decision.llm_provider,
            }
        )

        if decision.confidence < LLM_MIN_CONFIDENCE:
            logger.debug(
                "orchestrator_low_confidence",
                symbol=snapshot.symbol,
                timeframe=snapshot.timeframe,
                confidence=decision.confidence,
                threshold=LLM_MIN_CONFIDENCE,
            )
            return

        if self._kill_switch.is_triggered:
            logger.warning(
                "orchestrator_kill_switch_blocks_trade",
                symbol=snapshot.symbol,
                reason=self._kill_switch.get_status().get("reason", ""),
            )
            return

        try:
            result = await self._order_executor.execute(decision)
            self._consecutive_errors["order_executor"] = 0
            self._health.total_trades += 1
            self._health.last_trade_time = datetime.now(tz=UTC)
            logger.info(
                "orchestrator_trade_executed",
                symbol=snapshot.symbol,
                timeframe=snapshot.timeframe,
                direction=decision.direction.value,
                confidence=decision.confidence,
                result=result,
            )
            self._trade_store.save_execution(
                {
                    "symbol": decision.symbol,
                    "direction": decision.direction.value,
                    "confidence": decision.confidence,
                    "entry": decision.entry,
                    "stop_loss": decision.stop_loss,
                    "take_profit": decision.take_profit,
                    "success": result.success,
                    "order_id": result.order_id,
                    "broker_order_id": result.broker_order_id,
                    "error": result.error,
                    "approval_required": result.approval_required,
                    "mode": self._trading_mode.value,
                    "timestamp": result.timestamp.isoformat(),
                }
            )
            await self._notifier.notify_trade(decision, result)
        except Exception as exc:
            self._handle_error("order_executor", exc)
            await self._notifier.notify_error("order_executor", str(exc))

    # -- health monitoring ---------------------------------------------------

    async def _health_loop(self) -> None:
        """Periodic health check — logs status and detects stalled components."""
        while self._running:
            try:
                await asyncio.sleep(HEALTH_CHECK_SECONDS)
                self._health_check()
                self._save_health()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.error("orchestrator_health_check_error", error=str(exc))

    def _health_check(self) -> None:
        """Evaluate component health and log warnings for degraded state."""
        status = self.get_status()

        if status.kill_switch_active and not self._kill_switch_notified:
            self._kill_switch_notified = True
            reason = self._kill_switch.get_status().get("reason", "unknown")
            asyncio.create_task(self._notifier.notify_kill_switch(reason))

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        if self._last_daily_summary_date != today:
            self._last_daily_summary_date = today
            stats = self._order_executor.get_daily_stats()
            asyncio.create_task(self._notifier.notify_daily_summary(stats))

        for component, count in self._consecutive_errors.items():
            if count >= MAX_CONSECUTIVE_ERRORS:
                logger.error(
                    "orchestrator_component_degraded",
                    component=component,
                    consecutive_errors=count,
                    max_allowed=MAX_CONSECUTIVE_ERRORS,
                )

        logger.debug(
            "orchestrator_health",
            uptime_seconds=round(status.uptime_seconds, 1),
            total_decisions=status.total_decisions,
            total_trades=status.total_trades,
            errors=status.errors,
            consecutive_errors=dict(self._consecutive_errors),
            kill_switch_active=status.kill_switch_active,
        )

    # -- error handling ------------------------------------------------------

    def _handle_error(self, component: str, error: Exception) -> None:
        """Record error and apply exponential backoff if threshold exceeded."""
        self._health.errors += 1
        self._consecutive_errors[component] = self._consecutive_errors.get(component, 0) + 1
        count = self._consecutive_errors[component]

        logger.error(
            "orchestrator_component_error",
            component=component,
            error=str(error),
            consecutive_errors=count,
        )

        if count >= MAX_CONSECUTIVE_ERRORS:
            backoff = min(RESTART_DELAY_SECONDS * (2 ** (count - MAX_CONSECUTIVE_ERRORS)), 300)
            logger.warning(
                "orchestrator_backoff",
                component=component,
                backoff_seconds=backoff,
            )
            asyncio.create_task(self._notifier.notify_error(component, str(error)))

    # -- signal handling & graceful shutdown ---------------------------------

    def _wire_signals(self) -> None:
        """Register SIGTERM/SIGINT handlers for graceful shutdown."""
        if sys.platform == "win32":
            return

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

    def _save_state(self) -> None:
        """Persist last decisions and positions for crash recovery."""
        self._save_health()
        logger.info(
            "orchestrator_state_saved",
            total_decisions=self._health.total_decisions,
            total_trades=self._health.total_trades,
        )

    def _save_health(self) -> None:
        status = self.get_status()
        self._trade_store.save_health(
            {
                "uptime_seconds": status.uptime_seconds,
                "total_decisions": status.total_decisions,
                "total_trades": status.total_trades,
                "errors": status.errors,
                "kill_switch_active": status.kill_switch_active,
            }
        )

    def _load_previous_state(self) -> None:
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        daily = self._trade_store.get_daily_stats(today)
        if daily.get("trades_today", 0) > 0:
            logger.info(
                "orchestrator_loaded_previous_state",
                date=today,
                trades_today=daily["trades_today"],
                realized_pnl=daily.get("realized_pnl", 0.0),
            )


async def main() -> None:
    """Convenience entry point — creates and starts the orchestrator."""
    orch = AutonomousOrchestrator()
    await orch.start()

    try:
        while orch.get_status().is_running:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await orch.stop()


if __name__ == "__main__":
    asyncio.run(main())
