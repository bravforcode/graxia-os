"""Test backup/rollback gate — documentation exists and contains required sections."""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestBackupRestoreGate:
    """Backup and restore documentation checks."""

    def test_backup_restore_runbook_exists(self):
        """BACKUP_RESTORE_RUNBOOK.md must exist."""
        path = PROJECT_ROOT / "docs" / "BACKUP_RESTORE_RUNBOOK.md"
        assert path.exists(), f"Missing: {path}"

    def test_backup_restore_runbook_has_rpo_rto(self):
        """Backup runbook must include RPO/RTO targets."""
        path = PROJECT_ROOT / "docs" / "BACKUP_RESTORE_RUNBOOK.md"
        content = path.read_text(encoding="utf-8")
        assert "RPO" in content or "Recovery Point" in content
        assert "RTO" in content or "Recovery Time" in content

    def test_backup_restore_runbook_has_procedure(self):
        """Backup runbook must include restore procedure."""
        path = PROJECT_ROOT / "docs" / "BACKUP_RESTORE_RUNBOOK.md"
        content = path.read_text(encoding="utf-8")
        assert "Restore" in content or "restore" in content
        assert "pg_restore" in content or "pg_dump" in content

    def test_backup_restore_runbook_has_verification(self):
        """Backup runbook must include verification steps."""
        path = PROJECT_ROOT / "docs" / "BACKUP_RESTORE_RUNBOOK.md"
        content = path.read_text(encoding="utf-8")
        assert "Verify" in content or "verify" in content


class TestRollbackGate:
    """Rollback documentation checks."""

    def test_rollback_runbook_exists(self):
        """ROLLBACK_RUNBOOK.md must exist."""
        path = PROJECT_ROOT / "docs" / "ROLLBACK_RUNBOOK.md"
        assert path.exists(), f"Missing: {path}"

    def test_rollback_runbook_has_decision_tree(self):
        """Rollback runbook must include decision tree."""
        path = PROJECT_ROOT / "docs" / "ROLLBACK_RUNBOOK.md"
        content = path.read_text(encoding="utf-8")
        assert "Decision Tree" in content or "decision" in content.lower()

    def test_rollback_runbook_has_code_rollback(self):
        """Rollback runbook must include code rollback procedure."""
        path = PROJECT_ROOT / "docs" / "ROLLBACK_RUNBOOK.md"
        content = path.read_text(encoding="utf-8")
        assert "Code" in content or "git checkout" in content

    def test_rollback_runbook_has_database_rollback(self):
        """Rollback runbook must include database rollback."""
        path = PROJECT_ROOT / "docs" / "ROLLBACK_RUNBOOK.md"
        content = path.read_text(encoding="utf-8")
        assert "Database" in content or "downgrade" in content or "alembic" in content

    def test_rollback_runbook_has_no_destructive_policy(self):
        """Rollback runbook must include no-destructive-migration policy."""
        path = PROJECT_ROOT / "docs" / "ROLLBACK_RUNBOOK.md"
        content = path.read_text(encoding="utf-8")
        assert "No Destructive" in content or "not allowed" in content.lower()


class TestSecretsRunbook:
    """Secrets runbook checks."""

    def test_production_secrets_runbook_exists(self):
        """PRODUCTION_SECRETS_RUNBOOK.md must exist."""
        path = PROJECT_ROOT / "docs" / "PRODUCTION_SECRETS_RUNBOOK.md"
        assert path.exists(), f"Missing: {path}"

    def test_production_secrets_runbook_has_inventory(self):
        """Secrets runbook must include secret inventory."""
        path = PROJECT_ROOT / "docs" / "PRODUCTION_SECRETS_RUNBOOK.md"
        content = path.read_text(encoding="utf-8")
        assert "Inventory" in content or "inventory" in content


class TestGoNoGoChecklist:
    """Go/no-go checklist checks."""

    def test_go_no_go_checklist_exists(self):
        """PRODUCTION_GO_NO_GO_CHECKLIST.md must exist."""
        path = PROJECT_ROOT / "docs" / "PRODUCTION_GO_NO_GO_CHECKLIST.md"
        assert path.exists(), f"Missing: {path}"

    def test_go_no_go_checklist_has_sections(self):
        """Go/no-go checklist must have required sections."""
        path = PROJECT_ROOT / "docs" / "PRODUCTION_GO_NO_GO_CHECKLIST.md"
        content = path.read_text(encoding="utf-8")
        assert "Environment" in content
        assert "Live Providers" in content
        assert "Infrastructure" in content
        assert "Monitoring" in content
        assert "Backup" in content
        assert "Security" in content


class TestStripeGate:
    """Stripe production gate checks."""

    def test_stripe_gate_exists(self):
        """STRIPE_PRODUCTION_GATE.md must exist."""
        path = PROJECT_ROOT / "docs" / "STRIPE_PRODUCTION_GATE.md"
        assert path.exists(), f"Missing: {path}"

    def test_stripe_gate_has_checklist(self):
        """Stripe gate must include go-live checklist."""
        path = PROJECT_ROOT / "docs" / "STRIPE_PRODUCTION_GATE.md"
        content = path.read_text(encoding="utf-8")
        assert "checklist" in content.lower() or "Go-Live" in content


class TestEmailGate:
    """Email production gate checks."""

    def test_email_gate_exists(self):
        """EMAIL_PRODUCTION_GATE.md must exist."""
        path = PROJECT_ROOT / "docs" / "EMAIL_PRODUCTION_GATE.md"
        assert path.exists(), f"Missing: {path}"

    def test_email_gate_has_checklist(self):
        """Email gate must include go-live checklist."""
        path = PROJECT_ROOT / "docs" / "EMAIL_PRODUCTION_GATE.md"
        content = path.read_text(encoding="utf-8")
        assert "checklist" in content.lower() or "Go-Live" in content


class TestGoogleWorkspaceGate:
    """Google Workspace production gate checks."""

    def test_google_workspace_gate_exists(self):
        """GOOGLE_WORKSPACE_PRODUCTION_GATE.md must exist."""
        path = PROJECT_ROOT / "docs" / "GOOGLE_WORKSPACE_PRODUCTION_GATE.md"
        assert path.exists(), f"Missing: {path}"

    def test_google_workspace_gate_has_checklist(self):
        """Google Workspace gate must include go-live checklist."""
        path = PROJECT_ROOT / "docs" / "GOOGLE_WORKSPACE_PRODUCTION_GATE.md"
        content = path.read_text(encoding="utf-8")
        assert "checklist" in content.lower() or "Go-Live" in content
