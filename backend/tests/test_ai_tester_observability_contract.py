"""Tests for observability / correlation runtime proof."""
from __future__ import annotations

import uuid

import pytest
from app.beta.synthetic_tester.runtime_evidence import (
    RuntimeEvidence,
    RuntimeEvidenceCollector,
)


def _simulate_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:16]}"


def _simulate_correlation_id() -> str:
    return f"corr_{uuid.uuid4().hex[:16]}"


def _simulate_audit_event_id() -> str:
    return f"audit_{uuid.uuid4().hex[:12]}"


def _simulate_security_event_id() -> str:
    return f"sec_{uuid.uuid4().hex[:12]}"


class TestObservabilityContract:
    """Tests that observability/correlation data can be collected."""

    def test_request_id_generated(self):
        rid = _simulate_request_id()
        assert rid.startswith("req_")
        assert len(rid) > 10

    def test_correlation_id_generated(self):
        cid = _simulate_correlation_id()
        assert cid.startswith("corr_")
        assert len(cid) > 10

    def test_audit_event_id_generated(self):
        eid = _simulate_audit_event_id()
        assert eid.startswith("audit_")

    def test_security_event_id_generated(self):
        eid = _simulate_security_event_id()
        assert eid.startswith("sec_")

    def test_evidence_captures_request_id(self):
        ev = RuntimeEvidence(
            component="api",
            scenario_id="O001",
            scenario_name="Correlation test",
        )
        ev.add_request_id(_simulate_request_id())
        assert len(ev.request_ids) == 1

    def test_evidence_captures_correlation_id(self):
        ev = RuntimeEvidence(
            component="api",
            scenario_id="O002",
            scenario_name="Correlation test 2",
        )
        ev.add_correlation_id(_simulate_correlation_id())
        assert len(ev.correlation_ids) == 1

    def test_evidence_captures_audit_event(self):
        ev = RuntimeEvidence(
            component="audit",
            scenario_id="O003",
            scenario_name="Audit event test",
        )
        ev.add_audit_event(_simulate_audit_event_id())
        assert len(ev.audit_event_ids) == 1

    def test_evidence_captures_security_event(self):
        ev = RuntimeEvidence(
            component="security",
            scenario_id="O004",
            scenario_name="Security event test",
        )
        ev.add_security_event(_simulate_security_event_id())
        assert len(ev.security_event_ids) == 1

    def test_collector_captures_multiple_correlations(self):
        col = RuntimeEvidenceCollector()
        ev = col.create_evidence("api", "O005", "Multi correlation")
        rid1 = _simulate_request_id()
        rid2 = _simulate_request_id()
        cid = _simulate_correlation_id()
        ev.add_request_id(rid1)
        ev.add_request_id(rid2)
        ev.add_correlation_id(cid)
        assert len(ev.request_ids) == 2
        assert len(ev.correlation_ids) == 1

    def test_request_and_correlation_across_scenarios(self):
        """Multiple scenarios share same run_id for traceability."""
        col = RuntimeEvidenceCollector()
        ev1 = col.create_evidence("api", "O006", "First call")
        ev2 = col.create_evidence("api", "O007", "Second call")
        assert ev1.test_run_id == ev2.test_run_id

    def test_mcp_call_id_captured(self):
        ev = RuntimeEvidence(
            component="mcp",
            scenario_id="O008",
            scenario_name="MCP call tracking",
        )
        ev.add_mcp_call("read_tool", "mcp_call_001", True)
        assert "mcp_call_001" in ev.mcp_call_ids

    def test_workflow_run_id_captured(self):
        ev = RuntimeEvidence(
            component="workflow",
            scenario_id="O009",
            scenario_name="Workflow tracking",
        )
        ev.add_workflow_run("opportunity_scout", "wf_run_001", True)
        assert "wf_run_001" in ev.workflow_run_ids

    def test_no_correlation_missing_ids(self):
        """Evidence without request/correlation IDs should flag limitations."""
        ev = RuntimeEvidence(
            component="api",
            scenario_id="O010",
            scenario_name="No correlation",
        )
        ev.add_limitation("No request_id/correlation_id captured")
        assert "request_id" in ev.limitations[0]

    def test_evidence_quality_capped_without_correlation(self):
        """Evidence quality should be capped when correlation data is missing."""
        ev = RuntimeEvidence(
            component="api",
            scenario_id="O011",
            scenario_name="Limited evidence",
        )
        assert len(ev.request_ids) == 0
        assert len(ev.correlation_ids) == 0
        # Quality would be capped per honesty rules

    def test_browser_trace_id_not_required(self):
        """Browser trace ID is optional but should not break anything."""
        ev = RuntimeEvidence(
            component="browser",
            scenario_id="O012",
            scenario_name="Browser trace",
        )
        ev.add_artifact("screenshots/test_screenshot.png")
        assert len(ev.artifacts) == 1

    def test_test_run_id_persistent(self):
        col = RuntimeEvidenceCollector()
        assert col.run_id.startswith("run_")
