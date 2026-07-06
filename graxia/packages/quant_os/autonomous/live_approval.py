"""Live Trade Approval — Telegram-based human approval for live trades.

When the autonomous loop runs in live mode, this module:
1. Sends a Telegram message with trade details + inline keyboard buttons
2. Waits for human approval (APPROVE / REJECT / HALF / SKIP)
3. Returns the approval result to the OrderExecutor

Integrates with existing TelegramCallbackHandler infrastructure.

Safety:
    Golden Rule #2: AI_CANNOT_SUBMIT_ORDER = True
    In live mode, NO trade executes without explicit human approval.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import httpx
import structlog

from ..autonomous.decision_engine import TradeDecision

logger = structlog.get_logger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"
APPROVAL_TIMEOUT_SECONDS = 300  # 5 minutes
MIN_SEND_INTERVAL_SECONDS = 1.0


class ApprovalAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    HALF = "half"
    SKIP = "skip"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class ApprovalResult:
    """Outcome of a live trade approval request."""

    action: ApprovalAction
    approved: bool
    size_multiplier: float = 1.0  # 1.0 = full, 0.5 = half, 0.0 = reject
    latency_seconds: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class LiveApprovalGate:
    """Telegram-based human approval for live autonomous trades.

    Usage:
        gate = LiveApprovalGate()
        result = await gate.request_approval(decision)
        if result.approved:
            # execute trade
    """

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        timeout_seconds: int = APPROVAL_TIMEOUT_SECONDS,
    ) -> None:
        self._token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self._timeout = timeout_seconds
        self._pending: dict[str, asyncio.Future[ApprovalAction]] = {}
        self._authorized_users: set[str] = self._load_authorized_users()
        self._last_send_time: dict[str, float] = {}

    @staticmethod
    def _load_authorized_users() -> set[str]:
        raw = os.getenv("TELEGRAM_ALLOWED_USERS", "")
        if not raw:
            return set()
        return {uid.strip() for uid in raw.split(",") if uid.strip()}

    async def request_approval(self, decision: TradeDecision) -> ApprovalResult:
        """Send trade details to Telegram and wait for human approval.

        Returns ApprovalResult with the human's decision.
        Times out after self._timeout seconds → treated as REJECT.
        """
        if not self._token or not self._chat_id:
            logger.error("live_approval_no_telegram_config")
            return ApprovalResult(action=ApprovalAction.REJECT, approved=False)

        request_id = f"{decision.symbol}-{decision.timestamp.strftime('%H%M%S')}"
        future: asyncio.Future[ApprovalAction] = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future

        # Build message
        text = self._build_message(decision, request_id)
        keyboard = self._build_keyboard(request_id)

        # Send to Telegram
        try:
            message_id = await self._send_message(text, keyboard)
            if not message_id:
                return ApprovalResult(action=ApprovalAction.REJECT, approved=False)
        except Exception as exc:
            logger.error("live_approval_send_failed", error=str(exc))
            return ApprovalResult(action=ApprovalAction.REJECT, approved=False)

        # Wait for callback
        try:
            action = await asyncio.wait_for(future, timeout=self._timeout)
        except TimeoutError:
            action = ApprovalAction.TIMEOUT
            logger.warning("live_approval_timeout", request_id=request_id)
            await self._edit_message(
                message_id,
                f"{text}\n\n⏰ TIMEOUT — auto-rejected after {self._timeout}s",
            )
        finally:
            self._pending.pop(request_id, None)

        # Map action to result
        result = self._action_to_result(action)
        logger.info(
            "live_approval_result",
            request_id=request_id,
            action=action.value,
            approved=result.approved,
        )
        return result

    def handle_callback(self, request_id: str, action: ApprovalAction, user_id: str = "") -> None:
        """Called by the Telegram callback handler when user presses a button."""
        if not self._authorized_users:
            logger.warning("live_approval.no_users_configured", action="rejecting")
            return
        if user_id not in self._authorized_users:
            logger.warning(
                "live_approval.unauthorized_user",
                user_id=user_id,
                request_id=request_id,
            )
            return
        future = self._pending.get(request_id)
        if future and not future.done():
            future.set_result(action)

    @staticmethod
    def parse_live_callback(callback_data: str) -> tuple[str, ApprovalAction] | None:
        """Parse live: prefix callback data. Returns (request_id, action) or None."""
        if not callback_data.startswith("live:"):
            return None
        parts = callback_data.split(":")
        if len(parts) != 3:
            return None
        _, request_id, action_str = parts
        try:
            action = ApprovalAction(action_str)
        except ValueError:
            return None
        return request_id, action

    def _build_message(self, decision: TradeDecision, request_id: str) -> str:
        """Format trade decision as a Telegram message."""
        emoji = "🟢" if decision.direction.value == "BUY" else "🔴"
        return (
            f"{emoji} LIVE TRADE APPROVAL\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Symbol:     {decision.symbol}\n"
            f"Direction:  {decision.direction.value}\n"
            f"Confidence: {decision.confidence:.0%}\n"
            f"Entry:      {decision.entry}\n"
            f"Stop Loss:  {decision.stop_loss}\n"
            f"Take Profit:{decision.take_profit}\n"
            f"Timeframe:  {decision.timeframe}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Reasoning: {decision.reasoning[:200]}\n"
            f"Red flags: {', '.join(decision.red_flags) or 'none'}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"ID: {request_id}\n"
            f"⏰ Expires in {self._timeout}s"
        )

    def _build_keyboard(self, request_id: str) -> dict[str, Any]:
        """Build Telegram inline keyboard for approval buttons."""
        return {
            "inline_keyboard": [
                [
                    {"text": "✅ APPROVE", "callback_data": f"live:{request_id}:approve"},
                    {"text": "❌ REJECT", "callback_data": f"live:{request_id}:reject"},
                ],
                [
                    {"text": "½ HALF SIZE", "callback_data": f"live:{request_id}:half"},
                    {"text": "⏭ SKIP", "callback_data": f"live:{request_id}:skip"},
                ],
            ]
        }

    async def _send_message(self, text: str, keyboard: dict) -> int | None:
        """Send message with inline keyboard to Telegram. Returns message_id."""
        await self._rate_limit(self._chat_id)
        url = f"{TELEGRAM_API.format(token=self._token)}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "reply_markup": keyboard,
            "parse_mode": "HTML",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                self._last_send_time[self._chat_id] = time.monotonic()
                data = resp.json()
                return data.get("result", {}).get("message_id")
            logger.error("telegram_send_failed", status=resp.status_code, body=resp.text)
            return None

    async def _rate_limit(self, chat_id: str) -> None:
        """Enforce minimum interval between sends to the same chat."""
        last = self._last_send_time.get(chat_id, 0.0)
        elapsed = time.monotonic() - last
        if elapsed < MIN_SEND_INTERVAL_SECONDS:
            await asyncio.sleep(MIN_SEND_INTERVAL_SECONDS - elapsed)

    async def _edit_message(self, message_id: int, text: str) -> None:
        """Edit a Telegram message (e.g. to show timeout status)."""
        url = f"{TELEGRAM_API.format(token=self._token)}/editMessageText"
        payload = {
            "chat_id": self._chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json=payload)

    @staticmethod
    def _action_to_result(action: ApprovalAction) -> ApprovalResult:
        """Map ApprovalAction to ApprovalResult."""
        match action:
            case ApprovalAction.APPROVE:
                return ApprovalResult(action=action, approved=True, size_multiplier=1.0)
            case ApprovalAction.HALF:
                return ApprovalResult(action=action, approved=True, size_multiplier=0.5)
            case _:
                return ApprovalResult(action=action, approved=False, size_multiplier=0.0)
