"""
Dead Man's Switch for Quant OS production trading system.

Monitors the heartbeat written by :class:`~quant_os.monitoring.heartbeat.HeartbeatMonitor`.
If no heartbeat is received within *TIMEOUT* seconds the switch fires:
1. Closes all open positions via the execution engine.
2. Halts the trading system (circuit breaker).
3. Sends a CRITICAL Telegram alert.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, UTC
from typing import Any, Callable, Coroutine, Dict, Optional

logger = logging.getLogger(__name__)

# Timeout before the switch fires (seconds)
DEFAULT_TIMEOUT: float = 300.0  # 5 minutes

# How often the monitor loop checks the heartbeat (seconds)
_CHECK_INTERVAL: float = 30.0


class DeadMansSwitch:
    """Watches the heartbeat and triggers an emergency shutdown on stall.

    Args:
        state: Shared state dict containing the heartbeat key.
        close_all_positions: Async callable that closes every open position.
        halt_system: Async callable that trips the circuit breaker / halts trading.
        send_alert: Async callable ``(message: str, severity: str) -> None``.
        timeout: Seconds of silence before firing.  Defaults to ``300`` (5 min).
        check_interval: Seconds between checks.  Defaults to ``30``.
        key: State key to read.  Must match the key used by
            :class:`~quant_os.monitoring.heartbeat.HeartbeatMonitor`.
    """

    def __init__(
        self,
        state: Dict[str, Any],
        *,
        close_all_positions: Callable[[], Coroutine[Any, Any, None]],
        halt_system: Callable[[], Coroutine[Any, Any, None]],
        send_alert: Callable[[str, str], Coroutine[Any, Any, None]],
        timeout: float = DEFAULT_TIMEOUT,
        check_interval: float = _CHECK_INTERVAL,
        key: str = "last_heartbeat",
    ) -> None:
        self._state = state
        self._close_all_positions = close_all_positions
        self._halt_system = halt_system
        self._send_alert = send_alert
        self._timeout = timeout
        self._check_interval = check_interval
        self._key = key

        self._task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._fired = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background monitoring loop."""
        if self._running:
            return
        self._running = True
        self._fired = False
        self._task = asyncio.create_task(self._monitor())
        logger.info(
            "DeadMansSwitch started (timeout=%.0fs, check_interval=%.0fs)",
            self._timeout,
            self._check_interval,
        )

    async def stop(self) -> None:
        """Stop the monitoring loop."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("DeadMansSwitch stopped")

    @property
    def fired(self) -> bool:
        """``True`` if the switch has already triggered."""
        return self._fired

    # ------------------------------------------------------------------
    # Core monitoring loop
    # ------------------------------------------------------------------

    async def _monitor(self) -> None:
        """Background coroutine that checks heartbeat freshness."""
        while self._running:
            await asyncio.sleep(self._check_interval)

            if self._fired:
                # Already triggered — keep sleeping until stop() is called.
                continue

            elapsed = self._seconds_since_last_beat()
            if elapsed is None:
                logger.warning("DeadMansSwitch: no heartbeat recorded yet")
                continue

            if elapsed > self._timeout:
                logger.critical(
                    "DeadMansSwitch TRIGGERED — no heartbeat for %.0fs (timeout=%.0fs)",
                    elapsed,
                    self._timeout,
                )
                await self._fire()
                return  # exit loop; the system is halted

            logger.debug(
                "DeadMansSwitch OK — last beat %.0fs ago", elapsed
            )

    # ------------------------------------------------------------------
    # Fire logic
    # ------------------------------------------------------------------

    async def _fire(self) -> None:
        """Execute emergency shutdown sequence.

        Order is critical:
        1. Halt trading (circuit breaker) to prevent new orders.
        2. Close all open positions to flatten exposure.
        3. Send CRITICAL alert to Telegram.
        """
        self._fired = True

        # Step 1: Halt system
        try:
            await self._halt_system()
            logger.critical("DeadMansSwitch: system halted")
        except Exception:
            logger.exception("DeadMansSwitch: failed to halt system")

        # Step 2: Close all positions
        try:
            await self._close_all_positions()
            logger.critical("DeadMansSwitch: all positions closed")
        except Exception:
            logger.exception("DeadMansSwitch: failed to close positions")

        # Step 3: Send CRITICAL alert
        elapsed = self._seconds_since_last_beat()
        msg = (
            f"DEAD MAN'S SWITCH FIRED\n\n"
            f"No heartbeat received for {elapsed:.0f}s (timeout: {self._timeout:.0f}s).\n"
            f"System halted. All positions closed.\n"
            f"Manual intervention required."
        )
        try:
            await self._send_alert(msg, "CRITICAL")
        except Exception:
            logger.exception("DeadMansSwitch: failed to send alert")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _seconds_since_last_beat(self) -> Optional[float]:
        """Return seconds elapsed since the last heartbeat, or ``None``."""
        raw = self._state.get(self._key)
        if raw is None:
            return None
        try:
            if isinstance(raw, str):
                last = datetime.fromisoformat(raw)
            elif isinstance(raw, datetime):
                last = raw
            else:
                return None
            if last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            return (datetime.now(UTC) - last).total_seconds()
        except (ValueError, TypeError):
            logger.warning("DeadMansSwitch: unparseable heartbeat value: %s", raw)
            return None


def create_mt5_close_all_callback(mt5_module=None) -> Callable[[], Coroutine[Any, Any, None]]:
    """P2 fix: Default MT5 close-all-positions callback factory.

    Closes all open positions by:
    1. Fetching all open positions from MT5
    2. Sending close order for each (market order, opposite direction)
    3. Logging results

    Usage:
        dms = DeadMansSwitch(
            state=state,
            close_all_positions=create_mt5_close_all_callback(),
            halt_system=halt_fn,
            send_alert=alert_fn,
        )
    """
    async def _close_all_mt5() -> None:
        import logging
        log = logging.getLogger("dead_mans_switch.close_all")
        try:
            import MetaTrader5 as mt5
        except ImportError:
            log.error("Cannot close positions: MetaTrader5 not installed")
            return

        positions = mt5.positions_get()
        if not positions:
            log.info("No open positions to close")
            return

        log.warning(f"Closing {len(positions)} open positions (dead man's switch)")
        for pos in positions:
            try:
                # Close = opposite direction market order
                close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "position": pos.ticket,
                    "symbol": pos.symbol,
                    "volume": pos.volume,
                    "type": close_type,
                    "price": mt5.symbol_info_tick(pos.symbol).bid if close_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(pos.symbol).ask,
                    "deviation": 20,
                    "magic": pos.magic,
                    "comment": "dead_mans_switch_close",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                result = mt5.order_send(request)
                if result.retcode != mt5.TRADE_RETCODE_DONE:
                    log.error(f"Close failed ticket={pos.ticket}: {result.retcode}")
                else:
                    log.info(f"Closed ticket={pos.ticket} {pos.symbol} {pos.volume}")
            except Exception as e:
                log.error(f"Error closing ticket={pos.ticket}: {e}")

    return _close_all_mt5

