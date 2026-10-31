import re
import uuid

import pytest
from app.middleware.auth import AuthLevel, classify_route

PATH_PARAM = re.compile(r"\{[^}]+\}")
GUARDED_LEVELS = {AuthLevel.AUTHENTICATED, AuthLevel.OPERATOR, AuthLevel.ADMIN}
REJECTED_WITHOUT_AUTH = {401, 403}
REJECTED_WITHOUT_INTERNAL_KEY = {401, 403, 422}
OPEN_INTERNAL_ROUTES = {("GET", "/internal/health")}


def _mounted_routes(app):
    for route in app.router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        for method in sorted(set(methods) - {"HEAD", "OPTIONS"}):
            yield method, path


def _concrete_url(path: str) -> str:
    return PATH_PARAM.sub(lambda _: str(uuid.uuid4()), path)


@pytest.mark.asyncio
async def test_guarded_routes_reject_unauthenticated_requests(public_async_client):
    from app.main import app

    checked = 0
    failures = []
    for method, path in _mounted_routes(app):
        level = classify_route(method, path)
        if level not in GUARDED_LEVELS:
            continue
        checked += 1
        response = await public_async_client.request(method, _concrete_url(path))
        if response.status_code not in REJECTED_WITHOUT_AUTH:
            failures.append(f"{method} {path} [{level.value}] -> {response.status_code}")

    assert checked > 0
    assert failures == [], "unauthenticated access allowed:\n" + "\n".join(failures)


@pytest.mark.asyncio
async def test_blocked_surfaces_are_not_served(public_async_client):
    from app.main import app

    failures = []
    for method, path in _mounted_routes(app):
        if path.startswith("/internal") or classify_route(method, path) is not AuthLevel.BLOCKED:
            continue
        response = await public_async_client.request(method, _concrete_url(path))
        if response.status_code < 400:
            failures.append(f"{method} {path} -> {response.status_code}")

    assert failures == [], "blocked surface served:\n" + "\n".join(failures)


@pytest.mark.asyncio
async def test_internal_routes_require_internal_api_key(public_async_client):
    from app.main import app

    checked = 0
    failures = []
    for method, path in _mounted_routes(app):
        if not path.startswith("/internal") or (method, path) in OPEN_INTERNAL_ROUTES:
            continue
        checked += 1
        response = await public_async_client.request(method, _concrete_url(path))
        if response.status_code not in REJECTED_WITHOUT_INTERNAL_KEY:
            failures.append(f"{method} {path} -> {response.status_code}")

    assert checked > 0
    assert failures == [], "internal route served without X-Internal-API-Key:\n" + "\n".join(failures)
