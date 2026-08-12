"""
Tests for Telegram Command Handler (api/telegram_commands.py).

Covers:
- Authorization check (authorized vs unauthorized)
- /status, /positions, /pnl, /kill, /resume, /help commands
- Unknown command handling
- Callback handling (kill confirmation)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from graxia.packages.quant_os.api.telegram_commands import TelegramCommandHandler

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def handler() -> TelegramCommandHandler:
    """Create a handler with mocked token and authorized chat_id."""
    return TelegramCommandHandler(
        token="test_bot_token",
        authorized_chat_id="12345",
    )


@pytest.fixture
def mock_state_store() -> SimpleNamespace:
    """Create a mock state store."""
    return SimpleNamespace(
        system_state="RUNNING",
        kill_switch_active=False,
        daily_pnl=127.50,
        weekly_pnl=450.00,
        peak_equity=10500.00,
        current_drawdown_pct=2.15,
    )


@pytest.fixture
def mock_ledger() -> MagicMock:
    """Create a mock ledger."""
    ledger = MagicMock()
    ledger.get_open_positions.return_value = [
        {
            "symbol": "XAUUSD",
            "side": "LONG",
            "entry_price": 2345.50,
            "unrealized_pnl": 85.00,
        },
    ]
    return ledger


@pytest.fixture
def mock_config() -> SimpleNamespace:
    """Create a mock config."""
    return SimpleNamespace(
        trading_mode="PAPER",
        max_risk_per_trade_pct=2.0,
        max_daily_loss_pct=5.0,
        max_drawdown_pct=10.0,
        max_positions=5,
    )


def _make_message(text: str, chat_id: str = "12345", username: str = "testuser") -> dict:
    """Build a Telegram message dict."""
    return {
        "text": text,
        "chat": {"id": int(chat_id)},
        "from": {"username": username},
        "message_id": 1,
    }


def _make_callback(data: str, chat_id: str = "12345") -> dict:
    """Build a Telegram callback_query dict."""
    return {
        "id": "cb_001",
        "data": data,
        "message": {
            "message_id": 42,
            "chat": {"id": int(chat_id)},
        },
    }


# ── Authorization ─────────────────────────────────────────────────


class TestAuthorization:
    @pytest.mark.asyncio
    async def test_authorized_command_accepted(self, handler: TelegramCommandHandler):
        """Authorized chat_id should be processed normally."""
        handler._send = AsyncMock(return_value=True)
        msg = _make_message("/help", chat_id="12345")

        await handler.handle_command(msg)
        handler._send.assert_awaited()
        # Should not contain "Unauthorized"
        call_args = handler._send.call_args[0]
        assert "Unauthorized" not in call_args[1]

    @pytest.mark.asyncio
    async def test_unauthorized_command_rejected(self, handler: TelegramCommandHandler):
        """Unauthorized chat_id should get rejection message."""
        handler._send = AsyncMock(return_value=True)
        msg = _make_message("/status", chat_id="99999")

        await handler.handle_command(msg)
        handler._send.assert_awaited_once()
        call_args = handler._send.call_args[0]
        assert "Unauthorized" in call_args[1]


# ── Command Handlers ──────────────────────────────────────────────


class TestCommands:
    @pytest.mark.asyncio
    async def test_status_command(self, handler: TelegramCommandHandler, mock_state_store, mock_config):
        """/status should return system status info."""
        handler._state_store = mock_state_store
        handler._config = mock_config
        handler._send = AsyncMock(return_value=True)

        await handler.handle_command(_make_message("/status"))
        handler._send.assert_awaited_once()
        text = handler._send.call_args[0][1]
        assert "System Status" in text
        assert "RUNNING" in text

    @pytest.mark.asyncio
    async def test_positions_command(self, handler: TelegramCommandHandler, mock_ledger):
        """/positions should list open positions."""
        handler._ledger = mock_ledger
        handler._send = AsyncMock(return_value=True)

        await handler.handle_command(_make_message("/positions"))
        handler._send.assert_awaited_once()
        text = handler._send.call_args[0][1]
        assert "XAUUSD" in text
        assert "LONG" in text

    @pytest.mark.asyncio
    async def test_positions_no_ledger(self, handler: TelegramCommandHandler):
        """/positions without ledger should inform user."""
        handler._ledger = None
        handler._send = AsyncMock(return_value=True)

        await handler.handle_command(_make_message("/positions"))
        handler._send.assert_awaited_once()
        text = handler._send.call_args[0][1]
        assert "No ledger" in text

    @pytest.mark.asyncio
    async def test_pnl_command(self, handler: TelegramCommandHandler, mock_state_store):
        """/pnl should show P&L summary."""
        handler._state_store = mock_state_store
        handler._send = AsyncMock(return_value=True)

        await handler.handle_command(_make_message("/pnl"))
        handler._send.assert_awaited_once()
        text = handler._send.call_args[0][1]
        assert "P&L" in text
        assert "127.50" in text or "+127.50" in text

    @pytest.mark.asyncio
    async def test_kill_command_sends_confirmation(self, handler: TelegramCommandHandler):
        """/kill should send confirmation keyboard, not activate immediately."""
        handler._send = AsyncMock(return_value=True)

        await handler.handle_command(_make_message("/kill"))
        handler._send.assert_awaited_once()

        # Check that reply_markup with inline keyboard was passed
        call_kwargs = handler._send.call_args[1]
        assert "reply_markup" in call_kwargs
        markup = call_kwargs["reply_markup"]
        assert "inline_keyboard" in markup
        # Should contain confirm and cancel buttons
        buttons = markup["inline_keyboard"][0]
        callback_data = [b["callback_data"] for b in buttons]
        assert "kill:confirm" in callback_data
        assert "kill:cancel" in callback_data

    @pytest.mark.asyncio
    async def test_resume_command(self, handler: TelegramCommandHandler, mock_state_store):
        """/resume should send confirmation keyboard, not activate immediately."""
        mock_state_store.kill_switch_active = True
        handler._state_store = mock_state_store
        handler._send = AsyncMock(return_value=True)

        await handler.handle_command(_make_message("/resume"))
        handler._send.assert_awaited_once()

        # Check that reply_markup with inline keyboard was passed
        call_kwargs = handler._send.call_args[1]
        assert "reply_markup" in call_kwargs
        markup = call_kwargs["reply_markup"]
        assert "inline_keyboard" in markup
        # Should contain confirm and cancel buttons
        buttons = markup["inline_keyboard"][0]
        callback_data = [b["callback_data"] for b in buttons]
        assert "resume:confirm" in callback_data
        assert "resume:cancel" in callback_data

    @pytest.mark.asyncio
    async def test_resume_not_active(self, handler: TelegramCommandHandler, mock_state_store):
        """/resume when kill switch is off should inform user."""
        mock_state_store.kill_switch_active = False
        handler._state_store = mock_state_store
        handler._send = AsyncMock(return_value=True)

        await handler.handle_command(_make_message("/resume"))
        handler._send.assert_awaited_once()
        text = handler._send.call_args[0][1]
        assert "not active" in text.lower()

    @pytest.mark.asyncio
    async def test_help_command(self, handler: TelegramCommandHandler):
        """/help should list all available commands."""
        handler._send = AsyncMock(return_value=True)

        await handler.handle_command(_make_message("/help"))
        handler._send.assert_awaited_once()
        text = handler._send.call_args[0][1]
        assert "/status" in text
        assert "/positions" in text
        assert "/pnl" in text
        assert "/kill" in text
        assert "/resume" in text
        assert "/help" in text

    @pytest.mark.asyncio
    async def test_unknown_command(self, handler: TelegramCommandHandler):
        """Unknown commands should get a helpful response."""
        handler._send = AsyncMock(return_value=True)

        await handler.handle_command(_make_message("/foobar"))
        handler._send.assert_awaited_once()
        text = handler._send.call_args[0][1]
        assert "Unknown" in text or "unknown" in text
        assert "/help" in text

    @pytest.mark.asyncio
    async def test_bot_username_suffix_stripped(self, handler: TelegramCommandHandler):
        """Commands like /status@mybot should be handled."""
        handler._send = AsyncMock(return_value=True)

        await handler.handle_command(_make_message("/help@graxia_bot"))
        handler._send.assert_awaited_once()
        text = handler._send.call_args[0][1]
        assert "Available Commands" in text


# ── Callback Handling ─────────────────────────────────────────────


class TestCallbackHandling:
    @pytest.mark.asyncio
    async def test_kill_confirm_activates(self, handler: TelegramCommandHandler, mock_state_store):
        """kill:confirm callback should activate kill switch."""
        handler._state_store = mock_state_store
        handler._send = AsyncMock(return_value=True)
        handler._answer_callback = AsyncMock()
        handler._edit_last_message = AsyncMock()

        cb = _make_callback("kill:confirm")
        await handler.handle_callback(cb)

        assert mock_state_store.kill_switch_active is True
        assert mock_state_store.system_state == "HALTED"

    @pytest.mark.asyncio
    async def test_kill_cancel(self, handler: TelegramCommandHandler):
        """kill:cancel callback should not activate kill switch."""
        handler._send = AsyncMock(return_value=True)
        handler._answer_callback = AsyncMock()
        handler._edit_last_message = AsyncMock()

        cb = _make_callback("kill:cancel")
        await handler.handle_callback(cb)

        handler._answer_callback.assert_awaited_once()
        handler._edit_last_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_callback_unauthorized_rejected(self, handler: TelegramCommandHandler):
        """Unauthorized callback should be rejected."""
        handler._answer_callback = AsyncMock()

        cb = _make_callback("kill:confirm", chat_id="99999")
        await handler.handle_callback(cb)

        handler._answer_callback.assert_awaited_once()
        args = handler._answer_callback.call_args[0]
        assert "Unauthorized" in args[1]

    @pytest.mark.asyncio
    async def test_resume_confirm_activates(self, handler: TelegramCommandHandler, mock_state_store):
        """resume:confirm callback should deactivate kill switch."""
        mock_state_store.kill_switch_active = True
        handler._state_store = mock_state_store
        handler._send = AsyncMock(return_value=True)
        handler._answer_callback = AsyncMock()
        handler._edit_last_message = AsyncMock()

        cb = _make_callback("resume:confirm")
        await handler.handle_callback(cb)

        assert mock_state_store.kill_switch_active is False
        assert mock_state_store.system_state == "RUNNING"

    @pytest.mark.asyncio
    async def test_resume_cancel(self, handler: TelegramCommandHandler):
        """resume:cancel callback should not activate resume."""
        handler._send = AsyncMock(return_value=True)
        handler._answer_callback = AsyncMock()
        handler._edit_last_message = AsyncMock()

        cb = _make_callback("resume:cancel")
        await handler.handle_callback(cb)

        handler._answer_callback.assert_awaited_once()
        handler._edit_last_message.assert_awaited_once()
