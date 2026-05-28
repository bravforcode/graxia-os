"""Tests for runtime evidence contract."""
from __future__ import annotations

from datetime import datetime

import pytest
from app.beta.synthetic_tester.runtime_evidence import (
    RuntimeEvidence,
    RuntimeEvidenceCollector,
)


class TestRuntimeEvidenceContract:
    def test_evidence_creation(self):
        ev = RuntimeEvidence(
            component="test_component",
            scenario_id="S001",
            scenario_name="Test Scenario",
        )
        assert ev.component == "test_component"
        assert ev.scenario_id == "S001"
        assert ev.result == "NOT_TESTED"
        assert ev.production_ready is False
        assert ev.backend_running is False
        assert ev.kill_switch_status == "inactive"

    def test_complete_sets_ended_at(self):
        ev = RuntimeEvidence(component="test", scenario_id="S001", scenario_name="Test")
        before = datetime.utcnow()
        ev.complete("PASS")
        assert ev.ended_at is not None
        assert ev.result == "PASS"

    def test_add_api_call(self):
        ev = RuntimeEvidence(component="api", scenario_id="S001", scenario_name="Test")
        ev.add_api_call("GET", "/health", 200)
        assert len(ev.api_calls) == 1
        assert ev.api_calls[0]["method"] == "GET"
        assert ev.api_calls[0]["status"] == 200

    def test_add_service_call(self):
        ev = RuntimeEvidence(component="svc", scenario_id="S001", scenario_name="Test")
        ev.add_service_call("beta_registry", "check_kill_switch", True)
        assert len(ev.service_calls) == 1
        assert ev.service_calls[0]["service"] == "beta_registry"

    def test_add_workflow_run(self):
        ev = RuntimeEvidence(component="wf", scenario_id="S001", scenario_name="Test")
        ev.add_workflow_run("opportunity_scout", "wf_001", True)
        assert len(ev.workflow_runs) == 1
        assert "wf_001" in ev.workflow_run_ids

    def test_add_mcp_call(self):
        ev = RuntimeEvidence(component="mcp", scenario_id="S001", scenario_name="Test")
        ev.add_mcp_call("read_tool", "mcp_001", True)
        assert len(ev.mcp_calls) == 1
        assert ev.mcp_call_ids == ["mcp_001"]

    def test_to_dict_no_secrets(self):
        ev = RuntimeEvidence(component="test", scenario_id="S001", scenario_name="Test")
        ev.add_api_call("GET", "/health", 200)
        d = ev.to_dict()
        assert d["production_ready"] is False
        assert d["no_live_payment_mode"] is True
        assert "Authorization" not in str(d)
        assert "sk_live_" not in str(d)

    def test_contains_forbidden_detects_env(self):
        ev = RuntimeEvidence(component="test", scenario_id="S001", scenario_name="Test")
        violations = ev.contains_forbidden_content()
        assert len(violations) == 0  # clean by default

    def test_production_ready_default_false(self):
        ev = RuntimeEvidence(component="test", scenario_id="S001", scenario_name="Test")
        assert ev.production_ready is False


class TestRuntimeEvidenceCollector:
    def test_collector_creates_evidence(self):
        col = RuntimeEvidenceCollector()
        ev = col.create_evidence("api", "S001", "Test Scenario")
        assert ev.component == "api"
        assert ev.test_run_id == col.run_id
        assert len(col.evidence_list) == 1

    def test_collector_get_by_component(self):
        col = RuntimeEvidenceCollector()
        col.create_evidence("api", "S001", "API Test")
        col.create_evidence("browser", "B001", "Browser Test")
        col.create_evidence("api", "S002", "Another API")
        assert len(col.get_by_component("api")) == 2
        assert len(col.get_by_component("browser")) == 1

    def test_collector_summary_counts(self):
        col = RuntimeEvidenceCollector()
        ev1 = col.create_evidence("api", "S001", "Pass")
        ev1.complete("PASS")
        ev2 = col.create_evidence("api", "S002", "Blocked")
        ev2.complete("BLOCKED")
        ev3 = col.create_evidence("api", "S003", "Not tested")
        summary = col.get_results_summary()
        assert summary["total"] == 3
        assert summary["passed"] == 1
        assert summary["blocked"] == 1
        assert summary["not_tested"] == 1

    def test_collector_no_forbidden_content_by_default(self):
        col = RuntimeEvidenceCollector()
        col.create_evidence("api", "S001", "Test")
        col.create_evidence("api", "S002", "Test 2")
        violations = col.has_forbidden_content()
        assert len(violations) == 0

    def test_evidence_has_no_live_payment_default(self):
        col = RuntimeEvidenceCollector()
        ev = col.create_evidence("payment", "P001", "Payment Test")
        assert ev.no_live_payment_mode is True

    def test_evidence_kill_switch_default(self):
        col = RuntimeEvidenceCollector()
        ev = col.create_evidence("kill", "K001", "Kill Switch Test")
        assert ev.kill_switch_status == "inactive"
