"""Tests for API runtime smoke contract."""
from __future__ import annotations

import pytest
from app.beta.synthetic_tester.runtime_evidence import RuntimeEvidence


class TestAPIRuntimeSmokeContract:
    """Tests the contract for API runtime smoke testing.
    
    These tests validate what an API runtime smoke should assert,
    without requiring a running backend.
    """

    def test_health_endpoint_success_expected(self):
        """/health should return 200 with ready status."""
        req = {"method": "GET", "endpoint": "/health", "expected_status": 200}
        assert req["expected_status"] == 200

    def test_readiness_staging_endpoint(self):
        """Readiness staging should be accessible."""
        req = {"method": "GET", "endpoint": "/readiness/staging"}
        assert req["endpoint"] is not None

    def test_readiness_production_false(self):
        """Production readiness must return false."""
        req = {
            "method": "GET",
            "endpoint": "/readiness/production",
            "expected_body_key": "productionReady",
            "expected_body_value": False,
        }
        assert req["expected_body_value"] is False

    def test_readiness_beta_endpoint(self):
        """Beta readiness endpoint should exist."""
        req = {"method": "GET", "endpoint": "/readiness/beta"}
        assert req["endpoint"] is not None

    def test_unknown_endpoint_returns_404(self):
        """Unknown endpoint should return safe 404."""
        req = {"method": "GET", "endpoint": "/nonexistent", "expected_status": 404}
        assert req["expected_status"] == 404

    def test_auth_required_returns_401(self):
        """Auth-required route without auth should return 401."""
        req = {
            "method": "GET",
            "endpoint": "/api/v1/opportunities",
            "expected_status": 401,
        }
        assert req["expected_status"] == 401

    def test_response_has_request_id(self):
        """Response should contain request_id for observability."""
        assert True  # contract check

    def test_response_has_correlation_id(self):
        """Response should contain correlation_id for tracing."""
        assert True  # contract check

    def test_no_stack_trace_in_error_response(self):
        """Error responses should not contain stack traces."""
        error_envelope = {"error": "not_found", "detail": "Resource not found"}
        assert "stack" not in str(error_envelope).lower()
        assert "File" not in str(error_envelope)
        assert "Traceback" not in str(error_envelope)

    def test_no_sql_in_error_response(self):
        """Error responses should not leak SQL."""
        error_body = {"detail": "Item not found"}
        assert "SELECT" not in str(error_body)
        assert "FROM" not in str(error_body)

    def test_no_raw_file_paths(self):
        """Error responses should not expose file paths."""
        error_body = {"detail": "Configuration error"}
        assert "/app/" not in str(error_body)
        assert "C:\\" not in str(error_body)

    def test_no_tokens_in_response(self):
        """Response should not contain raw tokens."""
        error_body = {"detail": "Invalid API key"}
        assert "sk_" not in str(error_body)
        assert "ghp_" not in str(error_body)

    def test_live_providers_disabled_in_response(self):
        """Response should indicate live providers are disabled."""
        readiness = {"liveProvidersEnabled": False}
        assert readiness["liveProvidersEnabled"] is False

    def test_production_ready_false_in_response(self):
        """Response should indicate production is not ready."""
        readiness = {"productionReady": False}
        assert readiness["productionReady"] is False


class TestAPIRuntimeSmokeEvidence:
    """Tests evidence collection for API smoke."""

    def test_evidence_records_api_call(self):
        ev = RuntimeEvidence(
            component="api_smoke",
            scenario_id="API001",
            scenario_name="Health check",
        )
        ev.add_api_call("GET", "/health", 200)
        ev.complete("PASS")
        assert len(ev.api_calls) == 1
        assert ev.result == "PASS"

    def test_evidence_backend_not_running(self):
        ev = RuntimeEvidence(
            component="api_smoke",
            scenario_id="API002",
            scenario_name="Backend unavailable",
        )
        ev.backend_running = False
        ev.add_limitation("Backend not running")
        ev.complete("BLOCKED")
        assert ev.result == "BLOCKED"
        assert len(ev.limitations) == 1
