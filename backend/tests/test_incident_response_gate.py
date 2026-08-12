"""Test incident response gate — documentation exists and contains required sections."""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestIncidentResponseGate:
    """Incident response documentation checks."""

    def test_incident_response_runbook_exists(self):
        """INCIDENT_RESPONSE_RUNBOOK.md must exist."""
        path = PROJECT_ROOT / "docs" / "INCIDENT_RESPONSE_RUNBOOK.md"
        assert path.exists(), f"Missing: {path}"

    def test_incident_response_has_severity_levels(self):
        """Incident response must include severity level definitions."""
        path = PROJECT_ROOT / "docs" / "INCIDENT_RESPONSE_RUNBOOK.md"
        content = path.read_text(encoding="utf-8")
        assert "SEV-" in content or "severity" in content.lower()

    def test_incident_response_has_detection(self):
        """Incident response must include detection methods."""
        path = PROJECT_ROOT / "docs" / "INCIDENT_RESPONSE_RUNBOOK.md"
        content = path.read_text(encoding="utf-8")
        assert "Detection" in content or "detection" in content.lower()

    def test_incident_response_has_response_procedure(self):
        """Incident response must have step-by-step response procedure."""
        path = PROJECT_ROOT / "docs" / "INCIDENT_RESPONSE_RUNBOOK.md"
        content = path.read_text(encoding="utf-8")
        assert "Triage" in content or "Containment" in content or "Diagnosis" in content

    def test_incident_response_has_escalation(self):
        """Incident response must include escalation path."""
        path = PROJECT_ROOT / "docs" / "INCIDENT_RESPONSE_RUNBOOK.md"
        content = path.read_text(encoding="utf-8")
        assert "Escalation" in content or "escalation" in content.lower()

    def test_incident_response_has_post_mortem(self):
        """Incident response must include post-mortem requirements."""
        path = PROJECT_ROOT / "docs" / "INCIDENT_RESPONSE_RUNBOOK.md"
        content = path.read_text(encoding="utf-8")
        assert "Post-Mortem" in content or "post-mortem" in content.lower()

    def test_incident_response_has_communication_templates(self):
        """Incident response must include communication templates."""
        path = PROJECT_ROOT / "docs" / "INCIDENT_RESPONSE_RUNBOOK.md"
        content = path.read_text(encoding="utf-8")
        assert "INCIDENT:" in content or "templates" in content.lower()
