"""Test all provider go-live checklists exist and contain required sections."""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestProviderGoLiveChecklists:
    """Provider go-live checklist checks."""

    def test_all_required_docs_exist(self):
        """All 8 required production docs must exist."""
        required_docs = [
            PROJECT_ROOT / "docs" / "PRODUCTION_GO_NO_GO_CHECKLIST.md",
            PROJECT_ROOT / "docs" / "PRODUCTION_SECRETS_RUNBOOK.md",
            PROJECT_ROOT / "docs" / "STRIPE_PRODUCTION_GATE.md",
            PROJECT_ROOT / "docs" / "EMAIL_PRODUCTION_GATE.md",
            PROJECT_ROOT / "docs" / "GOOGLE_WORKSPACE_PRODUCTION_GATE.md",
            PROJECT_ROOT / "docs" / "BACKUP_RESTORE_RUNBOOK.md",
            PROJECT_ROOT / "docs" / "INCIDENT_RESPONSE_RUNBOOK.md",
            PROJECT_ROOT / "docs" / "ROLLBACK_RUNBOOK.md",
        ]
        missing = [str(p) for p in required_docs if not p.exists()]
        assert not missing, f"Missing required docs: {missing}"

    def test_production_runbooks_present_in_readiness(self):
        """Verify the readiness endpoint would report runbooks present."""
        from app.api.health import _production_docs_present
        assert _production_docs_present() is True

    @pytest.mark.asyncio
    async def test_production_readiness_confirms_runbooks(self, async_client):
        """Production readiness endpoint must confirm runbooks present."""
        response = await async_client.get("/api/v1/health/readiness/production")
        assert response.status_code == 200
        payload = response.json()

        checks = payload.get("checks", {})
        assert "production_runbooks_present" in checks

    def test_stripe_gate_has_protected_operations(self):
        """Stripe gate must list protected operations."""
        path = PROJECT_ROOT / "docs" / "STRIPE_PRODUCTION_GATE.md"
        content = path.read_text(encoding="utf-8")
        assert "Protected Operations" in content or "blocked" in content.lower()

    def test_email_gate_has_protected_operations(self):
        """Email gate must list protected operations."""
        path = PROJECT_ROOT / "docs" / "EMAIL_PRODUCTION_GATE.md"
        content = path.read_text(encoding="utf-8")
        assert "Protected Operations" in content or "blocked" in content.lower()

    def test_google_workspace_gate_has_protected_operations(self):
        """Google Workspace gate must list protected operations."""
        path = PROJECT_ROOT / "docs" / "GOOGLE_WORKSPACE_PRODUCTION_GATE.md"
        content = path.read_text(encoding="utf-8")
        assert "Protected Operations" in content or "blocked" in content.lower()

    def test_all_gates_have_protected_data_section(self):
        """All provider gates must document what data is never exposed."""
        gates = [
            PROJECT_ROOT / "docs" / "STRIPE_PRODUCTION_GATE.md",
            PROJECT_ROOT / "docs" / "EMAIL_PRODUCTION_GATE.md",
            PROJECT_ROOT / "docs" / "GOOGLE_WORKSPACE_PRODUCTION_GATE.md",
        ]
        for gate_path in gates:
            content = gate_path.read_text(encoding="utf-8")
            assert "Protected Data" in content or "never" in content.lower(), \
                f"{gate_path.name} missing protected data section"
