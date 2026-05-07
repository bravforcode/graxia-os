"""
Tests for Jobs API endpoints
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_jobs_list(async_client: AsyncClient):
    """Test GET /api/v1/jobs"""
    response = await async_client.get("/api/v1/jobs")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_jobs_with_filters(async_client: AsyncClient):
    """Test GET /api/v1/jobs with filters"""
    response = await async_client.get(
        "/api/v1/jobs",
        params={"status": "discovered", "min_score": 7.0, "limit": 10}
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 10


@pytest.mark.asyncio
async def test_get_job_by_id(async_client: AsyncClient, sample_job):
    """Test GET /api/v1/jobs/{id}"""
    response = await async_client.get(f"/api/v1/jobs/{sample_job.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(sample_job.id)
    assert data["title"] == sample_job.title


@pytest.mark.asyncio
async def test_get_job_not_found(async_client: AsyncClient):
    """Test GET /api/v1/jobs/{id} with invalid ID"""
    from uuid import uuid4
    response = await async_client.get(f"/api/v1/jobs/{uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_job_stats(async_client: AsyncClient):
    """Test GET /api/v1/jobs/stats"""
    response = await async_client.get("/api/v1/jobs/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_jobs" in data
    assert "by_status" in data
    assert "by_platform" in data
    assert "average_score" in data


@pytest.mark.asyncio
async def test_jobs_pagination(async_client: AsyncClient):
    """Test jobs pagination"""
    # Get first page
    response1 = await async_client.get("/api/v1/jobs", params={"limit": 5, "offset": 0})
    assert response1.status_code == 200
    page1 = response1.json()
    
    # Get second page
    response2 = await async_client.get("/api/v1/jobs", params={"limit": 5, "offset": 5})
    assert response2.status_code == 200
    page2 = response2.json()
    
    # Ensure different results
    if len(page1) > 0 and len(page2) > 0:
        assert page1[0]["id"] != page2[0]["id"]


@pytest.mark.asyncio
async def test_jobs_filter_by_platform(async_client: AsyncClient):
    """Test filtering jobs by platform"""
    response = await async_client.get(
        "/api/v1/jobs",
        params={"platform": "linkedin"}
    )
    assert response.status_code == 200
    data = response.json()
    for job in data:
        assert job["source_platform"] == "linkedin"


@pytest.mark.asyncio
async def test_jobs_filter_by_score(async_client: AsyncClient):
    """Test filtering jobs by minimum score"""
    min_score = 8.0
    response = await async_client.get(
        "/api/v1/jobs",
        params={"min_score": min_score}
    )
    assert response.status_code == 200
    data = response.json()
    for job in data:
        if job["match_score"]:
            assert float(job["match_score"]) >= min_score


@pytest.mark.asyncio
async def test_jobs_sorting(async_client: AsyncClient):
    """Test jobs sorting by score"""
    response = await async_client.get(
        "/api/v1/jobs",
        params={"sort_by": "match_score", "order": "desc"}
    )
    assert response.status_code == 200
    data = response.json()
    
    # Verify descending order
    scores = [float(job["match_score"]) for job in data if job["match_score"]]
    assert scores == sorted(scores, reverse=True)
