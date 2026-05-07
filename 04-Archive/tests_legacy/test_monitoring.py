"""
Monitoring Tests

Tests for Prometheus metrics collection and export.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.monitoring import metrics_collector

client = TestClient(app)


class TestMetrics:
    """Test metrics collection and export."""
    
    def test_metrics_endpoint(self):
        """Test Prometheus metrics endpoint."""
        response = client.get("/metrics")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        
        # Check for expected metrics
        content = response.text
        assert "http_requests_total" in content
        assert "http_request_duration_seconds" in content
    
    def test_http_request_metrics(self):
        """Test HTTP request metrics recording."""
        # Make a request
        client.get("/health")
        
        # Check metrics
        response = client.get("/metrics")
        content = response.text
        
        assert 'http_requests_total{endpoint="/health"' in content
        assert 'http_request_duration_seconds' in content
    
    def test_metrics_collector_record_http(self):
        """Test metrics collector HTTP recording."""
        metrics_collector.record_http_request(
            method="GET",
            endpoint="/test",
            status=200,
            duration=0.123
        )
        
        # Verify metrics were recorded
        response = client.get("/metrics")
        content = response.text
        
        assert 'http_requests_total{endpoint="/test"' in content
    
    def test_metrics_collector_record_agent(self):
        """Test metrics collector agent recording."""
        metrics_collector.record_agent_execution(
            agent_name="test_agent",
            status="success",
            duration=1.5
        )
        
        response = client.get("/metrics")
        content = response.text
        
        assert 'agent_executions_total{agent_name="test_agent"' in content
    
    def test_metrics_collector_record_llm(self):
        """Test metrics collector LLM recording."""
        metrics_collector.record_llm_call(
            model="gpt-4",
            status="success",
            cost=0.05
        )
        
        response = client.get("/metrics")
        content = response.text
        
        assert 'llm_calls_total{model="gpt-4"' in content
        assert 'llm_cost_usd{model="gpt-4"' in content
    
    def test_metrics_collector_record_scraper(self):
        """Test metrics collector scraper recording."""
        metrics_collector.record_scraper_run(
            scraper_name="linkedin",
            status="success",
            items_found=10
        )
        
        response = client.get("/metrics")
        content = response.text
        
        assert 'scraper_runs_total{scraper_name="linkedin"' in content
        assert 'scraper_items_found{scraper_name="linkedin"' in content
    
    def test_metrics_collector_cache(self):
        """Test metrics collector cache recording."""
        metrics_collector.record_cache_hit("redis")
        metrics_collector.record_cache_miss("redis")
        
        response = client.get("/metrics")
        content = response.text
        
        assert 'cache_hits_total{cache_type="redis"' in content
        assert 'cache_misses_total{cache_type="redis"' in content
    
    @pytest.mark.asyncio
    async def test_update_gauges(self):
        """Test gauge metrics update."""
        await metrics_collector.update_gauges()
        
        response = client.get("/metrics")
        content = response.text
        
        # Check for gauge metrics
        assert "active_jobs" in content
        assert "active_contacts" in content
        assert "pending_tasks" in content
        assert "unread_emails" in content
        assert "daily_cost_usd" in content
        assert "monthly_cost_usd" in content


class TestHealthChecks:
    """Test health check endpoints."""
    
    def test_health_endpoint(self):
        """Test health check endpoint."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data
        assert "service" in data
        assert "readiness" in data
    
    def test_health_no_rate_limit(self):
        """Test that health checks are not rate limited."""
        # Make many requests
        for _ in range(200):
            response = client.get("/health")
            assert response.status_code == 200
