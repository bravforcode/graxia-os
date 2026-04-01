import logging
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)

_bot = None


def _get_bot():
    global _bot
    if _bot is None and settings.TELEGRAM_BOT_TOKEN:
        try:
            from telegram import Bot
            _bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        except Exception as e:
            logger.warning(f"Telegram bot init failed: {e}")
    return _bot


async def send_message(text: str, chat_id: Optional[str] = None, parse_mode: str = "Markdown") -> bool:
    bot = _get_bot()
    if not bot:
        logger.info(f"[TELEGRAM STUB] {text[:100]}")
        return False
    target = chat_id or settings.TELEGRAM_CHAT_ID
    if not target:
        return False
    try:
        await bot.send_message(chat_id=target, text=text, parse_mode=parse_mode)
        return True
    except Exception as e:
        logger.warning(f"Telegram send failed: {e}")
        return False
