from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Protocol


WorkerRiskLevel = Literal["READ_ONLY", "LOW_WRITE", "APPROVAL_REQUIRED", "DANGEROUS_BLOCKED"]


@dataclass(slots=True)
class WorkerExecutionContext:
    organization_id: str
    correlation_id: str
    actor_type: str = "agent"
    actor_id: str | None = None
    environment: str = "local"


@dataclass(slots=True)
class WorkerCapabilityResult:
    ok: bool
    risk_level: WorkerRiskLevel
    approval_required: bool
    data: dict[str, Any] | None = None
    error: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "risk_level": self.risk_level,
            "approval_required": self.approval_required,
            "data": self.data or {},
            "error": self.error,
        }


class WorkerCapability(Protocol):
    name: str
    risk_level: WorkerRiskLevel

    async def execute(
        self,
        payload: dict[str, Any],
        context: WorkerExecutionContext,
    ) -> WorkerCapabilityResult: ...


CapabilityExecutor = Callable[[dict[str, Any], WorkerExecutionContext], Awaitable[WorkerCapabilityResult]]
