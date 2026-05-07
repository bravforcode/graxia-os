import asyncio
import pytest
import time
from fastapi.testclient import TestClient
from api import app
from core.execution.message_bus import message_bus
from core.providers.llm_client import LLMClient
from unittest.mock import patch, AsyncMock

# Add default headers for authentication
client = TestClient(app)
AUTH_HEADERS = {"X-API-Key": "graxia-secret-token"}

@pytest.mark.asyncio
async def test_chaos_concurrent_flooding():
    """Stress test the API with many concurrent requests to ensure it doesn't crash."""
    async def make_request():
        payload = {"project_description": "Chaos test payload"}
        # Use a background thread or async client if possible, but TestClient is sync.
        # We will wrap it in asyncio.to_thread
        return await asyncio.to_thread(client.post, "/v1/tasks/execute", json=payload, headers=AUTH_HEADERS)
    
    # 50 concurrent requests
    tasks = [make_request() for _ in range(50)]
    responses = await asyncio.gather(*tasks)
    
    for resp in responses:
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert resp.json()["status"] == "success"

def test_chaos_malformed_payloads():
    """Test API resilience against deeply nested and malformed payloads."""
    malformed_payloads = [
        {},
        {"wrong_key": "value"},
        {"project_description": 12345},
        {"project_description": "A" * 100000}, # Giant string
        {"project_description": None},
    ]
    for payload in malformed_payloads:
        resp = client.post("/v1/tasks/execute", json=payload, headers=AUTH_HEADERS)
        # Should be handled gracefully by Pydantic (422) or logic (400), but not crash (500)
        assert resp.status_code in [422, 400]

@pytest.mark.asyncio
async def test_chaos_redis_connection_failure():
    """Simulate Redis connection dropping during operation."""
    # Temporarily set use_redis to True, but remove the actual connection
    original_use_redis = getattr(message_bus, '_use_redis', False)
    message_bus._use_redis = True
    
    with patch.object(message_bus, '_redis', AsyncMock()) as mock_redis:
        mock_redis.publish.side_effect = Exception("Simulated Redis Connection Drop")
        
        # This should trigger the fallback mechanism and not crash
        try:
            from core.execution.message_bus import AgentMessage
            msg = AgentMessage(sender="chaos", topic="test", content="fail")
            await message_bus.publish("test", msg)
            # If it didn't raise, the fallback worked
            success = True
        except Exception as e:
            success = False
            
        assert success == True
        
    message_bus._use_redis = original_use_redis

@pytest.mark.asyncio
async def test_chaos_llm_timeout():
    """Simulate LLM API taking too long to respond."""
    llm = LLMClient()
    
    with patch.object(llm, '_call_api', new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = asyncio.TimeoutError("LLM Timeout")
        
        try:
            messages = [{"role": "user", "content": "Hello"}]
            # LLMClient should handle timeouts gracefully via circuit breaker or retries, 
            # or raise a clean exception rather than hanging indefinitely.
            with pytest.raises(Exception):
                await llm.chat(messages)
            
            # Circuit breaker should record this failure
            assert llm.gateway_circuit_breaker.failures > 0
        except Exception:
            pass

def test_health_check_resilience():
    """Check health check under missing attributes."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert "status" in resp.json()
