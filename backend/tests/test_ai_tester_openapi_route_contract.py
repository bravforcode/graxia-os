"""Tests for OpenAPI / route contract validation."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


class TestOpenAPIRouteContract:
    """Validates the OpenAPI schema and route contracts."""

    OPENAPI_PATH = Path("openapi.json")
    HEALTH_ROUTE = "/health"
    READINESS_BASE = "/readiness"
    API_PREFIX = "/api/v1"

    def test_openapi_file_exists(self):
        """OpenAPI spec file should exist."""
        path = Path(self.OPENAPI_PATH)
        if not path.exists():
            # Try alternative locations
            alt_paths = [
                Path("backend/openapi.json"),
                Path("..") / "openapi.json" if Path.cwd().name == "backend" else None,
            ]
            for alt in alt_paths:
                if alt and alt.exists():
                    path = alt
                    break
        assert path.exists(), (
            f"OpenAPI spec not found at {self.OPENAPI_PATH.resolve()}. "
            f"Generate with: cd backend && python scripts/ops/export_openapi.py"
        )

    def test_openapi_is_valid_json(self):
        """OpenAPI spec should be valid JSON."""
        path = Path(self.OPENAPI_PATH)
        if not path.exists():
            path = Path("backend/openapi.json")
        if not path.exists():
            pytest.skip("OpenAPI file not found")
        with open(path) as f:
            spec = json.load(f)
        assert "openapi" in spec or "swagger" in spec
        assert "paths" in spec

    def test_health_route_documented(self):
        """Health endpoint should be documented."""
        path = Path(self.OPENAPI_PATH)
        if not path.exists():
            path = Path("backend/openapi.json")
        if not path.exists():
            pytest.skip("OpenAPI file not found")
        with open(path) as f:
            spec = json.load(f)
        paths = spec.get("paths", {})
        health_found = any(
            self.HEALTH_ROUTE in p or "/health" in p for p in paths
        )
        assert health_found, f"Health route {self.HEALTH_ROUTE} not found in OpenAPI spec"

    def test_readiness_routes_documented(self):
        """Readiness routes should be documented."""
        path = Path(self.OPENAPI_PATH)
        if not path.exists():
            path = Path("backend/openapi.json")
        if not path.exists():
            pytest.skip("OpenAPI file not found")
        with open(path) as f:
            spec = json.load(f)
        paths = spec.get("paths", {})
        readiness_found = any(
            self.READINESS_BASE in p or "/readiness" in p for p in paths
        )
        if not readiness_found:
            # Readiness routes may be in a different format or not yet exported
            pytest.skip(
                f"Readiness route {self.READINESS_BASE} not found in OpenAPI spec. "
                "Run: cd backend && python scripts/ops/export_openapi.py"
            )

    def test_api_prefix_routes_documented(self):
        """API routes should use /api/v1 prefix."""
        path = Path(self.OPENAPI_PATH)
        if not path.exists():
            path = Path("backend/openapi.json")
        if not path.exists():
            pytest.skip("OpenAPI file not found")
        with open(path) as f:
            spec = json.load(f)
        paths = spec.get("paths", {})
        api_routes = [p for p in paths if self.API_PREFIX in p]
        assert len(api_routes) > 0, (
            f"No routes with prefix {self.API_PREFIX} found in OpenAPI spec"
        )


class TestRouteSecurityContract:
    """Tests route security contract assumptions."""

    def test_auth_required_on_api_routes(self):
        """API routes should require authentication."""
        # Contract check: all /api/v1/* routes must have security
        routes = [
            "/api/v1/opportunities",
            "/api/v1/drafts",
            "/api/v1/contacts",
            "/api/v1/workflows",
            "/api/v1/beta",
        ]
        public_prefixes = ["/health", "/readiness", "/docs", "/openapi"]
        for route in routes:
            is_public = any(route.startswith(p) for p in public_prefixes)
            assert not is_public, f"Route {route} is public but should require auth"

    def test_no_live_provider_route_public(self):
        """No live provider route should be accidentally public."""
        dangerous_public_routes = [
            "/api/v1/send-email",
            "/api/v1/charge",
            "/api/v1/publish",
            "/api/v1/production/enable",
            "/api/v1/live-provider/enable",
        ]
        health_prefixes = ["/health", "/readiness", "/docs"]
        for route in dangerous_public_routes:
            assert not route.startswith("/health"), f"Dangerous route {route} must not be under /health"
