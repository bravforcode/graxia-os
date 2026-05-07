"""Telegram bot package."""
from app.telegram_bot.bot import (
    get_application,
    send_approval_request,
    send_message,
    setup_bot,
    start_polling,
    stop_polling,
)

__all__ = [
    "setup_bot",
    "send_message",
    "send_approval_request",
    "start_polling",
    "stop_polling",
    "get_application"
]
