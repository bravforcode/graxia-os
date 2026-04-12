import pytest


@pytest.mark.asyncio
async def test_jobs_list_stats_and_detail_contract(async_client, seeded_records):
    list_response = await async_client.get(
        "/api/v1/jobs",
        params={"status": "discovered", "min_score": 7.0},
    )
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == str(seeded_records.high_score_job.id)
    assert float(payload["items"][0]["match_score"]) >= 7.0

    detail_response = await async_client.get(f"/api/v1/jobs/{seeded_records.high_score_job.id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["title"] == "Senior Platform Engineer"

    stats_response = await async_client.get("/api/v1/jobs/stats")
    assert stats_response.status_code == 200
    stats = stats_response.json()
    assert stats["total_jobs"] == 2
    assert stats["by_status"]["discovered"] == 2
    assert stats["average_score"] > 0


@pytest.mark.asyncio
async def test_email_thread_list_stats_messages_and_mark_read_contract(async_client, seeded_records):
    list_response = await async_client.get(
        "/api/v1/email-threads/",
        params={"category": "important", "unread_only": True},
    )
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == str(seeded_records.email_thread.id)
    assert payload["items"][0]["status"] == "unread"

    stats_response = await async_client.get("/api/v1/email-threads/stats")
    assert stats_response.status_code == 200
    stats = stats_response.json()
    assert stats["total_threads"] == 1
    assert stats["unread_count"] == 1
    assert stats["action_items_count"] == 1
    assert stats["by_category"]["important"] == 1

    messages_response = await async_client.get(
        f"/api/v1/email-threads/{seeded_records.email_thread.id}/messages"
    )
    assert messages_response.status_code == 200
    assert messages_response.json() == []

    mark_read_response = await async_client.patch(
        f"/api/v1/email-threads/{seeded_records.email_thread.id}/mark-read"
    )
    assert mark_read_response.status_code == 200
    assert mark_read_response.json()["status"] == "read"
    assert mark_read_response.json()["unread_count"] == 0


@pytest.mark.asyncio
async def test_task_list_stats_update_and_complete_contract(async_client, seeded_records):
    list_response = await async_client.get(
        "/api/v1/tasks/",
        params={"status": "pending", "priority_min": 7},
    )
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == str(seeded_records.task.id)

    stats_response = await async_client.get("/api/v1/tasks/stats")
    assert stats_response.status_code == 200
    stats = stats_response.json()
    assert stats["total_tasks"] == 1
    assert stats["by_status"]["pending"] == 1
    assert stats["due_today_count"] == 1

    update_response = await async_client.patch(
        f"/api/v1/tasks/{seeded_records.task.id}",
        json={"status": "in_progress", "priority": 9},
    )
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "in_progress"
    assert update_response.json()["priority"] == 9

    complete_response = await async_client.patch(f"/api/v1/tasks/{seeded_records.task.id}/complete")
    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == "completed"
    assert complete_response.json()["completed_at"] is not None


@pytest.mark.asyncio
async def test_cost_summary_usage_and_forecast_contract(async_client, seeded_records):
    summary_response = await async_client.get("/api/v1/costs/summary")
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["today"]["cost_usd"] == 0.25
    assert summary["week"]["cost_usd"] == 0.375
    assert summary["month"]["cost_usd"] == 0.375

    usage_response = await async_client.get("/api/v1/costs/usage", params={"days": 7})
    assert usage_response.status_code == 200
    usage = usage_response.json()
    assert usage["period_days"] == 7
    assert usage["total_requests"] == 2
    assert usage["total_cost_usd"] == 0.375
    assert usage["by_platform"]["linkedin"]["requests"] == 1
    assert usage["by_platform"]["upwork"]["cost_usd"] == 0.125

    forecast_response = await async_client.get("/api/v1/costs/forecast")
    assert forecast_response.status_code == 200
    forecast = forecast_response.json()
    assert forecast["current_cost"] == 0.375
    assert forecast["forecasted_cost"] >= forecast["current_cost"]
    assert forecast["budget"] > 0
