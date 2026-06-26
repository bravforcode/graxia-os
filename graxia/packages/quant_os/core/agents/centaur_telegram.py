"""
Centaur Telegram Agent — async signal-notifier for human-in-the-loop trading.

Subscribes to ensemble signals on EventBus, formats a centaur message,
and fires it to Telegram via httpx.AsyncClient (non-blocking).

This agent does NOT execute trades.  It only notifies the human operator
who presses Buy/Sell on their phone.  Once trust is established after ~6
months, the human can switch to full-auto mode.

Sanity checks applied:
- httpx.AsyncClient (NOT requests) — never blocks the Event Loop
- Fire-and-forget pattern — Telegram downtime cannot stall the trading engine
- Env-var config: TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
"""

from __future__ import annotations

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
        1. observe(SignalEvent) — stores latest signal per symbol
        2. act() — formats + fires HTTP POST to Telegram (fire-and-forget)
        3. Returns None (does not produce a trading signal)

    Usage with EventBus:
        agent = CentaurTelegramAgent()
        bus.subscribe("signal.new", agent.observe)
    """

    SEND_TIMEOUT = 5.0  # seconds — max wait for Telegram API

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

    # ── Lifecycle ──────────────────────────────────────────────────

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Lazy-init the async HTTP client (created once, reused)."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.SEND_TIMEOUT)
        return self._client

    async def close(self) -> None:
        """Shut down the HTTP client gracefully."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

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
        Fire-and-forget Telegram messages for all pending signals.

        Returns None — this agent never produces a trading signal.
        Errors are logged but never raised (Telegram failure ≠ trading failure).
        """
        if not self._pending:
            return
        if not self._token or not self._chat_id:
            logger.warning("centaur_telegram.skip_no_config", pending=len(self._pending))
            self._pending.clear()
            return

        events = list(self._pending)
        self._pending.clear()

        client = await self._ensure_client()

        for sig in events:
            payload = CentaurPayload(
                asset=sig.symbol,
                direction=sig.signal_type.value if isinstance(sig.signal_type, SignalType) else str(sig.signal_type),
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
                    # Rate limited — Telegram says retry after N seconds
                    retry_after = resp.json().get("parameters", {}).get("retry_after", 30)
                    logger.warning(
                        "centaur_telegram.rate_limited",
                        retry_after=retry_after,
                        asset=payload.asset,
                    )
                elif resp.status_code != 200:
                    logger.warning(
                        "centaur_telegram.send_failed",
                        status=resp.status_code,
                        asset=payload.asset,
                    )
            except httpx.ConnectTimeout:
                logger.warning("centaur_telegram.timeout", asset=payload.asset)
            except httpx.HTTPError as exc:
                # Any HTTP-level error (DNS, connection refused, etc.)
                logger.warning("centaur_telegram.http_error", error=str(exc), asset=payload.asset)
            except Exception as exc:
                # Catch-all — Telegram failure must NEVER block the trading engine
                logger.warning("centaur_telegram.send_error", error=str(exc), asset=payload.asset)

    def reset(self) -> None:
        super().reset()
        self._pending.clear()
