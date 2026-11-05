"""AuthMiddleware denials use the safe error envelope.

Unknown routes stay fail-closed with 403 (by design, see
test_phase22_6_api_runtime_smoke_execution.py). The body keeps the legacy
"detail" key for existing clients and adds the request/correlation IDs that
every other error response carries.
"""

import pytest


@pytest.mark.asyncio
async def test_unknown_route_denial_carries_error_envelope(public_async_client):
    response = await public_async_client.get("/nonexistent-envelope-check")

    assert response.status_code == 403
    body = response.json()
    assert body["detail"] == "Forbidden"
    error = body["error"]
    assert error["code"] == "FORBIDDEN"
    assert error["message"] == "Forbidden"
    assert error["request_id"].startswith("req_")
    assert error["correlation_id"]
    assert response.headers["X-Request-ID"] == error["request_id"]
    assert response.headers["X-Correlation-ID"] == error["correlation_id"]
