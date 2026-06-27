"""
Telegram Callback Handler — Processes inline keyboard responses.

Receives callback_query from Telegram when user presses:
  - APPROVE: Execute trade at full size
  - REJECT: Cancel trade
  - HALF: Execute trade at half size
  - SKIP: Skip this signal, keep listening

Usage:
  from core.telegram_callback import TelegramCallbackHandler
  handler = TelegramCallbackHandler()
  await handler.handle_callback(callback_query)
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


class CallbackAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    HALF = "half"
    SKIP = "skip"


@dataclass(frozen=True)
class CallbackResult:
    """Result of processing a callback query."""
    action: CallbackAction
    asset: str
    direction: str
    message_id: int | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class PendingSignal:
    """Signal waiting for human approval."""
    message_id: int
    asset: str
    direction: str
    confidence: float
    entry: float
    stop_loss: float
    take_profit: float
    regime: str
    strategy_source: str
    metadata: dict[str, Any]
    sent_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class TelegramCallbackHandler:
    """
    Handles inline keyboard callbacks from Telegram.

    Architecture:
        Telegram Bot API (webhook/polling)
            -> handle_callback()
            -> parse callback_data
            -> execute/reject/half/skip
            -> answer_callback_query() (remove loading spinner)
            -> edit_message() (update status)
    """

    CALLBACK_TIMEOUT = 300  # 5 minutes — expire unapproved signals

    def __init__(
        self,
        token: str | None = None,
        on_approve: Callable | None = None,
        on_reject: Callable | None = None,
    ):
        self._token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._client: httpx.AsyncClient | None = None
        self._pending: dict[str, PendingSignal] = {}  # key = "asset:direction"
        self._on_approve = on_approve
        self._on_reject = on_reject
        self._results: list[CallbackResult] = []

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=5.0)
        return self._client

    def register_signal(self, signal: PendingSignal) -> None:
        """Register a signal that's waiting for approval."""
        key = f"{signal.asset}:{signal.direction}"
        self._pending[key] = signal
        logger.info("callback.signal_registered", key=key, asset=signal.asset)

    async def handle_callback(self, callback_query: dict) -> CallbackResult | None:
        """
        Process a callback_query from Telegram webhook/polling.

        Args:
            callback_query: Raw callback_query dict from Telegram API

        Returns:
            CallbackResult or None if invalid
        """
        cb_id = callback_query.get("id", "")
        data = callback_query.get("data", "")
        message = callback_query.get("message", {})
        message_id = message.get("message_id")

        if not data:
            await self._answer(cb_id, "Invalid action")
            return None

        parts = data.split(":")
        if len(parts) < 3:
            await self._answer(cb_id, "Invalid format")
            return None

        action_str, asset, direction = parts[0], parts[1], parts[2]

        try:
            action = CallbackAction(action_str)
        except ValueError:
            await self._answer(cb_id, f"Unknown action: {action_str}")
            return None

        key = f"{asset}:{direction}"
        pending = self._pending.pop(key, None)

        if not pending and action != CallbackAction.SKIP:
            await self._answer(cb_id, f"No pending signal for {asset}")
            return None

        result = CallbackResult(
            action=action,
            asset=asset,
            direction=direction,
            message_id=message_id,
        )
        self._results.append(result)

        # Process action
        if action == CallbackAction.APPROVE:
            await self._answer(cb_id, f"Approved {asset} {direction}")
            await self._edit_message(message_id, f"Approved {asset} {direction}", approved=True)
            if self._on_approve:
                await self._fire_callback(self._on_approve, pending, 1.0)
            logger.info("callback.approved", asset=asset, direction=direction)

        elif action == CallbackAction.REJECT:
            await self._answer(cb_id, f"Rejected {asset} {direction}")
            await self._edit_message(message_id, f"Rejected {asset} {direction}", approved=False)
            if self._on_reject:
                await self._fire_callback(self._on_reject, pending)
            logger.info("callback.rejected", asset=asset, direction=direction)

        elif action == CallbackAction.HALF:
            await self._answer(cb_id, f"Half size {asset} {direction}")
            await self._edit_message(message_id, f"Half size {asset} {direction}", approved=True)
            if self._on_approve:
                await self._fire_callback(self._on_approve, pending, 0.5)
            logger.info("callback.half", asset=asset, direction=direction)

        elif action == CallbackAction.SKIP:
            await self._answer(cb_id, f"Skipped {asset}")
            logger.info("callback.skipped", asset=asset, direction=direction)

        return result

    async def _fire_callback(self, fn: Callable, signal: PendingSignal | None, size_mult: float = 1.0):
        """Fire callback safely."""
        try:
            if asyncio.iscoroutinefunction(fn):
                await fn(signal, size_mult)
            else:
                fn(signal, size_mult)
        except Exception as e:
            logger.warning("callback.fire_error", error=str(e))

    async def _answer(self, callback_id: str, text: str = ""):
        """Answer callback query to remove loading spinner."""
        if not self._token or not callback_id:
            return
        try:
            client = await self._ensure_client()
            await client.post(
                f"https://api.telegram.org/bot{self._token}/answerCallbackQuery",
                json={"callback_query_id": callback_id, "text": text},
            )
        except Exception:
            pass

    async def _edit_message(self, message_id: int | None, text: str, approved: bool = True):
        """Edit the original message to show status."""
        if not self._token or not message_id:
            return
        try:
            client = await self._ensure_client()
            status = "APPROVED" if approved else "REJECTED"
            emoji = "✅" if approved else "❌"
            await client.post(
                f"https://api.telegram.org/bot{self._token}/editMessageText",
                json={
                    "chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
                    "message_id": message_id,
                    "text": f"{emoji} {status}: {text}",
                },
            )
        except Exception:
            pass

    async def check_expired(self) -> list[CallbackResult]:
        """Check for expired signals (no response within timeout)."""
        now = datetime.now(UTC)
        expired = []
        for key, signal in list(self._pending.items()):
            age = (now - signal.sent_at).total_seconds()
            if age > self.CALLBACK_TIMEOUT:
                result = CallbackResult(
                    action=CallbackAction.SKIP,
                    asset=signal.asset,
                    direction=signal.direction,
                )
                expired.append(result)
                self._results.append(result)
                del self._pending[key]
                logger.info("callback.expired", asset=signal.asset, age_s=age)
        return expired

    def get_results(self) -> list[CallbackResult]:
        return list(self._results)

    def clear_results(self):
        self._results.clear()

    async def shutdown(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
