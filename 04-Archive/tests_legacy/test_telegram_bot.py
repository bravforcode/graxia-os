"""
Tests for Telegram bot functionality.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.telegram_bot.bot import (
    send_message,
    send_approval_request,
    setup_bot
)


@pytest.mark.asyncio
async def test_setup_bot_without_token():
    """Test bot setup without token."""
    with patch('app.telegram_bot.bot.settings') as mock_settings:
        mock_settings.TELEGRAM_BOT_TOKEN = None
        
        bot = setup_bot()
        assert bot is None


@pytest.mark.asyncio
async def test_setup_bot_with_token():
    """Test bot setup with token."""
    with patch('app.telegram_bot.bot.settings') as mock_settings:
        mock_settings.TELEGRAM_BOT_TOKEN = "test_token"
        
        bot = setup_bot()
        assert bot is not None


@pytest.mark.asyncio
async def test_send_message_without_app():
    """Test sending message without initialized app."""
    with patch('app.telegram_bot.bot._app', None):
        result = await send_message("Test message")
        assert result is False


@pytest.mark.asyncio
async def test_send_message_with_app():
    """Test sending message with initialized app."""
    mock_app = MagicMock()
    mock_app.bot.send_message = AsyncMock()
    
    with patch('app.telegram_bot.bot._app', mock_app):
        with patch('app.telegram_bot.bot.settings') as mock_settings:
            mock_settings.TELEGRAM_CHAT_ID = "123456"
            
            result = await send_message("Test message")
            assert result is True
            mock_app.bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_send_approval_request():
    """Test sending approval request."""
    mock_app = MagicMock()
    mock_app.bot.send_message = AsyncMock()
    
    with patch('app.telegram_bot.bot._app', mock_app):
        with patch('app.telegram_bot.bot.settings') as mock_settings:
            mock_settings.TELEGRAM_CHAT_ID = "123456"
            
            result = await send_approval_request(
                request_id="test-id",
                description="Test action",
                action_type="test"
            )
            assert result is True
            mock_app.bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_command_handlers():
    """Test that command handlers are registered."""
    with patch('app.telegram_bot.bot.settings') as mock_settings:
        mock_settings.TELEGRAM_BOT_TOKEN = "test_token"
        
        bot = setup_bot()
        assert bot is not None
        
        # Check handlers are registered
        handlers = bot.handlers
        assert len(handlers) > 0
