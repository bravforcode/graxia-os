"""
Centaur Telegram Agent — async signal-notifier for human-in-the-loop trading.

Subscribes to ensemble signals on EventBus, buffers them into an internal
asyncio.Queue, and drains the queue one-by-one with rate-limit backoff.
Telegram downtime or 429 blocks ONLY the queue, never the EventBus.

This agent does NOT execute trades.  It only notifies the human operator
who presses Buy/Sell on their phone.  Once trust is established after ~6
months, the human can switch to full-auto mode.

Architecture:
    EventBus ──observe()──▶ _pending list ──act()──▶ asyncio.Queue
                                                          │
                                                    _drain_queue()
                                                          │
                                                    httpx POST
                                                    (with 429 backoff)
                                                          │
                                                    Telegram API

Sanity checks:
- httpx.AsyncClient (NOT requests) — never blocks the Event Loop
- Queue isolation — rate-limit sleep only blocks the drain task
- Fire-and-forget — Telegram failure never propagates to EventBus
- shutdown() hook — closes TCP connection on SIGTERM / Ctrl+C
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from ..enums import SignalType
from ..events import Event, SignalEvent
from .base import Agent

logger = structlog.get_logger(__name__)

# ── Config ─────────────────────────────────────────────────────────


def _get_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def _get_chat_id() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "")


# ── Message Formatter ──────────────────────────────────────────────


@dataclass(frozen=True)
class CentaurPayload:
    """Immutable payload sent to Telegram."""

    asset: str
    direction: str
    confidence: float
    entry: float
    stop_loss: float
    take_profit: float
    regime: str
    risk_check: str
    strategy_source: str
    metadata: dict[str, Any]


def format_centaur_message(p: CentaurPayload) -> str:
    """Format a centaur-style Telegram message."""
    emoji = "🟢 LONG" if p.direction == "BUY" else "🔴 SHORT"
    rr = "—"
    if p.stop_loss and p.entry:
        risk = abs(p.entry - p.stop_loss)
        reward = abs(p.take_profit - p.entry) if p.take_profit else 0
        rr = f"{reward / risk:.1f}:1" if risk > 0 else "—"

    lines = [
        "🦾 *GRAXIA CENTAUR*",
        "",
        f"🪙 Asset: `{p.asset}` | Regime: `{p.regime}`",
        f"📊 Signal: *{emoji}* (Conf: `{p.confidence:.2f}`)",
        f"🎯 Entry: `{p.entry:.2f}` | RR: `{rr}`",
        f"🛡️ SL: `{p.stop_loss:.2f}` | TP: `{p.take_profit:.2f}`",
        f"🔍 Risk: `{p.risk_check}` | Source: `{p.strategy_source}`",
        "",
        "[กดเทรดด้วยมือคุณเอง]",
    ]
    return "\n".join(lines)


# ── Agent ──────────────────────────────────────────────────────────


class CentaurTelegramAgent(Agent):
    """
    Async Telegram notifier for centaur (human-in-the-loop) trading.

    Lifecycle:
        1. observe(SignalEvent) — stores signal in _pending list
        2. act() — moves _pending into asyncio.Queue, starts drain
        3. _drain_queue() — sends one-by-one with 429 backoff
        4. shutdown() — closes TCP connection cleanly

    Usage with EventBus:
        agent = CentaurTelegramAgent()
        bus.subscribe("signal.new", agent.observe)
        # on shutdown:
        await agent.shutdown()
    """

    SEND_TIMEOUT = 5.0  # seconds — max wait per HTTP request
    QUEUE_MAXSIZE = 100  # max buffered signals before dropping

    def __init__(
        self,
        name: str = "centaur_telegram",
        token: str | None = None,
        chat_id: str | None = None,
    ) -> None:
        super().__init__(name)
        self._token = token or _get_token()
        self._chat_id = chat_id or _get_chat_id()
        self._pending: list[SignalEvent] = []
        self._client: httpx.AsyncClient | None = None
        self._queue: asyncio.Queue[SignalEvent] = asyncio.Queue(
            maxsize=self.QUEUE_MAXSIZE
        )
        self._drain_task: asyncio.Task[None] | None = None

    # ── Lifecycle ──────────────────────────────────────────────────

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Lazy-init the async HTTP client (created once, reused)."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.SEND_TIMEOUT)
        return self._client

    async def shutdown(self) -> None:
        """Close TCP connection and cancel drain task. Call on SIGTERM."""
        if self._drain_task and not self._drain_task.done():
            self._drain_task.cancel()
            try:
                await self._drain_task
            except asyncio.CancelledError:
                pass
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        logger.info("centaur_telegram.shutdown_complete")

    # Backward-compat alias
    async def close(self) -> None:
        await self.shutdown()

    # ── Agent interface ────────────────────────────────────────────

    def observe(self, event: Event) -> None:  # type: ignore[override]
        """Store incoming SignalEvent for later dispatch."""
        if not isinstance(event, SignalEvent):
            return
        if event.signal_type in (SignalType.NO_TRADE, None):
            return
        self._pending.append(event)

    async def act(self) -> None:
        """
        Move pending signals into the async queue and start drain.

        The drain runs as a background task so the EventBus is never
        blocked by Telegram latency or 429 backoff sleeps.
        """
        if not self._pending:
            return
        if not self._token or not self._chat_id:
            logger.warning(
                "centaur_telegram.skip_no_config", pending=len(self._pending)
            )
            self._pending.clear()
            return

        # Transfer pending → queue (drop if full — never block EventBus)
        dropped = 0
        for sig in self._pending:
            try:
                self._queue.put_nowait(sig)
            except asyncio.QueueFull:
                dropped += 1
        self._pending.clear()

        if dropped:
            logger.warning("centaur_telegram.queue_overflow", dropped=dropped)

        # Start drain if not already running
        if self._drain_task is None or self._drain_task.done():
            self._drain_task = asyncio.create_task(
                self._drain_queue(), name="telegram_drain"
            )

    async def _drain_queue(self) -> None:
        """
        Send signals one-by-one from the queue.

        Rate-limit isolation: 429 backoff sleep happens HERE only,
        never touching the EventBus loop.
        """
        if not self._token or not self._chat_id:
            return

        client = await self._ensure_client()

        while not self._queue.empty():
            try:
                sig = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            payload = CentaurPayload(
                asset=sig.symbol,
                direction=(
                    sig.signal_type.value
                    if isinstance(sig.signal_type, SignalType)
                    else str(sig.signal_type)
                ),
                confidence=sig.confidence,
                entry=sig.entry_price,
                stop_loss=sig.stop_loss,
                take_profit=sig.take_profit,
                regime=sig.regime or "UNKNOWN",
                risk_check="PENDING",
                strategy_source=sig.source or "ensemble",
                metadata=sig.metadata,
            )
            text = format_centaur_message(payload)

            try:
                resp = await client.post(
                    f"https://api.telegram.org/bot{self._token}/sendMessage",
                    json={
                        "chat_id": self._chat_id,
                        "text": text,
                        "parse_mode": "Markdown",
                    },
                )
                if resp.status_code == 429:
                    retry_after = resp.json().get("parameters", {}).get(
                        "retry_after", 30
                    )
                    logger.warning(
                        "centaur_telegram.rate_limited",
                        retry_after=retry_after,
                        asset=payload.asset,
                    )
                    # Backoff — blocks ONLY this drain task, EventBus is safe
                    await asyncio.sleep(min(retry_after, 30))
                elif resp.status_code != 200:
                    logger.warning(
                        "centaur_telegram.send_failed",
                        status=resp.status_code,
                        asset=payload.asset,
                    )
            except httpx.ConnectTimeout:
                logger.warning("centaur_telegram.timeout", asset=payload.asset)
            except httpx.HTTPError as exc:
                logger.warning(
                    "centaur_telegram.http_error",
                    error=str(exc),
                    asset=payload.asset,
                )
            except Exception as exc:
                logger.warning(
                    "centaur_telegram.send_error",
                    error=str(exc),
                    asset=payload.asset,
                )

    def reset(self) -> None:
        super().reset()
        self._pending.clear()
