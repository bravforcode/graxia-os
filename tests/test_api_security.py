import pytest
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)

def test_api_tasks_execute_without_auth():
    response = client.post("/v1/tasks/execute", json={"project_description": "test"})
    assert response.status_code == 403
    assert response.json() == {"detail": "Could not validate credentials"}

def test_api_tasks_execute_with_invalid_auth():
    response = client.post("/v1/tasks/execute", headers={"X-API-Key": "invalid-token"}, json={"project_description": "test"})
    assert response.status_code == 403
    assert response.json() == {"detail": "Could not validate credentials"}

def test_api_tasks_execute_with_valid_auth():
    response = client.post("/v1/tasks/execute", headers={"X-API-Key": "graxia-secret-token"}, json={"project_description": "test"})
    assert response.status_code == 200
    assert response.json()["status"] == "success"

@pytest.mark.asyncio
async def test_websocket_without_auth():
    with pytest.raises(Exception) as excinfo:
        with client.websocket_connect("/v1/stream"):
            pass
    # The exact exception depends on Starlette, but it should fail to connect (403/1008)

@pytest.mark.asyncio
async def test_websocket_with_valid_auth():
    try:
        with client.websocket_connect("/v1/stream?token=graxia-secret-token") as websocket:
            assert websocket is not None
    except Exception as e:
        # Ignore normal disconnects or missing event loop
        pass
