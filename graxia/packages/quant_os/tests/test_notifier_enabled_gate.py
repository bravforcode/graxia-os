"""Regression tests: TradeNotifier never POSTs when disabled.

The three notify_* methods other than notify_trade previously skipped the
``_enabled`` gate and would fire live Telegram POSTs (via ``_send``) even
when the notifier was unconfigured or explicitly disabled.  ``_send`` also
guarded on a dead ``_chat_id is None`` check that could never trigger.
"""

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from graxia.packages.quant_os.autonomous.notifications import TradeNotifier


def _disabled_notifier() -> TradeNotifier:
    # Token + chat_id present, but explicitly disabled — the dangerous case:
    # every field looks configured, yet no POST may go out.
    return TradeNotifier(bot_token="t", chat_id="1", enabled=False)


@pytest.mark.asyncio
async def test_notify_kill_switch_skips_send_when_disabled():
    notifier = _disabled_notifier()
    notifier._send = AsyncMock(side_effect=AssertionError("_send called while disabled"))  # type: ignore[method-assign]
    await notifier.notify_kill_switch("test")
    notifier._send.assert_not_called()


@pytest.mark.asyncio
async def test_notify_daily_summary_skips_send_when_disabled():
    notifier = _disabled_notifier()
    notifier._send = AsyncMock(side_effect=AssertionError("_send called while disabled"))  # type: ignore[method-assign]
    await notifier.notify_daily_summary({"trades_today": 1, "mode": "paper"})
    notifier._send.assert_not_called()


@pytest.mark.asyncio
async def test_notify_error_skips_send_when_disabled():
    notifier = _disabled_notifier()
    notifier._send = AsyncMock(side_effect=AssertionError("_send called while disabled"))  # type: ignore[method-assign]
    await notifier.notify_error("component", "boom")
    notifier._send.assert_not_called()


@pytest.mark.asyncio
async def test_send_returns_before_httpx_when_disabled(monkeypatch):
    """_send's own guard is _enabled (not the dead chat_id None check)."""
    fake_httpx = MagicMock()
    fake_httpx.AsyncClient.return_value.post = AsyncMock()
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    notifier = _disabled_notifier()
    await notifier._send("text")

    fake_httpx.AsyncClient.assert_not_called()
