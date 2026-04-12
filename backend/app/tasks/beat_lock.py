"""Singleton lock for Celery beat instances."""
from __future__ import annotations

import asyncio
import os
import socket
from dataclasses import dataclass
from typing import Any

BEAT_LOCK_KEY = "beat:singleton:lock"
BEAT_LOCK_TTL = 120
BEAT_HEARTBEAT_INTERVAL = 60


@dataclass(slots=True)
class BeatLockStatus:
    owner: str | None
    ttl_seconds: int | None


class BeatSingletonLock:
    def __init__(self, redis_client: Any, instance_id: str | None = None):
        self.redis = redis_client
        self.instance_id = instance_id or f"beat:{socket.gethostname()}:{os.getpid()}"
        self._heartbeat_task: asyncio.Task[None] | None = None

    async def acquire(self) -> bool:
        acquired = await self.redis.set(BEAT_LOCK_KEY, self.instance_id, ex=BEAT_LOCK_TTL, nx=True)
        if acquired:
            self._heartbeat_task = asyncio.create_task(self._heartbeat())
        return bool(acquired)

    async def release(self) -> None:
        current = await self.redis.get(BEAT_LOCK_KEY)
        if current == self.instance_id:
            await self.redis.delete(BEAT_LOCK_KEY)
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(BEAT_HEARTBEAT_INTERVAL)
            current = await self.redis.get(BEAT_LOCK_KEY)
            if current != self.instance_id:
                os._exit(1)
            await self.redis.expire(BEAT_LOCK_KEY, BEAT_LOCK_TTL)


async def get_beat_lock_status(redis_client: Any | None) -> BeatLockStatus:
    if redis_client is None:
        return BeatLockStatus(owner=None, ttl_seconds=None)
    owner = await redis_client.get(BEAT_LOCK_KEY)
    ttl = await redis_client.ttl(BEAT_LOCK_KEY)
    return BeatLockStatus(owner=owner, ttl_seconds=ttl if ttl and ttl > 0 else None)
