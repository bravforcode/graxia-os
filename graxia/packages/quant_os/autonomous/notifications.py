"""Telegram notification module for autonomous trading.

Sends trade alerts, kill switch events, daily summaries, and error alerts.
Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime

import structlog

logger = structlog.get_logger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
_MIN_SEND_INTERVAL_SECONDS = 1.0


class TradeNotifier:
    """Sends trade notifications to Telegram."""

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        enabled: bool = True,
    ) -> None:
        self._token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self._enabled = enabled and bool(self._token and self._chat_id)
        self._last_send_time: dict[str, float] = {}

        if not self._enabled:
            logger.debug("trade_notifier_disabled", reason="missing token or chat_id")

    async def notify_trade(self, decision: object, result: object) -> None:
        """Send trade execution notification."""
        if not self._enabled:
            return

        symbol = getattr(decision, "symbol", "?")
        direction = getattr(decision, "direction", None)
        direction_str = direction.value if hasattr(direction, "value") else str(direction)
        confidence = getattr(decision, "confidence", 0.0)
        entry = getattr(decision, "entry", 0.0)
        sl = getattr(decision, "stop_loss", 0.0)
        tp = getattr(decision, "take_profit", 0.0)
        success = getattr(result, "success", False)
        order_id = getattr(result, "order_id", "")
        filled_qty = getattr(result, "filled_quantity", 0.0)
        error = getattr(result, "error", "")

        mode_label = "PAPER" if not getattr(result, "approval_required", False) else "LIVE"
        status = "EXECUTED" if success else "FAILED"

        if not success:
            text = (
                f"X TRADE FAILED ({mode_label})\n"
                f"{'━' * 28}\n"
                f"Symbol: {symbol} | {direction_str}\n"
                f"Confidence: {confidence:.0%}\n"
                f"Entry: {entry:.5f} | SL: {sl:.5f} | TP: {tp:.5f}\n"
                f"Order ID: {order_id}\n"
                f"Error: {error}\n"
                f"{'━' * 28}"
            )
        else:
            text = (
                f"TRADE EXECUTED ({mode_label})\n"
                f"{'━' * 28}\n"
                f"Symbol: {symbol} | {direction_str}\n"
                f"Confidence: {confidence:.0%}\n"
                f"Entry: {entry:.5f} | SL: {sl:.5f} | TP: {tp:.5f}\n"
                f"Size: {filled_qty:.4f} lots\n"
                f"Order ID: {order_id}\n"
                f"{'━' * 28}"
            )

        await self._send(text)

    async def notify_kill_switch(self, reason: str) -> None:
        """Send kill switch activation alert."""
        text = (
            f"KILL SWITCH ACTIVATED\n"
            f"{'━' * 28}\n"
            f"Reason: {reason}\n"
            f"Time: {datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"All trading halted.\n"
            f"{'━' * 28}"
        )
        await self._send(text)

    async def notify_daily_summary(self, stats: dict) -> None:
        """Send daily trading summary."""
        trades = stats.get("trades_today", 0)
        pnl = stats.get("realized_pnl", 0.0)
        max_trades = stats.get("max_daily_trades", 0)
        open_pos = stats.get("open_positions", 0)
        max_pos = stats.get("max_open_positions", 0)
        mode = stats.get("mode", "?")

        pnl_str = f"{pnl:+.2f}" if pnl != 0 else "0.00"
        text = (
            f"DAILY SUMMARY ({mode})\n"
            f"{'━' * 28}\n"
            f"Date: {datetime.now(tz=UTC).strftime('%Y-%m-%d')}\n"
            f"Trades: {trades}/{max_trades}\n"
            f"P&L: {pnl_str}\n"
            f"Open Positions: {open_pos}/{max_pos}\n"
            f"{'━' * 28}"
        )
        await self._send(text)

    async def notify_error(self, component: str, error: str) -> None:
        """Send error alert when consecutive errors exceed threshold."""
        text = (
            f"ERROR ALERT\n"
            f"{'━' * 28}\n"
            f"Component: {component}\n"
            f"Error: {error}\n"
            f"Time: {datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"{'━' * 28}"
        )
        await self._send(text)

    async def _send(self, text: str) -> None:
        """Send a message via Telegram Bot API."""
        try:
            import httpx

            await self._rate_limit(self._chat_id)
            url = _TELEGRAM_API.format(token=self._token)
            payload = {
                "chat_id": self._chat_id,
                "text": text,
                "parse_mode": "HTML",
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    self._last_send_time[self._chat_id] = time.monotonic()
                else:
                    logger.warning(
                        "trade_notifier_send_failed",
                        status=resp.status_code,
                        body=resp.text[:200],
                    )
        except ImportError:
            logger.warning("trade_notifier_httpx_missing", hint="pip install httpx")
        except Exception as exc:
            logger.error("trade_notifier_send_error", error=str(exc))

    async def _rate_limit(self, chat_id: str) -> None:
        """Enforce minimum interval between sends to the same chat."""
        last = self._last_send_time.get(chat_id, 0.0)
        elapsed = time.monotonic() - last
        if elapsed < _MIN_SEND_INTERVAL_SECONDS:
            await asyncio.sleep(_MIN_SEND_INTERVAL_SECONDS - elapsed)
