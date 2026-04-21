"""Singleton lock for Telegram polling workers."""
from __future__ import annotations

import asyncio
import os
import socket
from typing import Any

TELEGRAM_POLLING_LOCK_KEY = "telegram:polling:singleton:lock"
TELEGRAM_POLLING_LOCK_TTL = 120
TELEGRAM_POLLING_HEARTBEAT_INTERVAL = 60


class TelegramPollingSingletonLock:
    def __init__(self, redis_client: Any, instance_id: str | None = None):
        self.redis = redis_client
        self.instance_id = instance_id or f"telegram:{socket.gethostname()}:{os.getpid()}"
        self._heartbeat_task: asyncio.Task[None] | None = None

    async def acquire(self) -> bool:
        acquired = await self.redis.set(
            TELEGRAM_POLLING_LOCK_KEY,
            self.instance_id,
            ex=TELEGRAM_POLLING_LOCK_TTL,
            nx=True,
        )
        if acquired:
            self._heartbeat_task = asyncio.create_task(self._heartbeat())
        return bool(acquired)

    async def release(self) -> None:
        current = await self.redis.get(TELEGRAM_POLLING_LOCK_KEY)
        if current == self.instance_id:
            await self.redis.delete(TELEGRAM_POLLING_LOCK_KEY)
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(TELEGRAM_POLLING_HEARTBEAT_INTERVAL)
            try:
                current = await self.redis.get(TELEGRAM_POLLING_LOCK_KEY)
                if current != self.instance_id:
                    return
                await self.redis.expire(TELEGRAM_POLLING_LOCK_KEY, TELEGRAM_POLLING_LOCK_TTL)
            except Exception:
                continue
