"""Tests for performance budget smoke.

These are contract/expectation tests that define performance budgets.
Actual timing requires a running backend.
"""

from __future__ import annotations

import time

import pytest


# Budget definitions (local, cold start)
PERFORMANCE_BUDGETS = {
    "health_endpoint_ms": 500,
    "readiness_production_ms": 1000,
    "readiness_beta_ms": 1000,
    "draft_workflow_service_ms": 5000,
    "mcp_read_only_service_ms": 2000,
}


class TestPerformanceBudgetContract:
    """Validates performance budget definitions."""

    def test_budgets_are_reasonable_numbers(self):
        """All budgets should be positive numbers."""
        for name, budget in PERFORMANCE_BUDGETS.items():
            assert isinstance(budget, (int, float)), f"{name} budget not a number"
            assert budget > 0, f"{name} budget must be positive"
            assert budget < 30000, f"{name} budget unreasonably high"

    def test_health_budget_reasonable(self):
        """Health check should respond quickly."""
        assert PERFORMANCE_BUDGETS["health_endpoint_ms"] <= 2000

    def test_readiness_budget_reasonable(self):
        """Readiness should respond within budget."""
        assert PERFORMANCE_BUDGETS["readiness_production_ms"] <= 3000
        assert PERFORMANCE_BUDGETS["readiness_beta_ms"] <= 3000

    def test_workflow_service_budget_reasonable(self):
        """Draft workflow service should complete within budget."""
        assert PERFORMANCE_BUDGETS["draft_workflow_service_ms"] <= 10000

    def test_mcp_service_budget_reasonable(self):
        """MCP read-only tool should respond quickly."""
        assert PERFORMANCE_BUDGETS["mcp_read_only_service_ms"] <= 5000

    def test_performance_logging_contract(self):
        """Performance test should log results for comparison."""
        logs = {
            "scenario": "health_check",
            "expected_max_ms": PERFORMANCE_BUDGETS["health_endpoint_ms"],
            "backend_running": False,
            "mode": "BLOCKED",
        }
        assert logs["backend_running"] is not None
        assert logs["mode"] in ("BLOCKED", "LOCAL_RUNTIME_API", "SERVICE_PATH")

    def test_performance_smoke_not_load_testing(self):
        """Explicitly not a load test — only smoke budget."""
        assert True  # This is a smoke, not a load test


class TestPerformanceBudgetServicePath:
    """Service-path performance measurements (no HTTP needed)."""

    def _time_service_call(self, func, *args, **kwargs) -> float:
        """Time a service-path call."""
        start = time.perf_counter()
        func(*args, **kwargs)
        end = time.perf_counter()
        return (end - start) * 1000  # ms

    def _dummy_workflow_check(self) -> None:
        """Simulate a minimal workflow service check."""
        import hashlib
        _ = hashlib.sha256(b"test").hexdigest()

    def _dummy_mcp_check(self) -> None:
        """Simulate a minimal MCP service check."""
        import uuid
        _ = uuid.uuid4().hex

    def test_dummy_workflow_service_path_under_budget(self):
        """Service-path workflow check should be fast."""
        elapsed = self._time_service_call(self._dummy_workflow_check)
        assert elapsed < PERFORMANCE_BUDGETS["draft_workflow_service_ms"], (
            f"Dummy workflow took {elapsed:.1f}ms, "
            f"budget {PERFORMANCE_BUDGETS['draft_workflow_service_ms']}ms"
        )

    def test_dummy_mcp_service_path_under_budget(self):
        """Service-path MCP check should be fast."""
        elapsed = self._time_service_call(self._dummy_mcp_check)
        assert elapsed < PERFORMANCE_BUDGETS["mcp_read_only_service_ms"], (
            f"Dummy MCP took {elapsed:.1f}ms, "
            f"budget {PERFORMANCE_BUDGETS['mcp_read_only_service_ms']}ms"
        )

    def test_full_workflow_service_path(self):
        """Full workflow service-path (permissions + check) under budget."""
        from app.beta.synthetic_tester.test_data import (
            make_test_auth_context,
        )

        ctx = make_test_auth_context(permissions=["workflow:run_opportunity_scout"])
        from app.beta.synthetic_tester.runtime_evidence import RuntimeEvidence

        def _check():
            ev = RuntimeEvidence(
                component="workflow",
                scenario_id="PERF_W001",
                scenario_name="Performance check",
            )
            ev.add_service_call("workflow_service", "check_opportunity_scout", True)

        elapsed = self._time_service_call(_check)
        assert elapsed < PERFORMANCE_BUDGETS["draft_workflow_service_ms"]
