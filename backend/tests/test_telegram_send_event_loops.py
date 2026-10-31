import asyncio
import json

import pytest
from telegram import request as telegram_request

from app.config import settings
from app.telegram_bot import bot as telegram_bot


@pytest.fixture
def telegram_http(monkeypatch):
    """Fake Telegram HTTP layer that binds each request object to the loop that first used it.

    A pooled httpx client behaves the same way: reusing it from a later loop raises
    "Event loop is closed". Each Celery task runs in its own asyncio.run() loop.
    """
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "123456:TEST")

    async def do_request(self, url, method, request_data=None, **kwargs):
        loop = asyncio.get_running_loop()
        if self.__dict__.setdefault("_bound_loop", loop) is not loop:
            raise RuntimeError("Event loop is closed")
        if url.endswith("/getMe"):
            result = {"id": 1, "is_bot": True, "first_name": "test", "username": "test_bot"}
        else:
            result = {"message_id": 1, "date": 0, "chat": {"id": 42, "type": "private"}}
        return 200, json.dumps({"ok": True, "result": result}).encode()

    monkeypatch.setattr(telegram_request.HTTPXRequest, "do_request", do_request)


def test_send_message_succeeds_in_each_task_event_loop(telegram_http, monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "42")

    results = [asyncio.run(telegram_bot.send_message("hello")) for _ in range(2)]

    assert results == [True, True]
