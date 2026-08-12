"""
Tests for Telegram Bot Server (api/telegram_server.py).

Covers:
- Webhook endpoint returns 200
- Callback query dispatching
- Command message dispatching
- HMAC verification (valid and invalid)
- Status endpoint
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from graxia.packages.quant_os.api.telegram_server import (
    _dispatch_update,
    _verify_telegram_signature,
    set_handlers,
    telegram_router,
)

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def mock_callback_handler():
    """Create a mock TelegramCallbackHandler."""
    handler = AsyncMock()
    handler.handle_callback = AsyncMock()
    return handler


@pytest.fixture
def mock_command_handler():
    """Create a mock TelegramCommandHandler."""
    handler = AsyncMock()
    handler.handle_command = AsyncMock()
    return handler


@pytest.fixture
def app():
    """Create a minimal FastAPI app with telegram router."""
    from fastapi import FastAPI

    application = FastAPI()
    application.include_router(telegram_router)
    return application


@pytest.fixture
async def client(app):
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── HMAC Verification ─────────────────────────────────────────────


class TestHMACVerification:
    def test_verify_valid_secret(self):
        """Should return True when signature matches secret."""
        secret = "my_webhook_secret_123"
        assert _verify_telegram_signature(b"", secret, secret) is True

    def test_verify_invalid_secret(self):
        """Should return False when signature doesn't match."""
        assert _verify_telegram_signature(b"", "wrong_secret", "correct_secret") is False

    def test_verify_no_secret_configured(self):
        """Should return False when no secret configured (fail-closed)."""
        assert _verify_telegram_signature(b"", "", "") is False

    def test_verify_empty_signature_with_secret(self):
        """Should return False when secret is configured but signature is empty."""
        assert _verify_telegram_signature(b"", "", "some_secret") is False


# ── Webhook Endpoint ──────────────────────────────────────────────


class TestWebhookEndpoint:
    @pytest.mark.asyncio
    async def test_webhook_returns_200(self, client: AsyncClient):
        """Webhook should return 200 OK on valid update with valid secret."""
        secret = "test_secret_123"
        update = {"update_id": 1, "message": {"text": "hello", "chat": {"id": 123}}}

        with patch(
            "graxia.packages.quant_os.api.telegram_server._get_webhook_secret",
            return_value=secret,
        ):
            resp = await client.post(
                "/telegram/webhook",
                json=update,
                headers={"X-Telegram-Bot-Api-Secret-Token": secret},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_webhook_callback_dispatches(self, client: AsyncClient, mock_callback_handler):
        """Webhook should dispatch callback_query to callback handler."""
        secret = "test_secret_abc"
        set_handlers(callback_handler=mock_callback_handler, command_handler=AsyncMock())

        update = {
            "update_id": 2,
            "callback_query": {
                "id": "cb123",
                "data": "approve:XAUUSD:BUY",
                "message": {"message_id": 42, "chat": {"id": 123}},
            },
        }

        with patch(
            "graxia.packages.quant_os.api.telegram_server._get_webhook_secret",
            return_value=secret,
        ):
            resp = await client.post(
                "/telegram/webhook",
                json=update,
                headers={"X-Telegram-Bot-Api-Secret-Token": secret},
            )

        assert resp.status_code == 200
        mock_callback_handler.handle_callback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_webhook_command_dispatches(self, client: AsyncClient, mock_command_handler):
        """Webhook should dispatch text commands to command handler."""
        secret = "test_secret_xyz"
        set_handlers(callback_handler=AsyncMock(), command_handler=mock_command_handler)

        update = {
            "update_id": 3,
            "message": {
                "text": "/status",
                "chat": {"id": 123},
                "from": {"username": "testuser"},
            },
        }

        with patch(
            "graxia.packages.quant_os.api.telegram_server._get_webhook_secret",
            return_value=secret,
        ):
            resp = await client.post(
                "/telegram/webhook",
                json=update,
                headers={"X-Telegram-Bot-Api-Secret-Token": secret},
            )

        assert resp.status_code == 200
        mock_command_handler.handle_command.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_webhook_hmac_verification(self, client: AsyncClient):
        """Webhook should accept valid HMAC signature."""
        secret = "test_secret_abc"
        update = {"update_id": 4, "message": {"text": "hello", "chat": {"id": 1}}}

        with patch(
            "graxia.packages.quant_os.api.telegram_server._get_webhook_secret",
            return_value=secret,
        ):
            resp = await client.post(
                "/telegram/webhook",
                json=update,
                headers={"X-Telegram-Bot-Api-Secret-Token": secret},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_webhook_hmac_invalid_rejects(self, client: AsyncClient):
        """Webhook should reject invalid HMAC signature."""
        update = {"update_id": 5, "message": {"text": "hello", "chat": {"id": 1}}}

        with patch(
            "graxia.packages.quant_os.api.telegram_server._get_webhook_secret",
            return_value="correct_secret",
        ):
            resp = await client.post(
                "/telegram/webhook",
                json=update,
                headers={"X-Telegram-Bot-Api-Secret-Token": "wrong_secret"},
            )

        assert resp.status_code == 200  # Always 200 to prevent Telegram retries
        assert resp.json()["status"] == "unauthorized"


# ── Status Endpoint ───────────────────────────────────────────────


class TestStatusEndpoint:
    @pytest.mark.asyncio
    async def test_status_endpoint(self, client: AsyncClient):
        """Status endpoint should return bot configuration."""
        with (
            patch(
                "graxia.packages.quant_os.api.telegram_server._get_bot_token",
                return_value="test_token",
            ),
            patch(
                "graxia.packages.quant_os.api.telegram_server._get_webhook_secret",
                return_value="secret",
            ),
            patch(
                "graxia.packages.quant_os.api.telegram_server._get_authorized_chat_id",
                return_value="12345",
            ),
        ):
            resp = await client.get("/telegram/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["bot_configured"] is True
        assert data["webhook_secret_configured"] is True
        assert data["authorized_chat_id"] == "12345"

    @pytest.mark.asyncio
    async def test_status_endpoint_no_config(self, client: AsyncClient):
        """Status endpoint should show unconfigured when env vars missing."""
        with (
            patch(
                "graxia.packages.quant_os.api.telegram_server._get_bot_token",
                return_value="",
            ),
            patch(
                "graxia.packages.quant_os.api.telegram_server._get_webhook_secret",
                return_value="",
            ),
            patch(
                "graxia.packages.quant_os.api.telegram_server._get_authorized_chat_id",
                return_value="",
            ),
        ):
            resp = await client.get("/telegram/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["bot_configured"] is False
        assert data["webhook_secret_configured"] is False


# ── Dispatch Unit Tests ───────────────────────────────────────────


class TestDispatchUpdate:
    @pytest.mark.asyncio
    async def test_dispatch_callback(self, mock_callback_handler):
        """_dispatch_update should route callback_query to callback handler."""
        set_handlers(callback_handler=mock_callback_handler, command_handler=AsyncMock())

        update = {
            "callback_query": {
                "id": "cb1",
                "data": "approve:XAUUSD:BUY",
                "message": {"message_id": 1},
            }
        }
        await _dispatch_update(update)
        mock_callback_handler.handle_callback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatch_command(self, mock_command_handler):
        """_dispatch_update should route text commands to command handler."""
        set_handlers(callback_handler=AsyncMock(), command_handler=mock_command_handler)

        update = {
            "message": {
                "text": "/status",
                "chat": {"id": 123},
                "from": {"username": "user"},
            }
        }
        await _dispatch_update(update)
        mock_command_handler.handle_command.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatch_non_command_message_ignored(self, mock_command_handler):
        """_dispatch_update should ignore non-command text messages."""
        set_handlers(callback_handler=AsyncMock(), command_handler=mock_command_handler)

        update = {
            "message": {
                "text": "hello world",
                "chat": {"id": 123},
                "from": {"username": "user"},
            }
        }
        await _dispatch_update(update)
        mock_command_handler.handle_command.assert_not_awaited()
