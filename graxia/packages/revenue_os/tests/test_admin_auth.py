import pytest
from fastapi import Request, HTTPException

from graxia.services.revenue_os_api.dependencies import require_admin_api_key


def _make_request(headers: list[tuple[bytes, bytes]]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
        "scheme": "http",
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_missing_key_raises_401(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-key")
    with pytest.raises(HTTPException) as exc:
        await require_admin_api_key(
            _make_request([]), x_admin_api_key=None, authorization=None
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_wrong_key_raises_403(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-key")
    with pytest.raises(HTTPException) as exc:
        await require_admin_api_key(
            _make_request([(b"x-admin-api-key", b"wrong-key")]),
            x_admin_api_key="wrong-key",
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_correct_key_header_accepted(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-key")
    result = await require_admin_api_key(
        _make_request([(b"x-admin-api-key", b"test-key")]),
        x_admin_api_key="test-key",
    )
    assert result is None


@pytest.mark.asyncio
async def test_bearer_token_accepted(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-key")
    result = await require_admin_api_key(
        _make_request([(b"authorization", b"Bearer test-key")]),
        x_admin_api_key=None,
        authorization="Bearer test-key",
    )
    assert result is None
