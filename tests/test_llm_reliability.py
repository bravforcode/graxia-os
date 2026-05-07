import pytest
import asyncio
import os
import json
import time
import uuid
import shutil
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from core.providers.llm_client import LLMClient, TokenBudgetGate, CircuitBreaker, SemanticCacheLayer, LLMResponse

@pytest.fixture
def mock_llm_client():
    # Use a project-local directory for the test database to avoid Windows permission issues in /Temp
    test_tmp = Path(".cache/test_tmp")
    test_tmp.mkdir(parents=True, exist_ok=True)
    db_path = test_tmp / f"test_cache_{uuid.uuid4().hex}.db"
    
    client = LLMClient()
    # Reset state for tests
    client.budget_gate = TokenBudgetGate(max_tokens=1000)
    client.gateway_circuit_breaker = CircuitBreaker(failure_threshold=2, reset_timeout=1)
    client.cache_layer = SemanticCacheLayer(cache_db=str(db_path))
    
    yield client
    
    # Attempt cleanup (might fail on Windows if still locked, but that's okay for tests)
    try:
        if db_path.exists():
            os.remove(db_path)
    except:
        pass

@pytest.mark.asyncio
async def test_token_budget_gate():
    gate = TokenBudgetGate(max_tokens=100)
    
    # Test successful check
    assert await gate.check_and_add(60) is True
    assert gate.used_tokens == 60
    
    # Test exceeding budget
    assert await gate.check_and_add(50) is False
    assert gate.used_tokens == 60
    
    # Test refund
    await gate.refund(30)
    assert gate.used_tokens == 30
    assert await gate.check_and_add(50) is True

def test_circuit_breaker():
    cb = CircuitBreaker(failure_threshold=2, reset_timeout=1)
    
    assert cb.can_execute() is True
    
    # First failure
    cb.record_failure()
    assert cb.state == "CLOSED"
    assert cb.can_execute() is True
    
    # Second failure - should trip
    cb.record_failure()
    assert cb.state == "OPEN"
    assert cb.can_execute() is False
    
    # Test reset timeout
    time.sleep(1.1)
    assert cb.can_execute() is True
    assert cb.state == "HALF_OPEN"
    
    # Test success after half-open
    cb.record_success()
    assert cb.state == "CLOSED"
    assert cb.failures == 0

@pytest.mark.asyncio
async def test_semantic_cache_logic(mock_llm_client):
    messages = [{"role": "user", "content": "Hello"}]
    model = "test-model"
    
    # Mock API call
    mock_response = LLMResponse(
        content="Hi there!",
        raw_response={"choices": [{"message": {"content": "Hi there!"}}]}
    )
    
    with patch.object(mock_llm_client, '_call_api', new_callable=AsyncMock) as mock_api:
        mock_api.return_value = mock_response
        
        # First call - cache miss
        resp1 = await mock_llm_client.chat(messages, model=model)
        assert mock_api.call_count == 1
        assert resp1.content == "Hi there!"
        
        # Second call - cache hit
        resp2 = await mock_llm_client.chat(messages, model=model)
        assert mock_api.call_count == 1 # Still 1
        assert resp2.content == "Hi there!"
        assert resp2.cached is True

@pytest.mark.asyncio
async def test_tiered_routing_logic(mock_llm_client):
    # Simple prompt
    simple_messages = [{"role": "user", "content": "Hello"}]
    assert mock_llm_client._estimate_complexity(simple_messages) < 4
    assert mock_llm_client._route_model(mock_llm_client._estimate_complexity(simple_messages)) == "gemini-2.0-flash-lite"
    
    # Complex prompt
    complex_text = "Analyze and optimize this complex architectural system framework."
    complex_messages = [{"role": "user", "content": complex_text * 10}]
    assert mock_llm_client._estimate_complexity(complex_messages) >= 8
    assert mock_llm_client._route_model(mock_llm_client._estimate_complexity(complex_messages)) == "gemini-2.5-pro"
