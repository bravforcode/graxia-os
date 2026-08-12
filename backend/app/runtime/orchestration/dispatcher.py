from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass
class QueueDispatchRequest:
    workflow_name: str
    organization_id: str
    correlation_id: str
    business_event_id: str | None
    context_packet_id: str | None
    inputs: dict[str, Any]


@dataclass
class QueueDispatchReceipt:
    workflow_run_id: str
    status: str = "queued"
    summary: str = "Workflow queued for later execution"


QueueExecutor = Callable[[QueueDispatchRequest], Awaitable[QueueDispatchReceipt]]


class RuntimeWorkflowDispatcher:
    def __init__(self, queue_executor: QueueExecutor | None = None) -> None:
        self._queue_executor = queue_executor

    async def dispatch_to_queue(self, request: QueueDispatchRequest) -> QueueDispatchReceipt:
        if self._queue_executor is None:
            raise RuntimeError("queue execution requested but no queue executor configured")
        return await self._queue_executor(request)
