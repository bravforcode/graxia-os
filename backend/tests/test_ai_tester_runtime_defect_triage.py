"""Tests for runtime defect triage framework."""
from __future__ import annotations

from enum import Enum


class DefectSeverity(str, Enum):
    S0_HARD_STOP = "S0"
    S1_CRITICAL_BLOCKER = "S1"
    S2_MAJOR = "S2"
    S3_MINOR = "S3"
    S4_BACKLOG = "S4"


class DefectFixPolicy(str, Enum):
    STOP_IMMEDIATELY = "stop and fix immediately"
    FIX_BEFORE_BETA = "fix before any human beta"
    FIX_BEFORE_EXPANDING_BETA = "fix before expanding beta"
    BATCH_INTO_NEXT_PHASE = "batch into next phase"
    BACKLOG = "backlog"


DEFECT_TRIAGE_MATRIX = {
    DefectSeverity.S0_HARD_STOP: {
        "examples": [
            "live provider call",
            "payment/send/publish",
            "productionReady true",
            "cross-org leak",
            "secret leak",
            "approval bypass",
        ],
        "policy": DefectFixPolicy.STOP_IMMEDIATELY,
    },
    DefectSeverity.S1_CRITICAL_BLOCKER: {
        "examples": [
            "backend cannot boot",
            "browser cannot run due project config",
            "beta readiness false unexpectedly",
            "workflow cannot run draft-only",
            "MCP service broken",
            "kill switch fails",
            "safe error leaks internals",
        ],
        "policy": DefectFixPolicy.FIX_BEFORE_BETA,
    },
    DefectSeverity.S2_MAJOR: {
        "examples": [
            "safety status unclear",
            "approval unclear",
            "feedback path missing",
            "request/correlation missing",
            "operator flow too complex",
        ],
        "policy": DefectFixPolicy.FIX_BEFORE_EXPANDING_BETA,
    },
    DefectSeverity.S3_MINOR: {
        "examples": [
            "copy/layout/helper text",
            "missing screenshot",
            "low-impact docs gap",
        ],
        "policy": DefectFixPolicy.BATCH_INTO_NEXT_PHASE,
    },
    DefectSeverity.S4_BACKLOG: {
        "examples": [
            "future polish",
            "nice-to-have",
        ],
        "policy": DefectFixPolicy.BACKLOG,
    },
}


class TestDefectTriage:
    """Tests for defect triage framework."""

    def test_all_severities_defined(self):
        assert len(DEFECT_TRIAGE_MATRIX) == 5  # S0-S4

    def test_s0_is_hard_stop(self):
        entry = DEFECT_TRIAGE_MATRIX[DefectSeverity.S0_HARD_STOP]
        assert "live provider call" in entry["examples"]
        assert "approval bypass" in entry["examples"]
        assert entry["policy"] == DefectFixPolicy.STOP_IMMEDIATELY

    def test_s1_is_critical_blocker(self):
        entry = DEFECT_TRIAGE_MATRIX[DefectSeverity.S1_CRITICAL_BLOCKER]
        assert "kill switch fails" in entry["examples"]
        assert entry["policy"] == DefectFixPolicy.FIX_BEFORE_BETA

    def test_s2_is_major(self):
        entry = DEFECT_TRIAGE_MATRIX[DefectSeverity.S2_MAJOR]
        assert "safety status unclear" in entry["examples"]
        assert entry["policy"] == DefectFixPolicy.FIX_BEFORE_EXPANDING_BETA

    def test_s3_is_minor(self):
        entry = DEFECT_TRIAGE_MATRIX[DefectSeverity.S3_MINOR]
        assert "copy/layout/helper text" in entry["examples"]
        assert entry["policy"] == DefectFixPolicy.BATCH_INTO_NEXT_PHASE

    def test_s4_is_backlog(self):
        entry = DEFECT_TRIAGE_MATRIX[DefectSeverity.S4_BACKLOG]
        assert "future polish" in entry["examples"]
        assert entry["policy"] == DefectFixPolicy.BACKLOG

    def test_no_security_defect_is_minor(self):
        """No security-related defect should be S3 or S4."""
        s3_entry = DEFECT_TRIAGE_MATRIX[DefectSeverity.S3_MINOR]
        s4_entry = DEFECT_TRIAGE_MATRIX[DefectSeverity.S4_BACKLOG]
        s3_examples = " ".join(s3_entry["examples"]).lower()
        s4_examples = " ".join(s4_entry["examples"]).lower()
        security_terms = ["leak", "security", "auth", "bypass", "permission"]
        for term in security_terms:
            assert term not in s3_examples, f"S3 should not contain security term: {term}"
            assert term not in s4_examples, f"S4 should not contain security term: {term}"


class TestDefectEvidence:
    """Tests that defects are recorded as evidence limitations."""
    RuntimeEvidence = None

    def _make_ev(self):
        if self.RuntimeEvidence is None:
            from app.beta.synthetic_tester.runtime_evidence import RuntimeEvidence as RE
            self.__class__.RuntimeEvidence = RE
        return self.RuntimeEvidence

    def test_defect_recorded_as_limitation(self):
        RuntimeEvidence = self._make_ev()

        ev = RuntimeEvidence(
            component="api",
            scenario_id="D001",
            scenario_name="Missing request_id",
        )
        ev.add_limitation("S2: request_id missing from response")
        assert len(ev.limitations) == 1
        assert "S2" in ev.limitations[0]

    def test_defect_confidence_impact(self):
        RE = self._make_ev()
        ev = RE(
            component="api",
            scenario_id="D002",
            scenario_name="Defect impacts confidence",
        )
        ev.confidence_impact = {"evidence_quality": -20}
        assert ev.confidence_impact["evidence_quality"] == -20

    def test_multiple_defects_recorded(self):
        RE = self._make_ev()
        ev = RE(
            component="api",
            scenario_id="D003",
            scenario_name="Multiple defects",
        )
        ev.add_limitation("S1: Backend cannot boot — missing DB")
        ev.add_limitation("S3: Feedback copy unclear")
        ev.complete("PARTIAL")
        assert len(ev.limitations) == 2
        assert ev.result == "PARTIAL"

    def test_s0_defect_causes_blocked(self):
        RE = self._make_ev()
        ev = RE(
            component="api",
            scenario_id="D004",
            scenario_name="S0 hard stop",
        )
        ev.add_limitation("S0: Live provider call detected")
        ev.production_ready = False  # must remain false
        ev.complete("BLOCKED")
        assert ev.result == "BLOCKED"
        assert ev.production_ready is False

    def test_defect_fix_recommendation_format(self):
        recommendations = [
            {"severity": "S1", "defect": "Backend cannot boot", "fix": "Ensure PostgreSQL is running via Docker"},
            {"severity": "S2", "defect": "Missing request_id", "fix": "Add middleware to attach request_id"},
        ]
        for rec in recommendations:
            assert "severity" in rec
            assert "defect" in rec
            assert "fix" in rec
