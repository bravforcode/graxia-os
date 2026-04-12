from __future__ import annotations

import pytest

from app.tasks.dlq_handler import DLQMessage, DeadLetterQueue


@pytest.mark.asyncio
async def test_admin_runtime_requires_admin_role(public_async_client):
    response = await public_async_client.get("/api/v1/admin/runtime")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_runtime_and_dlq_listing(async_client):
    queue = DeadLetterQueue()
    await queue.push(
        DLQMessage(
            task_name="tasks.daily_scan.run",
            args=[],
            kwargs={},
            exception="boom",
            original_queue="default",
        )
    )

    runtime = await async_client.get("/api/v1/admin/runtime")
    assert runtime.status_code == 200
    payload = runtime.json()
    assert "queue_depths" in payload
    assert "workers_online" in payload

    dlq = await async_client.get("/api/v1/admin/dlq")
    assert dlq.status_code == 200
    items = dlq.json()["items"]
    assert items
    assert items[0]["task_name"] == "tasks.daily_scan.run"


@pytest.mark.asyncio
async def test_admin_audit_log_endpoint_returns_checksum(async_client):
    response = await async_client.get("/api/v1/admin/audit-logs")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    if body["items"]:
        assert "checksum" in body["items"][0]
