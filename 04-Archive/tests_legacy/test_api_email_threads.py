"""
Tests for Email Threads API endpoints
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_email_threads(async_client: AsyncClient):
    """Test GET /api/v1/email-threads"""
    response = await async_client.get("/api/v1/email-threads")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_email_threads_with_filters(async_client: AsyncClient):
    """Test GET /api/v1/email-threads with filters"""
    response = await async_client.get(
        "/api/v1/email-threads",
        params={"category": "urgent", "unread_only": True}
    )
    assert response.status_code == 200
    data = response.json()
    for thread in data:
        assert thread["category"] == "urgent"
        assert thread["status"] == "unread"


@pytest.mark.asyncio
async def test_get_email_thread_by_id(async_client: AsyncClient, sample_email_thread):
    """Test GET /api/v1/email-threads/{id}"""
    response = await async_client.get(f"/api/v1/email-threads/{sample_email_thread.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(sample_email_thread.id)
    assert data["subject"] == sample_email_thread.subject


@pytest.mark.asyncio
async def test_get_email_thread_messages(async_client: AsyncClient, sample_email_thread):
    """Test GET /api/v1/email-threads/{id}/messages"""
    response = await async_client.get(f"/api/v1/email-threads/{sample_email_thread.id}/messages")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_mark_email_thread_read(async_client: AsyncClient, sample_email_thread):
    """Test POST /api/v1/email-threads/{id}/mark-read"""
    response = await async_client.post(f"/api/v1/email-threads/{sample_email_thread.id}/mark-read")
    assert response.status_code == 200
    
    # Verify status changed
    get_response = await async_client.get(f"/api/v1/email-threads/{sample_email_thread.id}")
    data = get_response.json()
    assert data["status"] == "read"


@pytest.mark.asyncio
async def test_get_email_stats(async_client: AsyncClient):
    """Test GET /api/v1/email-threads/stats/summary"""
    response = await async_client.get("/api/v1/email-threads/stats/summary")
    assert response.status_code == 200
    data = response.json()
    assert "total_threads" in data
    assert "unread_count" in data
    assert "by_category" in data
    assert "action_items_count" in data


@pytest.mark.asyncio
async def test_email_threads_filter_by_category(async_client: AsyncClient):
    """Test filtering by category"""
    categories = ["urgent", "important", "normal", "spam", "newsletter"]
    
    for category in categories:
        response = await async_client.get(
            "/api/v1/email-threads",
            params={"category": category}
        )
        assert response.status_code == 200
        data = response.json()
        for thread in data:
            assert thread["category"] == category


@pytest.mark.asyncio
async def test_email_threads_priority_sorting(async_client: AsyncClient):
    """Test sorting by priority"""
    response = await async_client.get(
        "/api/v1/email-threads",
        params={"sort_by": "priority", "order": "desc"}
    )
    assert response.status_code == 200
    data = response.json()
    
    # Verify descending order
    priorities = [thread["priority"] for thread in data]
    assert priorities == sorted(priorities, reverse=True)
