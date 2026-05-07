"""Redis-backed dead-letter queue helpers."""
from __future__ import annotations

import asyncio
import json
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.core.monitoring import metrics_collector
from app.telegram_bot.bot import send_message

DLQ_KEY = "celery:dlq"
_memory_dlq: deque[str] = deque()


def reset_dlq_state() -> None:
    _memory_dlq.clear()


@dataclass(slots=True)
class DLQMessage:
    task_name: str
    args: list[Any] = field(default_factory=list)
    kwargs: dict[str, Any] = field(default_factory=dict)
    exception: str = ""
    traceback: str = ""
    original_queue: str | None = None
    failed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    message_id: str = field(default_factory=lambda: str(uuid4()))
    retries: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, default=str)

    @classmethod
    def from_json(cls, payload: str) -> DLQMessage:
        return cls(**json.loads(payload))


class DeadLetterQueue:
    def __init__(self, redis_client: Any | None = None):
        self.redis = redis_client

    async def push(self, message: DLQMessage) -> None:
        payload = message.to_json()
        if self.redis is not None:
            await self.redis.lpush(DLQ_KEY, payload)
            depth = int(await self.redis.llen(DLQ_KEY) or 0)
        else:
            _memory_dlq.appendleft(payload)
            depth = len(_memory_dlq)
        metrics_collector.set_dlq_depth(depth)
        if depth > 100:
            try:
                await send_message(
                    f"HIGH DLQ depth alert: {depth} failed task(s) waiting for replay.",
                    parse_mode=None,
                )
            except Exception:
                pass

    async def list_messages(self, offset: int = 0, limit: int = 20) -> list[DLQMessage]:
        if self.redis is not None:
            raw = await self.redis.lrange(DLQ_KEY, offset, offset + limit - 1)
            return [DLQMessage.from_json(item) for item in raw]
        items = list(_memory_dlq)[offset : offset + limit]
        return [DLQMessage.from_json(item) for item in items]

    async def get_depth(self) -> int:
        if self.redis is not None:
            depth = int(await self.redis.llen(DLQ_KEY) or 0)
            metrics_collector.set_dlq_depth(depth)
            return depth
        depth = len(_memory_dlq)
        metrics_collector.set_dlq_depth(depth)
        return depth

    async def replay_message(self, message_id: str, *, operator_id: str) -> bool:
        message = await self._find_message(message_id)
        if message is None:
            return False
        from app.tasks.celery_app import celery_app

        celery_app.send_task(
            message.task_name,
            args=message.args,
            kwargs=message.kwargs,
            queue=message.original_queue or "default",
        )
        await self._remove_message(message_id)
        try:
            await send_message(
                f"DLQ replay initiated by {operator_id} for `{message.task_name}` ({message_id}).",
                parse_mode=None,
            )
        except Exception:
            pass
        return True

    async def _find_message(self, message_id: str) -> DLQMessage | None:
        for message in await self.list_messages(0, 1000):
            if message.message_id == message_id:
                return message
        return None

    async def _remove_message(self, message_id: str) -> None:
        if self.redis is not None:
            items = await self.redis.lrange(DLQ_KEY, 0, -1)
            for item in items:
                message = DLQMessage.from_json(item)
                if message.message_id == message_id:
                    await self.redis.lrem(DLQ_KEY, 1, item)
                    return
            return
        for item in list(_memory_dlq):
            message = DLQMessage.from_json(item)
            if message.message_id == message_id:
                _memory_dlq.remove(item)
                return


def record_dlq_failure(
    *,
    task_name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    exception: Exception,
    traceback_text: str,
    original_queue: str | None = None,
    retries: int = 0,
) -> None:
    message = DLQMessage(
        task_name=task_name,
        args=list(args),
        kwargs=kwargs,
        exception=str(exception),
        traceback=traceback_text,
        original_queue=original_queue,
        retries=retries,
    )
    try:
        from app.tasks.queues import get_sync_redis_client

        redis_client = get_sync_redis_client()
        if redis_client is not None:
            redis_client.lpush(DLQ_KEY, message.to_json())
            return
    except Exception:
        pass
    _memory_dlq.appendleft(message.to_json())


def replay_dlq_message_sync(message_id: str, operator_id: str, redis_client: Any | None = None) -> bool:
    queue = DeadLetterQueue(redis_client)
    return asyncio.run(queue.replay_message(message_id, operator_id=operator_id))
