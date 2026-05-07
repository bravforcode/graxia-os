"""CRUD tests for the opportunities API endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_opportunities_requires_auth(public_async_client: AsyncClient):
    resp = await public_async_client.get("/api/v1/opportunities")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_opportunity_requires_auth(public_async_client: AsyncClient):
    resp = await public_async_client.post(
        "/api/v1/opportunities",
        json={"title": "Test", "source_platform": "test", "source_url": "https://example.com"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_opportunities_authenticated(
    async_client: AsyncClient,
    setup_database,
):
    resp = await async_client.get("/api/v1/opportunities?limit=10&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    # Endpoint returns {total: int, items: list}
    assert "items" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) <= 10


@pytest.mark.asyncio
async def test_create_opportunity_uses_provided_type(
    async_client: AsyncClient,
    setup_database,
):
    resp = await async_client.post(
        "/api/v1/opportunities",
        json={
            "title": "Test Hackathon",
            "type": "hackathon",
            "source_platform": "test",
            "source_url": "https://example.com/job/1",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "hackathon"


@pytest.mark.asyncio
async def test_create_opportunity_defaults_to_freelance(
    async_client: AsyncClient,
    setup_database,
):
    resp = await async_client.post(
        "/api/v1/opportunities",
        json={
            "title": "Test Freelance",
            "source_platform": "test",
            "source_url": "https://example.com/job/2",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["type"] == "freelance"


@pytest.mark.asyncio
async def test_list_opportunities_is_paginated(
    async_client: AsyncClient,
    setup_database,
):
    resp = await async_client.get("/api/v1/opportunities?limit=5&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) <= 5
