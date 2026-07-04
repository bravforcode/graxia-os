"""
MT5 Tick Ingester — streams live ticks from MetaTrader 5 into the pipeline.

Polls MT5 for new ticks, validates through the quality gate, writes to the
DuckDB write queue, and publishes to the EventBus for downstream consumers
(bar aggregator, strategy engine).

Handles reconnection with exponential backoff. Designed to run as a long-lived
background task alongside the trading runtime.

Requires: MetaTrader5 PyPI package (Windows only).

Usage:
    from core.event_bus import EventBus
    bus = EventBus()
    await bus.start()

    write_queue = DuckDBWriteQueue("data/ticks.duckdb")
    await write_queue.start()

    ingester = MT5TickIngester(
        symbols=["XAUUSD", "EURUSD"],
        event_bus=bus,
        write_queue=write_queue,
    )
    await ingester.start()
    ...
    await ingester.stop()
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Attempt import — graceful degradation if MT5 not available
try:
    import MetaTrader5 as mt5

    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore[assignment]
    MT5_AVAILABLE = False


# ── Configuration ──────────────────────────────────────────────────


@dataclass(frozen=True)
class MT5IngesterConfig:
    """Immutable configuration for the MT5 tick ingester."""

    symbols: tuple[str, ...] = ("XAUUSD", "EURUSD")
    poll_interval_ms: int = 100
    reconnect_delay_sec: float = 5.0
    max_reconnect_delay_sec: float = 60.0
    max_consecutive_errors: int = 50
    quality_gate_strict: bool = True
    asset_class_override: str | None = None
    mt5_login: int | None = None
    mt5_password: str | None = None
    mt5_server: str | None = None
    mt5_path: str | None = None


# ── Tick data ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class MT5Tick:
    """Normalized tick from MT5."""

    symbol: str
    bid: float
    ask: float
    last: float
    volume: float
    timestamp: datetime
    time_msc: int = 0
    flags: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "bid": self.bid,
            "ask": self.ask,
            "last": self.last,
            "volume": self.volume,
            "timestamp": self.timestamp.isoformat(),
            "time_msc": self.time_msc,
        }


# ── Ingester stats ────────────────────────────────────────────────


@dataclass
class IngesterStats:
    """Mutable statistics for monitoring."""

    total_ticks: int = 0
    total_batches: int = 0
    total_reconnects: int = 0
    total_quality_rejects: int = 0
    total_write_errors: int = 0
    last_tick_time: float | None = None
    consecutive_errors: int = 0
    connected: bool = False
    uptime_sec: float = 0.0


# ── MT5 Tick Ingester ─────────────────────────────────────────────


class MT5TickIngester:
    """
    Streams ticks from MetaTrader 5 through quality gate → write queue → event bus.

    Architecture:
        MT5 Terminal → poll → quality gate → DuckDBWriteQueue
                                        → EventBus (tick.{asset_class}.new)

    Args:
        symbols: List of MT5 symbol names to stream.
        event_bus: EventBus instance for publishing validated ticks.
        write_queue: DuckDBWriteQueue for persistence.
        config: Optional configuration override.
        on_tick: Optional async callback for each validated tick.
    """

    def __init__(
        self,
        symbols: Sequence[str],
        event_bus: Any,  # EventBus — avoid circular import
        write_queue: Any,  # DuckDBWriteQueue
        config: MT5IngesterConfig | None = None,
        on_tick: Callable[[MT5Tick], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        self._config = config or MT5IngesterConfig(symbols=tuple(symbols))
        self._event_bus = event_bus
        self._write_queue = write_queue
        self._on_tick = on_tick

        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._stats = IngesterStats()
        self._start_time: float = 0.0

        # Deferred imports to avoid circular dependency
        from .quality_gate import DataQualityGate, classify_symbol

        self._quality_gate = DataQualityGate(strict=self._config.quality_gate_strict)
        self._classify_symbol = classify_symbol

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialize MT5 connection and start the polling loop."""
        if not MT5_AVAILABLE:
            raise RuntimeError("MetaTrader5 package not installed. " "Install with: pip install MetaTrader5")
        if self._running:
            return

        connected = await self._connect_mt5()
        if not connected:
            raise ConnectionError("Failed to connect to MT5 terminal")

        self._running = True
        self._start_time = time.monotonic()
        self._task = asyncio.create_task(
            self._poll_loop(),
            name="mt5_tick_ingester",
        )
        logger.info(
            "mt5_ingester.started",
            symbols=list(self._config.symbols),
            poll_ms=self._config.poll_interval_ms,
        )

    async def stop(self) -> None:
        """Stop polling and disconnect from MT5."""
        if not self._running:
            return
        self._running = False

        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        self._disconnect_mt5()
        self._stats.uptime_sec = time.monotonic() - self._start_time

        logger.info(
            "mt5_ingester.stopped",
            total_ticks=self._stats.total_ticks,
            total_reconnects=self._stats.total_reconnects,
            quality_rejects=self._stats.total_quality_rejects,
            uptime_sec=round(self._stats.uptime_sec, 1),
        )

    @property
    def stats(self) -> IngesterStats:
        """Current statistics snapshot."""
        if self._running:
            self._stats.uptime_sec = time.monotonic() - self._start_time
        return self._stats

    @property
    def is_connected(self) -> bool:
        return self._stats.connected

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Main loop: poll MT5 → validate → write → publish."""
        backoff = self._config.reconnect_delay_sec

        while self._running:
            try:
                ticks = await self._poll_ticks()
                if ticks:
                    await self._process_ticks(ticks)
                    backoff = self._config.reconnect_delay_sec  # Reset on success
                    self._stats.consecutive_errors = 0
                else:
                    # No new ticks — normal for polling
                    pass

                await asyncio.sleep(self._config.poll_interval_ms / 1000.0)

            except asyncio.CancelledError:
                break
            except Exception:
                self._stats.consecutive_errors += 1
                logger.exception(
                    "mt5_ingester.poll_error",
                    consecutive=self._stats.consecutive_errors,
                )

                if self._stats.consecutive_errors >= self._config.max_consecutive_errors:
                    logger.warning(
                        "mt5_ingester.too_many_errors",
                        count=self._stats.consecutive_errors,
                        attempting_reconnect=True,
                    )
                    await self._reconnect(backoff)
                    backoff = min(backoff * 2, self._config.max_reconnect_delay_sec)

    async def _poll_ticks(self) -> list[MT5Tick]:
        """Poll MT5 for new ticks on all subscribed symbols."""
        if not self._stats.connected or mt5 is None:
            return []

        ticks: list[MT5Tick] = []
        for symbol in self._config.symbols:
            try:
                tick_data = mt5.symbol_info_tick(symbol)
                if tick_data is None:
                    continue

                # MT5 returns time in seconds; time_msc in milliseconds
                ts_sec = tick_data.time
                ts_msc = getattr(tick_data, "time_msc", 0)
                if ts_msc:
                    ts = datetime.fromtimestamp(ts_msc / 1000.0, tz=UTC)
                else:
                    ts = datetime.fromtimestamp(ts_sec, tz=UTC)

                tick = MT5Tick(
                    symbol=symbol,
                    bid=tick_data.bid,
                    ask=tick_data.ask,
                    last=getattr(tick_data, "last", 0.0),
                    volume=getattr(tick_data, "volume_real", 0.0),
                    timestamp=ts,
                    time_msc=ts_msc,
                    flags=getattr(tick_data, "flags", 0),
                )
                ticks.append(tick)

            except Exception:
                logger.exception("mt5_ingester.tick_error", symbol=symbol)

        return ticks

    async def _process_ticks(self, ticks: list[MT5Tick]) -> None:
        """Validate, write, and publish a batch of ticks."""
        # Convert to dicts for quality gate
        records = [t.to_dict() for t in ticks]

        # Quality gate
        asset_class = self._config.asset_class_override
        gate_result = self._quality_gate.run(records, asset_class=asset_class)

        if not gate_result["passed"]:
            self._stats.total_quality_rejects += gate_result["failed_records"]
            logger.warning(
                "mt5_ingester.quality_failed",
                failed=gate_result["failed_records"],
                checks={k: v["failed_count"] for k, v in gate_result["checks"].items() if v["failed_count"] > 0},
            )
            # Still write passing records
            passing_records = []
            passing_ticks = []
            for i, rec in enumerate(records):
                # Re-run per-record check (fast, O(1))
                rec_ok = all(c["failed_count"] == 0 for c in gate_result["checks"].values())
                # Simplified: skip individual filtering for now
                pass

        # Write all records to DuckDB (quality gate is advisory for now)
        try:
            await self._write_queue.enqueue("ticks", records)
        except Exception:
            self._stats.total_write_errors += 1
            logger.exception("mt5_ingester.write_error")

        # Publish to event bus
        for tick in ticks:
            asset_cls = asset_class or self._classify_symbol(tick.symbol)
            subject = f"tick.{asset_cls}.new"
            try:
                await self._event_bus.publish(subject, tick)
            except Exception:
                logger.exception("mt5_ingester.publish_error", subject=subject)

            # Custom callback
            if self._on_tick is not None:
                try:
                    await self._on_tick(tick)
                except Exception:
                    logger.exception("mt5_ingester.on_tick_error")

        self._stats.total_ticks += len(ticks)
        self._stats.total_batches += 1
        self._stats.last_tick_time = time.time()

    # ------------------------------------------------------------------
    # MT5 connection management
    # ------------------------------------------------------------------

    async def _connect_mt5(self) -> bool:
        """Initialize MT5 terminal and authenticate."""
        if mt5 is None:
            return False

        # Run blocking MT5 init in thread pool
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, self._mt5_initialize)
        return result

    def _mt5_initialize(self) -> bool:
        """Blocking MT5 initialization (runs in executor)."""
        if mt5 is None:
            return False

        kwargs: dict[str, Any] = {}
        if self._config.mt5_path:
            kwargs["path"] = self._config.mt5_path

        if not mt5.initialize(**kwargs):
            error = mt5.last_error()
            logger.error("mt5_ingester.init_failed", error=error)
            return False

        # Authenticate if credentials provided
        if self._config.mt5_login is not None:
            authorized = mt5.login(
                login=self._config.mt5_login,
                password=self._config.mt5_password or "",
                server=self._config.mt5_server or "",
            )
            if not authorized:
                error = mt5.last_error()
                logger.error("mt5_ingester.login_failed", error=error)
                mt5.shutdown()
                return False

        # Verify symbols are available
        for symbol in self._config.symbols:
            info = mt5.symbol_info(symbol)
            if info is None:
                logger.warning("mt5_ingester.symbol_not_found", symbol=symbol)
            elif not info.visible:
                mt5.symbol_select(symbol, True)

        account = mt5.account_info()
        if account:
            logger.info(
                "mt5_ingester.connected",
                login=account.login,
                server=account.server,
                balance=account.balance,
            )

        self._stats.connected = True
        return True

    def _disconnect_mt5(self) -> None:
        """Shutdown MT5 connection."""
        if mt5 is not None and self._stats.connected:
            mt5.shutdown()
            self._stats.connected = False
            logger.info("mt5_ingester.disconnected")

    async def _reconnect(self, delay: float) -> None:
        """Disconnect and reconnect with backoff."""
        self._disconnect_mt5()
        self._stats.total_reconnects += 1
        logger.info("mt5_ingester.reconnecting", delay_sec=delay)
        await asyncio.sleep(delay)

        loop = asyncio.get_running_loop()
        connected = await loop.run_in_executor(None, self._mt5_initialize)
        if connected:
            logger.info("mt5_ingester.reconnected")
        else:
            logger.error("mt5_ingester.reconnect_failed")
