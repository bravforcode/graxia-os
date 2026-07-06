"""Chart Monitor — continuous TradingView data collection for the autonomous loop.

Collects OHLCV bars and optional screenshots for every configured
symbol/timeframe pair, stores snapshots in a ring buffer, and publishes
them to registered callbacks.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from ..api.tv_cdp import TradingViewCDP
from ..api.tv_client import OHLCVBar, TradingViewClient
from .config import (
    CHART_POLL_SECONDS,
    LLM_USE_SCREENSHOT,
    SYMBOLS,
    TIMEFRAMES,
    TV_CDP_ENABLED,
    TV_SCREENSHOT_DIR,
)

logger = structlog.get_logger(__name__)

SnapshotCallback = Callable[["ChartSnapshot"], Coroutine[Any, Any, None] | None]

MAX_SNAPSHOTS = 100


@dataclass(frozen=True)
class ChartSnapshot:
    """Immutable snapshot of chart state for one symbol/timeframe."""

    symbol: str
    timeframe: str
    ohlcv: list[OHLCVBar]
    indicators: dict[str, Any]
    screenshot_path: Path | None
    timestamp: datetime


class ChartMonitor:
    """Async poller that collects TradingView chart data.

    Usage::

        monitor = ChartMonitor()
        monitor.on_snapshot(my_callback)
        await monitor.start()   # blocks until stop()
    """

    def __init__(
        self,
        symbols: list[str] | None = None,
        timeframes: list[str] | None = None,
        poll_seconds: int | None = None,
    ) -> None:
        self._symbols = symbols or SYMBOLS
        self._timeframes = timeframes or TIMEFRAMES
        self._poll_seconds = poll_seconds or CHART_POLL_SECONDS

        self._buffers: dict[str, deque[ChartSnapshot]] = {}
        self._callbacks: list[SnapshotCallback] = []
        self._running = False
        self._task: asyncio.Task[None] | None = None

        self._tv_client: TradingViewClient | None = None
        self._tv_cdp: TradingViewCDP | None = None
        self._cdp_available = False
        self._last_cdp_attempt: float = 0.0
        self._cdp_reconnect_interval: float = 300.0

    # -- public api ----------------------------------------------------------

    def on_snapshot(self, callback: SnapshotCallback) -> None:
        """Register a callback invoked for every new snapshot."""
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Start the collection loop. Returns immediately; run in background."""
        if self._running:
            logger.warning("chart_monitor_already_running")
            return

        self._running = True
        self._tv_client = TradingViewClient()

        if TV_CDP_ENABLED and LLM_USE_SCREENSHOT:
            await self._init_cdp()

        self._task = asyncio.create_task(self._loop())
        logger.info(
            "chart_monitor_started",
            symbols=self._symbols,
            timeframes=self._timeframes,
            poll_seconds=self._poll_seconds,
            cdp=self._cdp_available,
        )

    async def stop(self) -> None:
        """Gracefully stop the collection loop and release resources."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._tv_cdp is not None:
            await self._tv_cdp.disconnect()
            self._tv_cdp = None
            self._cdp_available = False

        if self._tv_client is not None:
            await self._tv_client.close()
            self._tv_client = None

        logger.info("chart_monitor_stopped")

    def get_latest(self, symbol: str, timeframe: str) -> ChartSnapshot | None:
        """Return the most recent snapshot for *symbol*/*timeframe*."""
        buf = self._buffers.get(self._key(symbol, timeframe))
        if buf:
            return buf[-1]
        return None

    def get_history(self, symbol: str, timeframe: str, n: int = 10) -> list[ChartSnapshot]:
        """Return up to *n* most recent snapshots for *symbol*/*timeframe*."""
        buf = self._buffers.get(self._key(symbol, timeframe))
        if not buf:
            return []
        return list(buf)[-n:]

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _key(symbol: str, timeframe: str) -> str:
        return f"{symbol}:{timeframe}"

    async def _init_cdp(self) -> None:
        """Attempt CDP connection; degrade gracefully on failure."""
        try:
            self._tv_cdp = TradingViewCDP()
            connected = await self._tv_cdp.connect()
            if connected:
                self._cdp_available = True
                logger.info("chart_monitor_cdp_connected")
            else:
                self._cdp_available = False
                self._tv_cdp = None
                logger.warning("chart_monitor_cdp_fallback_mcp_only")
        except Exception as exc:
            self._cdp_available = False
            self._tv_cdp = None
            logger.warning(
                "chart_monitor_cdp_init_failed",
                error=str(exc),
                fallback="mcp_only",
            )

    async def _loop(self) -> None:
        """Main polling loop — iterates all symbol/timeframe pairs."""
        while self._running:
            start = asyncio.get_event_loop().time()
            for symbol in self._symbols:
                for timeframe in self._timeframes:
                    if not self._running:
                        return
                    try:
                        snapshot = await self._collect_snapshot(symbol, timeframe)
                        self._store(snapshot)
                        await self._publish(snapshot)
                    except Exception as exc:
                        logger.error(
                            "chart_monitor_collect_failed",
                            symbol=symbol,
                            timeframe=timeframe,
                            error=str(exc),
                        )
            elapsed = asyncio.get_event_loop().time() - start
            sleep_for = max(0.0, self._poll_seconds - elapsed)
            await asyncio.sleep(sleep_for)

    async def _collect_snapshot(
        self,
        symbol: str,
        timeframe: str,
    ) -> ChartSnapshot:
        """Fetch OHLCV (MCP) and optionally screenshot (CDP) for one pair."""
        assert self._tv_client is not None

        bars: list[OHLCVBar] = []
        indicators: dict[str, Any] = {}
        screenshot_path: Path | None = None

        # OHLCV via MCP (primary source)
        try:
            bars = await self._tv_client.get_ohlcv(symbol, timeframe, limit=100)
        except Exception as exc:
            logger.warning(
                "chart_monitor_ohlcv_failed",
                symbol=symbol,
                timeframe=timeframe,
                error=str(exc),
            )

        if not bars:
            logger.warning("chart_monitor_ohlcv_empty", symbol=symbol, timeframe=timeframe)

        # Screenshot via CDP (optional, best-effort)
        if self._cdp_available and self._tv_cdp is not None:
            try:
                await self._tv_cdp.change_symbol(symbol)
                await self._tv_cdp.change_timeframe(timeframe)
                out_dir = Path(TV_SCREENSHOT_DIR)
                out_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
                out_path = out_dir / f"{symbol}_{timeframe}_{ts}.png"
                screenshot_path = await self._tv_cdp.screenshot_chart(out_path)

                # Extract indicator data from CDP if available
                chart_data = await self._tv_cdp.get_chart_data()
                if chart_data and "error" not in chart_data:
                    indicators = chart_data.get("indicators", {})
            except Exception as exc:
                logger.warning(
                    "chart_monitor_screenshot_failed",
                    symbol=symbol,
                    timeframe=timeframe,
                    error=str(exc),
                )
                self._cdp_available = False
                self._tv_cdp = None
                self._last_cdp_attempt = time.monotonic()

        if not self._cdp_available and self._should_reconnect_cdp():
            await self._try_reconnect_cdp()

        if bars and bars[-1].close == 0:
            logger.warning(
                "chart_monitor_ohlcv_zero_price",
                symbol=symbol,
                timeframe=timeframe,
                last_bar_close=bars[-1].close if bars else None,
            )

        return ChartSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            ohlcv=bars,
            indicators=indicators,
            screenshot_path=screenshot_path,
            timestamp=datetime.now(tz=UTC),
        )

    def _should_reconnect_cdp(self) -> bool:
        elapsed = time.monotonic() - self._last_cdp_attempt
        return elapsed >= self._cdp_reconnect_interval

    async def _try_reconnect_cdp(self) -> None:
        self._last_cdp_attempt = time.monotonic()
        logger.info("chart_monitor_cdp_reconnect_attempt")
        try:
            if self._tv_cdp is not None:
                await self._tv_cdp.disconnect()
            self._tv_cdp = TradingViewCDP()
            connected = await self._tv_cdp.connect()
            if connected:
                self._cdp_available = True
                logger.info("chart_monitor_cdp_reconnected")
            else:
                self._tv_cdp = None
                logger.warning("chart_monitor_cdp_reconnect_failed")
        except Exception as exc:
            self._cdp_available = False
            self._tv_cdp = None
            logger.warning(
                "chart_monitor_cdp_reconnect_error",
                error=str(exc),
            )

    def _store(self, snapshot: ChartSnapshot) -> None:
        """Append snapshot to the ring buffer for its symbol/timeframe."""
        key = self._key(snapshot.symbol, snapshot.timeframe)
        if key not in self._buffers:
            self._buffers[key] = deque(maxlen=MAX_SNAPSHOTS)
        self._buffers[key].append(snapshot)

    async def _publish(self, snapshot: ChartSnapshot) -> None:
        """Invoke all registered callbacks with the new snapshot."""
        for cb in self._callbacks:
            try:
                result = cb(snapshot)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.error(
                    "chart_monitor_callback_error",
                    symbol=snapshot.symbol,
                    timeframe=snapshot.timeframe,
                    error=str(exc),
                )
