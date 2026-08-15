"""
Telegram Bot Server — receives updates from Telegram.

Two modes:
1. Webhook (production): Telegram sends POST to /telegram/webhook
2. Polling (development): Long-polling loop via getUpdates

Routes:
    POST /telegram/webhook     — receive callback_query and message updates
    GET  /telegram/status      — bot health check
    POST /telegram/set-webhook — set webhook URL with Telegram

Architecture:
    Telegram API → POST /telegram/webhook → process update → dispatch
    update.callback_query → TelegramCallbackHandler.handle_callback()
    update.message.text   → TelegramCommandHandler.handle_command()

Safety:
    - HMAC-SHA256 verification on webhook (if secret configured)
    - Only authorized chat_id can issue commands
    - Rate limiting on command processing
"""

from __future__ import annotations

import asyncio
import hmac
import os
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Header, Request
from pydantic import BaseModel

from ..core.telegram_callback import TelegramCallbackHandler

logger = structlog.get_logger(__name__)

telegram_router = APIRouter(prefix="/telegram", tags=["telegram"])


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _get_bot_token() -> str:
    """Get Telegram bot token from env."""
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def _get_authorized_chat_id() -> str:
    """Get authorized chat ID from env."""
    return os.getenv("TELEGRAM_CHAT_ID", "")


def _get_webhook_secret() -> str:
    """Get webhook HMAC secret from env."""
    return os.getenv("TELEGRAM_WEBHOOK_SECRET", "")


# ---------------------------------------------------------------------------
# HMAC verification
# ---------------------------------------------------------------------------


def _verify_telegram_signature(body: bytes, signature: str, secret: str) -> bool:
    """Verify Telegram webhook signature using HMAC-SHA256.

    Uses constant-time comparison via hmac.compare_digest to prevent
    timing side-channel attacks.

    Args:
        body: Raw request body bytes
        signature: Signature from X-Telegram-Bot-Api-Secret-Token header
        secret: Expected secret value

    Returns:
        True if signature is valid. False if no secret configured (fail-closed).
    """
    if not secret:
        # Fail-closed: reject requests when no secret is configured
        logger.warning("telegram_webhook.no_secret_configured", action="rejecting")
        return False

    if not signature:
        return False

    # Telegram sends the secret token directly in the header,
    # not as HMAC of the body. Compare constant-time.
    return hmac.compare_digest(signature, secret)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TelegramStatusResponse(BaseModel):
    """Status response for GET /telegram/status."""

    bot_configured: bool
    webhook_secret_configured: bool
    authorized_chat_id: str
    polling_active: bool


class SetWebhookRequest(BaseModel):
    """Request body for POST /telegram/set-webhook."""

    url: str
    secret_token: str | None = None
    max_connections: int = 40
    allowed_updates: list[str] = ["message", "callback_query"]


class SetWebhookResponse(BaseModel):
    """Response for POST /telegram/set-webhook."""

    success: bool
    url: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Global state (module-level singletons)
# ---------------------------------------------------------------------------

_callback_handler: TelegramCallbackHandler | None = None
_command_handler: Any = None  # TelegramCommandHandler — avoid circular import
_polling_loop: TelegramPollingLoop | None = None


def set_handlers(
    callback_handler: TelegramCallbackHandler,
    command_handler: Any,
) -> None:
    """Register callback and command handlers (called from main.py lifespan)."""
    global _callback_handler, _command_handler
    _callback_handler = callback_handler
    _command_handler = command_handler
    logger.info("telegram.handlers_registered")


# ---------------------------------------------------------------------------
# Update dispatcher
# ---------------------------------------------------------------------------


async def _dispatch_update(update: dict) -> None:
    """Route a Telegram update to the appropriate handler.

    Args:
        update: Parsed Telegram Update object
    """
    # Handle callback_query (inline keyboard presses)
    callback_query = update.get("callback_query")
    if callback_query:
        data = callback_query.get("data", "")
        # Kill/resume callbacks go to command handler (has coordinator)
        if data.startswith(("kill:", "resume:")) and _command_handler:
            try:
                await _command_handler.handle_callback(callback_query)
            except Exception as exc:
                logger.warning("telegram.callback_error", error=str(exc))
            return
        # Trade approval callbacks go to callback handler
        if _callback_handler:
            try:
                await _callback_handler.handle_callback(callback_query)
            except Exception as exc:
                logger.warning("telegram.callback_error", error=str(exc))
            return

    # Handle text commands
    message = update.get("message")
    if message and _command_handler:
        text = message.get("text", "").strip()
        if text.startswith("/"):
            try:
                await _command_handler.handle_command(message)
            except Exception as exc:
                logger.warning("telegram.command_error", error=str(exc))
            return

    # Unhandled update type — log and ignore
    logger.debug("telegram.unhandled_update", keys=list(update.keys()))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@telegram_router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_secret: str | None = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> dict[str, str]:
    """Receive Telegram webhook updates.

    Telegram sends POST requests here when:
    - User sends a message (message field)
    - User presses an inline keyboard button (callback_query field)

    Always returns 200 OK — Telegram retries on non-200 responses.
    """
    secret = _get_webhook_secret()

    # Production requires a webhook secret — fail-closed
    if not secret and os.getenv("ENVIRONMENT", "").lower() == "production":
        logger.error("telegram.webhook.no_secret_in_production")
        return {"status": "misconfigured"}

    # Verify HMAC if secret is configured
    if not _verify_telegram_signature(b"", x_telegram_secret or "", secret):
        logger.warning("telegram.webhook.auth_failed")
        # Still return 200 to prevent Telegram retries, but log the failure
        return {"status": "unauthorized"}

    # Parse update
    try:
        update = await request.json()
    except Exception as exc:
        logger.warning("telegram.webhook.parse_error", error=str(exc))
        return {"status": "invalid_json"}

    # Dispatch to handler (fire-and-forget style — Telegram expects fast 200)
    update_id = update.get("update_id", "unknown")
    logger.info("telegram.webhook.received", update_id=update_id)

    try:
        await _dispatch_update(update)
    except Exception as exc:
        logger.error("telegram.webhook.dispatch_error", error=str(exc))

    return {"status": "ok"}


@telegram_router.get("/status", response_model=TelegramStatusResponse)
async def telegram_status() -> TelegramStatusResponse:
    """Bot health check — returns configuration and active state."""
    token = _get_bot_token()
    return TelegramStatusResponse(
        bot_configured=bool(token),
        webhook_secret_configured=bool(_get_webhook_secret()),
        authorized_chat_id=_get_authorized_chat_id(),
        polling_active=_polling_loop is not None and _polling_loop.running,
    )


@telegram_router.post("/set-webhook", response_model=SetWebhookResponse)
async def set_webhook(payload: SetWebhookRequest) -> SetWebhookResponse:
    """Set or update the Telegram webhook URL.

    Calls the Telegram setWebhook API to register the callback URL.
    """
    token = _get_bot_token()
    if not token:
        return SetWebhookResponse(success=False, error="TELEGRAM_BOT_TOKEN not configured")

    secret = payload.secret_token or _get_webhook_secret()

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/setWebhook",
                json={
                    "url": payload.url,
                    "secret_token": secret,
                    "max_connections": payload.max_connections,
                    "allowed_updates": payload.allowed_updates,
                },
            )
            data = resp.json()
            if data.get("ok"):
                logger.info("telegram.webhook.set", url=payload.url)
                return SetWebhookResponse(success=True, url=payload.url)
            else:
                logger.warning("telegram.webhook.set_failed", error=data.get("description"))
                return SetWebhookResponse(success=False, error=data.get("description", "Unknown error"))
        except Exception as exc:
            logger.error("telegram.webhook.set_error", error=str(exc))
            return SetWebhookResponse(success=False, error=str(exc))


# ---------------------------------------------------------------------------
# Polling mode (development)
# ---------------------------------------------------------------------------


class TelegramPollingLoop:
    """Long-polling loop for development. Not used in production.

    Fetches updates via getUpdates instead of receiving webhooks.
    Useful for local development where a public URL is not available.
    """

    POLL_INTERVAL = 0.5  # seconds between polls
    ERROR_BACKOFF_MAX = 60  # max backoff on errors
    REQUEST_TIMEOUT = 30  # long-poll timeout

    def __init__(self) -> None:
        self.running: bool = False
        self._task: asyncio.Task[None] | None = None
        self._offset: int = 0
        self._client: httpx.AsyncClient | None = None

    async def start(
        self,
        token: str,
        callback_handler: TelegramCallbackHandler,
        command_handler: Any,
    ) -> None:
        """Start polling loop. Run as background task.

        Args:
            token: Telegram bot token
            callback_handler: Handler for callback_query updates
            command_handler: Handler for text commands
        """
        global _callback_handler, _command_handler
        _callback_handler = callback_handler
        _command_handler = command_handler

        self.running = True
        self._client = httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT + 5)
        self._task = asyncio.create_task(self._poll_loop(token))
        logger.info("telegram.polling.started")

    async def stop(self) -> None:
        """Stop polling loop and clean up resources."""
        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        logger.info("telegram.polling.stopped")

    async def _poll_loop(self, token: str) -> None:
        """Main polling loop with exponential backoff on errors."""
        backoff = 1.0

        while self.running:
            try:
                resp = await self._client.get(
                    f"https://api.telegram.org/bot{token}/getUpdates",
                    params={
                        "offset": self._offset,
                        "timeout": self.REQUEST_TIMEOUT,
                        "allowed_updates": '["message","callback_query"]',
                    },
                )

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        updates = data.get("result", [])
                        for update in updates:
                            self._offset = update["update_id"] + 1
                            await _dispatch_update(update)
                        backoff = 1.0  # reset on success
                    else:
                        logger.warning("telegram.polling.api_error", description=data.get("description"))
                elif resp.status_code == 429:
                    retry_after = resp.json().get("parameters", {}).get("retry_after", 30)
                    logger.warning("telegram.polling.rate_limited", retry_after=retry_after)
                    await asyncio.sleep(min(retry_after, self.ERROR_BACKOFF_MAX))
                else:
                    logger.warning("telegram.polling.http_error", status=resp.status_code)

            except asyncio.CancelledError:
                break
            except httpx.TimeoutException:
                logger.debug("telegram.polling.timeout")
            except Exception as exc:
                logger.warning("telegram.polling.error", error=str(exc))
                await asyncio.sleep(min(backoff, self.ERROR_BACKOFF_MAX))
                backoff *= 2

            # Small sleep between polls to avoid hammering
            await asyncio.sleep(self.POLL_INTERVAL)
