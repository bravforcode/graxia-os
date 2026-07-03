from __future__ import annotations

import pytest

from app.runtime.workers.service import RuntimeWorkerService, WorkerExecutionContext


@pytest.fixture
def ctx() -> WorkerExecutionContext:
    return WorkerExecutionContext(
        organization_id="org-worker",
        correlation_id="corr-worker",
        actor_type="agent",
        actor_id="worker-test",
    )


@pytest.mark.asyncio
async def test_runtime_worker_lists_expected_capabilities(ctx: WorkerExecutionContext) -> None:
    service = RuntimeWorkerService()

    result = service.list_capabilities()

    assert result == [
        "classify_lead",
        "draft_customer_reply",
        "prepare_recommendation",
        "propose_tool_call",
        "summarize_order",
        "write_memory_draft",
    ]


@pytest.mark.asyncio
async def test_summarize_order_is_deterministic(ctx: WorkerExecutionContext) -> None:
    service = RuntimeWorkerService()

    result = await service.execute(
        "summarize_order",
        {
            "order_id": "ord-123",
            "customer_name": "Nina",
            "currency": "THB",
            "total": 1490,
            "items": [
                {"name": "Course A", "quantity": 1},
                {"name": "Template Pack", "quantity": 2},
            ],
        },
        ctx,
    )

    assert result["ok"] is True
    assert result["risk_level"] == "READ_ONLY"
    assert result["approval_required"] is False
    assert result["data"]["summary"] == "Order ord-123 for Nina totals THB 1490 across 2 line items."
    assert result["data"]["item_count"] == 2


@pytest.mark.asyncio
async def test_draft_customer_reply_requires_approval(ctx: WorkerExecutionContext) -> None:
    service = RuntimeWorkerService()

    result = await service.execute(
        "draft_customer_reply",
        {
            "customer_name": "Mina",
            "subject": "Refund question",
            "customer_message": "Can I switch to another product instead?",
        },
        ctx,
    )

    assert result["ok"] is True
    assert result["risk_level"] == "APPROVAL_REQUIRED"
    assert result["approval_required"] is True
    assert "Mina" in result["data"]["draft_body"]
    assert result["data"]["channel"] == "customer_reply"


@pytest.mark.asyncio
async def test_write_memory_draft_redacts_sensitive_values(ctx: WorkerExecutionContext) -> None:
    service = RuntimeWorkerService()

    result = await service.execute(
        "write_memory_draft",
        {
            "title": "Customer delivery follow-up",
            "content": "Delivery token tok_live_secret_123 and api_key sk-test-123 should never be stored raw.",
            "tags": ["delivery", "followup"],
        },
        ctx,
    )

    assert result["ok"] is True
    assert result["risk_level"] == "LOW_WRITE"
    assert result["approval_required"] is False
    assert "[REDACTED]" in result["data"]["content"]
    assert "tok_live_secret_123" not in result["data"]["content"]
    assert "sk-test-123" not in result["data"]["content"]


@pytest.mark.asyncio
async def test_propose_tool_call_flags_approval_and_blocks_dangerous_tool(
    ctx: WorkerExecutionContext,
) -> None:
    service = RuntimeWorkerService()

    safe_result = await service.execute(
        "propose_tool_call",
        {
            "tool_name": "send_email",
            "arguments": {"to": "customer@example.com", "subject": "Hello"},
        },
        ctx,
    )
    blocked_result = await service.execute(
        "propose_tool_call",
        {
            "tool_name": "read_env",
            "arguments": {},
        },
        ctx,
    )

    assert safe_result["ok"] is True
    assert safe_result["risk_level"] == "APPROVAL_REQUIRED"
    assert safe_result["approval_required"] is True
    assert safe_result["data"]["tool_name"] == "send_email"

    assert blocked_result["ok"] is False
    assert blocked_result["risk_level"] == "DANGEROUS_BLOCKED"
    assert blocked_result["approval_required"] is False
    assert blocked_result["error"]["code"] == "DANGEROUS_TOOL_BLOCKED"
