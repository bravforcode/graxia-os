from __future__ import annotations

from pathlib import Path

from starlette.requests import Request
from starlette.responses import PlainTextResponse

from app.auth.context import AuthContext
from app.auth.middleware import AuthContextMiddleware
from app.config import settings
from scripts.ops.production_env_audit import audit_production_env


def _request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/protected",
            "headers": headers or [],
        }
    )


async def _noop_app(scope, receive, send):
    return None


async def test_production_context_uses_verified_jwt_identity_not_actor_headers(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    organization_id = "11111111-1111-1111-1111-111111111111"

    async def verified_payload(request):
        return {
            "sub": "verified-user",
            "role": "viewer",
            "organization_id": organization_id,
        }

    monkeypatch.setattr("app.auth.middleware.find_route_template", lambda request: "/api/v1/protected")
    monkeypatch.setattr("app.auth.middleware.build_auth_context", verified_payload)
    middleware = AuthContextMiddleware(_noop_app)
    seen: list[AuthContext | None] = []

    async def call_next(request):
        seen.append(request.state.auth_context)
        return PlainTextResponse("ok")

    response = await middleware.dispatch(
        _request(
            [
                (b"x-graxia-org-id", organization_id.encode()),
                (b"x-graxia-actor-type", b"admin"),
                (b"x-graxia-actor-id", b"spoofed-admin"),
            ]
        ),
        call_next,
    )

    assert response.status_code == 200
    assert seen[0] is not None
    assert seen[0].actor_type == "user"
    assert seen[0].actor_id == "verified-user"


async def test_local_context_preserves_actor_headers_for_fixtures(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "test")
    middleware = AuthContextMiddleware(_noop_app)
    seen: list[AuthContext | None] = []

    async def call_next(request):
        seen.append(request.state.auth_context)
        return PlainTextResponse("ok")

    response = await middleware.dispatch(
        _request(
            [
                (b"x-graxia-org-id", b"00000000-0000-0000-0000-000000000001"),
                (b"x-graxia-actor-type", b"service"),
                (b"x-graxia-actor-id", b"fixture-service"),
            ]
        ),
        call_next,
    )

    assert response.status_code == 200
    assert seen[0] is not None
    assert seen[0].actor_type == "service"
    assert seen[0].actor_id == "fixture-service"


def test_production_env_audit_requires_explicit_production_marker(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env.production"
    compose_file = tmp_path / "docker-compose.production.yml"
    env_file.write_text("SECRET_KEY=not-used\n", encoding="utf-8")
    compose_file.write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "production")

    result = audit_production_env(env_file, compose_file, repo_root=tmp_path)

    assert result.failed == 1
    assert ("env APP_ENV", False, "explicit env file must declare APP_ENV=production") in result.checks


def test_production_compose_does_not_publish_backend_port():
    repo_root = Path(__file__).resolve().parents[2]
    compose = (repo_root / "config" / "docker-compose.production.yml").read_text(encoding="utf-8")
    backend = compose.split("  backend:", 1)[1].split("  # Caddy Reverse Proxy", 1)[0]

    assert "ports:" not in backend
    assert '      - "8000"' in backend
