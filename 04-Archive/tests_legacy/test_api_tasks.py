"""
Tests for Tasks API endpoints
"""
import pytest
from httpx import AsyncClient
from datetime import datetime, timedelta


@pytest.mark.asyncio
async def test_get_tasks(async_client: AsyncClient):
    """Test GET /api/v1/tasks"""
    response = await async_client.get("/api/v1/tasks")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_task(async_client: AsyncClient):
    """Test POST /api/v1/tasks"""
    task_data = {
        "title": "Test Task",
        "description": "Test description",
        "task_type": "email",
        "priority": 8,
        "due_date": (datetime.now() + timedelta(days=1)).isoformat(),
    }
    
    response = await async_client.post("/api/v1/tasks", json=task_data)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == task_data["title"]
    assert data["priority"] == task_data["priority"]
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_get_task_by_id(async_client: AsyncClient, sample_task):
    """Test GET /api/v1/tasks/{id}"""
    response = await async_client.get(f"/api/v1/tasks/{sample_task.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(sample_task.id)
    assert data["title"] == sample_task.title


@pytest.mark.asyncio
async def test_update_task(async_client: AsyncClient, sample_task):
    """Test PATCH /api/v1/tasks/{id}"""
    update_data = {
        "status": "in_progress",
        "priority": 9,
    }
    
    response = await async_client.patch(f"/api/v1/tasks/{sample_task.id}", json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "in_progress"
    assert data["priority"] == 9


@pytest.mark.asyncio
async def test_complete_task(async_client: AsyncClient, sample_task):
    """Test POST /api/v1/tasks/{id}/complete"""
    response = await async_client.post(f"/api/v1/tasks/{sample_task.id}/complete")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["completed_at"] is not None


@pytest.mark.asyncio
async def test_delete_task(async_client: AsyncClient, sample_task):
    """Test DELETE /api/v1/tasks/{id}"""
    response = await async_client.delete(f"/api/v1/tasks/{sample_task.id}")
    assert response.status_code == 204
    
    # Verify deleted
    get_response = await async_client.get(f"/api/v1/tasks/{sample_task.id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_get_task_stats(async_client: AsyncClient):
    """Test GET /api/v1/tasks/stats/summary"""
    response = await async_client.get("/api/v1/tasks/stats/summary")
    assert response.status_code == 200
    data = response.json()
    assert "total_tasks" in data
    assert "by_status" in data
    assert "overdue_count" in data
    assert "due_today_count" in data


@pytest.mark.asyncio
async def test_tasks_filter_by_status(async_client: AsyncClient):
    """Test filtering tasks by status"""
    statuses = ["pending", "in_progress", "completed", "cancelled"]
    
    for status in statuses:
        response = await async_client.get(
            "/api/v1/tasks",
            params={"status": status}
        )
        assert response.status_code == 200
        data = response.json()
        for task in data:
            assert task["status"] == status


@pytest.mark.asyncio
async def test_tasks_filter_by_priority(async_client: AsyncClient):
    """Test filtering tasks by minimum priority"""
    min_priority = 7
    response = await async_client.get(
        "/api/v1/tasks",
        params={"priority_min": min_priority}
    )
    assert response.status_code == 200
    data = response.json()
    for task in data:
        assert task["priority"] >= min_priority


@pytest.mark.asyncio
async def test_tasks_overdue(async_client: AsyncClient):
    """Test getting overdue tasks"""
    response = await async_client.get(
        "/api/v1/tasks",
        params={"overdue": True}
    )
    assert response.status_code == 200
    data = response.json()
    
    now = datetime.now()
    for task in data:
        if task["due_date"]:
            due_date = datetime.fromisoformat(task["due_date"].replace("Z", "+00:00"))
            assert due_date < now


@pytest.mark.asyncio
async def test_create_task_validation(async_client: AsyncClient):
    """Test task creation validation"""
    # Missing required field
    invalid_data = {
        "description": "Missing title",
    }
    
    response = await async_client.post("/api/v1/tasks", json=invalid_data)
    assert response.status_code == 422  # Validation error
