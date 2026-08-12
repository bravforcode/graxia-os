from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .capabilities import CapabilityExecutor, WorkerCapabilityResult, WorkerExecutionContext
from .mock_provider import RuntimeWorkerMockProvider


@dataclass(slots=True)
class RegisteredWorkerCapability:
    name: str
    risk_level: str
    executor: CapabilityExecutor


class RuntimeWorkerService:
    """Runtime-safe worker capability layer with deterministic mock execution."""

    def __init__(self, provider: RuntimeWorkerMockProvider | None = None) -> None:
        self.provider = provider or RuntimeWorkerMockProvider()
        self._capabilities = {
            "summarize_order": RegisteredWorkerCapability(
                name="summarize_order",
                risk_level="READ_ONLY",
                executor=self._execute_summarize_order,
            ),
            "draft_customer_reply": RegisteredWorkerCapability(
                name="draft_customer_reply",
                risk_level="APPROVAL_REQUIRED",
                executor=self._execute_draft_customer_reply,
            ),
            "classify_lead": RegisteredWorkerCapability(
                name="classify_lead",
                risk_level="READ_ONLY",
                executor=self._execute_classify_lead,
            ),
            "prepare_recommendation": RegisteredWorkerCapability(
                name="prepare_recommendation",
                risk_level="APPROVAL_REQUIRED",
                executor=self._execute_prepare_recommendation,
            ),
            "write_memory_draft": RegisteredWorkerCapability(
                name="write_memory_draft",
                risk_level="LOW_WRITE",
                executor=self._execute_write_memory_draft,
            ),
            "propose_tool_call": RegisteredWorkerCapability(
                name="propose_tool_call",
                risk_level="LOW_WRITE",
                executor=self._execute_propose_tool_call,
            ),
        }

    def list_capabilities(self) -> list[str]:
        return sorted(self._capabilities.keys())

    async def execute(
        self,
        capability_name: str,
        payload: dict[str, Any],
        context: WorkerExecutionContext,
    ) -> dict[str, Any]:
        capability = self._capabilities.get(capability_name)
        if capability is None:
            return WorkerCapabilityResult(
                ok=False,
                risk_level="DANGEROUS_BLOCKED",
                approval_required=False,
                error={
                    "code": "UNKNOWN_CAPABILITY",
                    "message": f"Unknown worker capability: {capability_name}",
                },
            ).to_dict()
        result = await capability.executor(payload, context)
        return result.to_dict()

    async def _execute_summarize_order(
        self,
        payload: dict[str, Any],
        context: WorkerExecutionContext,
    ) -> WorkerCapabilityResult:
        return self.provider.summarize_order(payload)

    async def _execute_draft_customer_reply(
        self,
        payload: dict[str, Any],
        context: WorkerExecutionContext,
    ) -> WorkerCapabilityResult:
        return self.provider.draft_customer_reply(payload)

    async def _execute_classify_lead(
        self,
        payload: dict[str, Any],
        context: WorkerExecutionContext,
    ) -> WorkerCapabilityResult:
        return self.provider.classify_lead(payload)

    async def _execute_prepare_recommendation(
        self,
        payload: dict[str, Any],
        context: WorkerExecutionContext,
    ) -> WorkerCapabilityResult:
        return self.provider.prepare_recommendation(payload)

    async def _execute_write_memory_draft(
        self,
        payload: dict[str, Any],
        context: WorkerExecutionContext,
    ) -> WorkerCapabilityResult:
        return self.provider.write_memory_draft(payload)

    async def _execute_propose_tool_call(
        self,
        payload: dict[str, Any],
        context: WorkerExecutionContext,
    ) -> WorkerCapabilityResult:
        return self.provider.propose_tool_call(payload)
