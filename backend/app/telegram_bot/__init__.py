"""Telegram bot package."""
from app.telegram_bot.bot import (
    setup_bot,
    send_message,
    send_approval_request,
    start_polling,
    stop_polling,
    get_application
)

__all__ = [
    "setup_bot",
    "send_message",
    "send_approval_request",
    "start_polling",
    "stop_polling",
    "get_application"
]
