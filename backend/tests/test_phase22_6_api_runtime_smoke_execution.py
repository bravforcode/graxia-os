"""API Runtime Smoke Execution — Phase 22.6 Lane D.

Runs against the local backend (http://127.0.0.1:8000) when available.
Documents the runtime evidence for each endpoint.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")
BACKEND_RUNNING = False


@dataclass
class ApiSmokeEvidence:
    endpoint: str
    method: str
    status_code: int | None
    response: dict[str, Any] | None
    request_id: str | None
    correlation_id: str | None
    safe_envelope: bool
    no_stack_trace: bool
    error_summary: str | None


_evidence: list[ApiSmokeEvidence] = []


@pytest.fixture(scope="session", autouse=True)
def check_backend():
    """Check if backend is running before any tests."""
    global BACKEND_RUNNING
    try:
        r = httpx.get(f"{BACKEND_URL}/health", timeout=3)
        BACKEND_RUNNING = r.status_code == 200
    except Exception:
        BACKEND_RUNNING = False


def _test_endpoint(
    method: str,
    path: str,
    expected_status: int | None = None,
    expect_auth_error: bool = False,
) -> ApiSmokeEvidence:
    """Test an API endpoint and record evidence."""
    url = f"{BACKEND_URL}{path}"
    try:
        if method == "GET":
            r = httpx.get(url, timeout=5)
        elif method == "POST":
            r = httpx.post(url, json={}, timeout=5)
        else:
            r = httpx.request(method, url, timeout=5)

        body = {}
        try:
            body = r.json()
        except Exception:
            body = {}

        request_id = body.get("request_id") or (body.get("error", {}) or {}).get("request_id")
        correlation_id = body.get("correlation_id") or (body.get("error", {}) or {}).get("correlation_id")

        # Check for safe error envelope
        safe = bool(body.get("error")) if r.status_code >= 400 else True

        # Check for stack traces in response text
        no_stack = "Traceback" not in r.text and "File \"" not in r.text

        ev = ApiSmokeEvidence(
            endpoint=path,
            method=method,
            status_code=r.status_code,
            response=body,
            request_id=request_id,
            correlation_id=correlation_id,
            safe_envelope=safe,
            no_stack_trace=no_stack,
            error_summary=str(body.get("error", {}).get("message", "")) if body.get("error") else None,
        )
        _evidence.append(ev)

        if expected_status is not None:
            assert r.status_code == expected_status, f"{method} {path}: expected {expected_status}, got {r.status_code}"
        if expect_auth_error:
            assert r.status_code in (401, 403), f"{method} {path}: expected auth error, got {r.status_code}"

        return ev
    except httpx.ConnectError:
        ev = ApiSmokeEvidence(
            endpoint=path,
            method=method,
            status_code=None,
            response=None,
            request_id=None,
            correlation_id=None,
            safe_envelope=False,
            no_stack_trace=True,
            error_summary="Connection refused",
        )
        _evidence.append(ev)
        pytest.skip(f"Backend not running at {BACKEND_URL}")
        return ev


# ── Root Health (no auth required) ──────────────────────────────────────


def test_health_endpoint():
    """GET /health — process health, no auth required."""
    ev = _test_endpoint("GET", "/health", expected_status=200)
    assert ev.response is not None
    assert "status" in ev.response
    assert "readiness" in ev.response
    assert ev.no_stack_trace


def test_root_endpoint():
    """GET / — API metadata, no auth required."""
    ev = _test_endpoint("GET", "/", expected_status=200)
    assert ev.response is not None
    assert ev.response.get("service") == "Graxia OS API"
    assert ev.no_stack_trace


# ── Auth-Protected Endpoints (expect 401) ───────────────────────────────


def test_health_api_v1():
    """GET /api/v1/health — requires auth, expect safe 401."""
    ev = _test_endpoint("GET", "/api/v1/health", expect_auth_error=True)
    assert ev.safe_envelope
    assert ev.no_stack_trace
    assert ev.request_id is not None
    assert ev.correlation_id is not None


def test_readiness_endpoint():
    """GET /api/v1/health/readiness — requires auth, expect safe 401."""
    ev = _test_endpoint("GET", "/api/v1/health/readiness", expect_auth_error=True)
    assert ev.safe_envelope
    assert ev.no_stack_trace


def test_readiness_production():
    """GET /api/v1/health/readiness/production — safe 401."""
    ev = _test_endpoint("GET", "/api/v1/health/readiness/production", expect_auth_error=True)
    assert ev.safe_envelope
    assert ev.no_stack_trace


def test_readiness_beta():
    """GET /api/v1/health/readiness/beta — safe 401."""
    ev = _test_endpoint("GET", "/api/v1/health/readiness/beta", expect_auth_error=True)
    assert ev.safe_envelope
    assert ev.no_stack_trace


# ── Safe Error Handling ────────────────────────────────────────────────


def test_unknown_endpoint_returns_safe_error():
    """GET /api/v1/nonexistent — should return safe error."""
    ev = _test_endpoint("GET", "/api/v1/nonexistent")
    # Middleware may return 403 for unknown API routes (by design)
    assert ev.status_code in (403, 404, 405, 401), f"Unexpected {ev.status_code}"
    assert ev.no_stack_trace


def test_unknown_root_endpoint_returns_safe_error():
    """GET /nonexistent-path — should return safe error."""
    ev = _test_endpoint("GET", "/nonexistent-path")
    # Middleware may return 403 for unknown routes (by design)
    assert ev.status_code in (403, 404, 405), f"Unexpected {ev.status_code}"
    assert ev.no_stack_trace


# ── Evidence Report ────────────────────────────────────────────────────


def test_generate_evidence_report():
    """Generate runtime smoke evidence summary."""
    total = len(_evidence)
    passed = sum(1 for e in _evidence if e.status_code and e.status_code < 500)
    auth_blocked = sum(1 for e in _evidence if e.status_code in (401, 403))

    report = {
        "phase": "22.6",
        "test_run_id": datetime.now(UTC).isoformat(),
        "backend_running": BACKEND_RUNNING,
        "backend_url": BACKEND_URL,
        "total_endpoints_tested": total,
        "passed": passed,
        "auth_blocked": auth_blocked,
        "evidence": [
            {
                "endpoint": e.endpoint,
                "method": e.method,
                "status": e.status_code,
                "request_id": e.request_id,
                "correlation_id": e.correlation_id,
                "safe_envelope": e.safe_envelope,
                "no_stack_trace": e.no_stack_trace,
            }
            for e in _evidence
        ],
    }
    # Print report for capture
    print(json.dumps(report, indent=2))
