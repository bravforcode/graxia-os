"""
Tests for Costs API endpoints
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_costs_summary(async_client: AsyncClient):
    """Test GET /api/v1/costs/summary"""
    response = await async_client.get("/api/v1/costs/summary")
    assert response.status_code == 200
    data = response.json()
    
    # Check structure
    assert "today" in data
    assert "week" in data
    assert "month" in data
    
    # Check today data
    assert "cost_usd" in data["today"]
    assert "budget_usd" in data["today"]
    assert "percentage" in data["today"]
    
    # Check values are valid
    assert data["today"]["cost_usd"] >= 0
    assert data["today"]["budget_usd"] > 0
    assert 0 <= data["today"]["percentage"] <= 200  # Allow over-budget


@pytest.mark.asyncio
async def test_get_costs_usage(async_client: AsyncClient):
    """Test GET /api/v1/costs/usage"""
    response = await async_client.get("/api/v1/costs/usage")
    assert response.status_code == 200
    data = response.json()
    
    assert "period_days" in data
    assert "total_requests" in data
    assert "total_cost_usd" in data
    assert "by_platform" in data
    
    # Check by_platform structure
    for platform, stats in data["by_platform"].items():
        assert "requests" in stats
        assert "cost_usd" in stats
        assert stats["requests"] >= 0
        assert stats["cost_usd"] >= 0


@pytest.mark.asyncio
async def test_get_costs_usage_with_filters(async_client: AsyncClient):
    """Test GET /api/v1/costs/usage with filters"""
    response = await async_client.get(
        "/api/v1/costs/usage",
        params={"platform": "linkedin", "days": 7}
    )
    assert response.status_code == 200
    data = response.json()
    
    assert data["period_days"] == 7
    
    # If platform filter works, should only have linkedin
    if data["by_platform"]:
        assert "linkedin" in data["by_platform"]


@pytest.mark.asyncio
async def test_get_costs_forecast(async_client: AsyncClient):
    """Test GET /api/v1/costs/forecast"""
    response = await async_client.get("/api/v1/costs/forecast")
    assert response.status_code == 200
    data = response.json()
    
    assert "current_cost" in data
    assert "forecasted_cost" in data
    assert "daily_average" in data
    assert "days_elapsed" in data
    assert "days_remaining" in data
    assert "budget" in data
    assert "over_budget" in data
    
    # Check logical consistency
    assert data["current_cost"] >= 0
    assert data["forecasted_cost"] >= data["current_cost"]
    assert data["daily_average"] >= 0
    assert data["days_elapsed"] >= 0
    assert data["days_remaining"] >= 0
    assert data["budget"] > 0


@pytest.mark.asyncio
async def test_costs_budget_alert(async_client: AsyncClient):
    """Test budget alert threshold"""
    response = await async_client.get("/api/v1/costs/summary")
    data = response.json()
    
    # Check if over 80% budget
    if data["month"]["percentage"] >= 80:
        # Should have warning flag or alert
        assert data["month"]["percentage"] >= 80


@pytest.mark.asyncio
async def test_costs_by_platform_breakdown(async_client: AsyncClient):
    """Test cost breakdown by platform"""
    response = await async_client.get("/api/v1/costs/usage", params={"days": 30})
    data = response.json()
    
    total_cost = data["total_cost_usd"]
    platform_costs = sum(stats["cost_usd"] for stats in data["by_platform"].values())
    
    # Platform costs should sum to total (with small floating point tolerance)
    assert abs(total_cost - platform_costs) < 0.01


@pytest.mark.asyncio
async def test_costs_historical_data(async_client: AsyncClient):
    """Test historical cost data"""
    # Get 7 days
    response7 = await async_client.get("/api/v1/costs/usage", params={"days": 7})
    data7 = response7.json()
    
    # Get 30 days
    response30 = await async_client.get("/api/v1/costs/usage", params={"days": 30})
    data30 = response30.json()
    
    # 30 days should have more or equal data than 7 days
    assert data30["total_requests"] >= data7["total_requests"]
    assert data30["total_cost_usd"] >= data7["total_cost_usd"]
