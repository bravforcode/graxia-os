import pytest
import os
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)

def test_health_check():
    """Test the health check endpoint to ensure all components report correctly."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "components" in data
    assert "version" in data
    assert data["status"] in ["healthy", "degraded"]
    
def test_execute_task_endpoint():
    """Test the task execution endpoint to ensure it accepts valid payloads."""
    payload = {
        "project_description": "Analyze market trends and summarize findings."
    }
    response = client.post("/v1/tasks/execute", json=payload, headers={"X-API-Key": "graxia-secret-token"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "message" in data
    assert "Swarm activated" in data["message"]

def test_execute_task_invalid_payload():
    """Test the task execution endpoint with invalid payload."""
    payload = {
        "wrong_field": "This should fail validation."
    }
    response = client.post("/v1/tasks/execute", json=payload, headers={"X-API-Key": "graxia-secret-token"})
    assert response.status_code == 422 # Unprocessable Entity due to pydantic validation

def test_testsprite_integration():
    """
    Mock test to demonstrate Testsprite integration.
    In a real CI/CD pipeline, this would interact with the Testsprite service
    using the provided TESTSPRITE_API_KEY environment variable.
    """
    api_key = os.environ.get("TESTSPRITE_API_KEY")
    # For CI/CD purposes, we expect the API key to be available or mocked
    if api_key:
        assert len(api_key) > 20
        assert api_key.startswith("sk-")
        # Proceed with testsprite specific API calls here
        pass
    else:
        pytest.skip("TESTSPRITE_API_KEY not found in environment.")
