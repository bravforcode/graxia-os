from __future__ import annotations

from typing import Awaitable, Callable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.runtime.contracts import TaskEnvelope, TaskStatus, TaskTarget
from app.runtime.gateway.errors import DispatchExecutionError

DispatchExecutor = Callable[[TaskEnvelope], Awaitable["DispatchResult"]]


class DispatchResult(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    target: TaskTarget
    status: TaskStatus
    summary: str
    error_message: str | None = Field(default=None, alias="errorMessage")
    run_id: UUID | None = Field(default=None, alias="runId")


class GatewayDispatcher:
    def __init__(self, executor: DispatchExecutor | None = None) -> None:
        self._executor = executor

    async def dispatch(self, task: TaskEnvelope) -> DispatchResult:
        if self._executor is not None:
            return await self._executor(task)
        if task.payload.get("force_failure"):
            raise DispatchExecutionError(
                str(task.payload.get("force_failure_message") or "forced dispatch failure")
            )
        return DispatchResult(
            target=task.target,
            status=TaskStatus.COMPLETED,
            summary=f"Dispatched {task.task_type} to {task.target}",
        )
