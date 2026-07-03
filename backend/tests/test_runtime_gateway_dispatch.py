from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.runtime.contracts import TaskEnvelope
from app.runtime.gateway import GatewayDispatcher, GatewayService, InMemoryGatewayRepository
from app.runtime.gateway.dispatcher import DispatchResult


def build_task(**overrides: object) -> TaskEnvelope:
    payload = {
        "idempotencyKey": f"idem-{uuid4()}",
    }
    payload.update(overrides.pop("payload", {}))
    data = {
        "organizationId": "00000000-0000-0000-0000-000000000001",
        "correlationId": f"corr-{uuid4().hex[:10]}",
        "source": "test",
        "target": "worker",
        "taskType": "draft_followup",
        "payload": payload,
    }
    data.update(overrides)
    return TaskEnvelope.model_validate(data)


@pytest.mark.asyncio
async def test_dispatch_task_completes_and_tracks_status() -> None:
    seen: list[str] = []

    async def fake_create_run(**kwargs):
        seen.append(kwargs["task_type"])
        return SimpleNamespace(id=uuid4())

    async def fake_run_marker(*args, **kwargs):
        return None

    service = GatewayService(
        repository=InMemoryGatewayRepository(),
        dispatcher=GatewayDispatcher(),
        approval_requester=None,
        run_creator=fake_create_run,
        run_started=fake_run_marker,
        run_completed=fake_run_marker,
        run_failed=fake_run_marker,
    )

    task = build_task()
    record = await service.dispatch_task(task)
    status = await service.get_task_status(task.task_id)
    audits = await service.list_audit_events()

    assert record.status == "completed"
    assert record.dead_lettered is False
    assert status is not None
    assert status.status == "completed"
    assert seen == ["draft_followup"]
    assert audits[0].event_type == "runtime.gateway.dispatched"


@pytest.mark.asyncio
async def test_dispatch_task_blocks_dangerous_mcp_tool() -> None:
    service = GatewayService(
        repository=InMemoryGatewayRepository(),
        dispatcher=GatewayDispatcher(),
        approval_requester=None,
        run_creator=None,
        run_started=None,
        run_completed=None,
        run_failed=None,
    )
    task = build_task(
        target="mcp",
        taskType="tool_call",
        payload={"toolName": "read_env"},
    )

    record = await service.dispatch_task(task)

    assert record.status == "blocked"
    assert record.risk_level == "DANGEROUS_BLOCKED"
    assert "Dangerous" in (record.error_message or "")


@pytest.mark.asyncio
async def test_dispatch_task_creates_approval_block() -> None:
    approval_id = uuid4()

    async def fake_approval_requester(**kwargs):
        assert kwargs["action_type"] == "send_customer_followup"
        return SimpleNamespace(id=approval_id)

    service = GatewayService(
        repository=InMemoryGatewayRepository(),
        dispatcher=GatewayDispatcher(),
        approval_requester=fake_approval_requester,
        run_creator=None,
        run_started=None,
        run_completed=None,
        run_failed=None,
    )
    task = build_task(
        taskType="send_customer_followup",
        payload={"customer_action": True},
    )

    record = await service.dispatch_task(task)

    assert record.status == "blocked"
    assert record.approval_request_id == approval_id
    assert record.risk_level == "APPROVAL_REQUIRED"


@pytest.mark.asyncio
async def test_dispatch_failure_moves_to_dead_letter_and_requeue_replays() -> None:
    attempts = {"count": 0}

    async def flaky_dispatch(task: TaskEnvelope) -> DispatchResult:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("boom")
        return DispatchResult(target=task.target, status="completed", summary="replayed ok")

    service = GatewayService(
        repository=InMemoryGatewayRepository(),
        dispatcher=GatewayDispatcher(executor=flaky_dispatch),
        approval_requester=None,
        run_creator=None,
        run_started=None,
        run_completed=None,
        run_failed=None,
    )
    task = build_task()

    failed = await service.dispatch_task(task)
    dead_letters = await service.list_dead_letters()
    replayed = await service.requeue_dead_letter({"deadLetterId": str(dead_letters[0].dead_letter_id)})

    assert failed.status == "failed"
    assert failed.dead_lettered is True
    assert len(dead_letters) == 1
    assert replayed.status == "completed"
    assert replayed.replay_of_task_id == task.task_id
    assert await service.list_dead_letters() == []


@pytest.mark.asyncio
async def test_idempotency_returns_existing_dispatch_record() -> None:
    async def fake_create_run(**kwargs):
        return SimpleNamespace(id=uuid4())

    async def fake_run_marker(*args, **kwargs):
        return None

    service = GatewayService(
        repository=InMemoryGatewayRepository(),
        dispatcher=GatewayDispatcher(),
        approval_requester=None,
        run_creator=fake_create_run,
        run_started=fake_run_marker,
        run_completed=fake_run_marker,
        run_failed=fake_run_marker,
    )
    task = build_task(payload={"idempotencyKey": "same-key"})

    first = await service.dispatch_task(task)
    second = await service.dispatch_task(task)

    assert first.dispatch_id == second.dispatch_id
