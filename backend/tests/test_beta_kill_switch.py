"""Test beta feature flags and kill switches — all disabled by default."""
from __future__ import annotations

from app.config import Settings


class TestBetaKillSwitchDefaults:
    """Beta feature flags must be disabled by default."""

    def test_beta_enabled_false_by_default(self):
        """BETA_ENABLED is false by default."""
        settings = Settings(
            APP_ENV="testing",
            SECRET_KEY=None,
            ENCRYPTION_KEY=None,
            POSTGRES_PASSWORD=None,
        )
        assert settings.BETA_ENABLED is False

    def test_beta_mcp_tools_enabled_false_by_default(self):
        """BETA_MCP_TOOLS_ENABLED is false by default."""
        settings = Settings(
            APP_ENV="testing",
            SECRET_KEY=None,
            ENCRYPTION_KEY=None,
            POSTGRES_PASSWORD=None,
        )
        assert settings.BETA_MCP_TOOLS_ENABLED is False

    def test_beta_workflows_enabled_false_by_default(self):
        """BETA_WORKFLOWS_ENABLED is false by default."""
        settings = Settings(
            APP_ENV="testing",
            SECRET_KEY=None,
            ENCRYPTION_KEY=None,
            POSTGRES_PASSWORD=None,
        )
        assert settings.BETA_WORKFLOWS_ENABLED is False

    def test_beta_public_funnel_enabled_false_by_default(self):
        """BETA_PUBLIC_FUNNEL_ENABLED is false by default."""
        settings = Settings(
            APP_ENV="testing",
            SECRET_KEY=None,
            ENCRYPTION_KEY=None,
            POSTGRES_PASSWORD=None,
        )
        assert settings.BETA_PUBLIC_FUNNEL_ENABLED is False

    def test_beta_operator_ui_enabled_false_by_default(self):
        """BETA_OPERATOR_UI_ENABLED is false by default."""
        settings = Settings(
            APP_ENV="testing",
            SECRET_KEY=None,
            ENCRYPTION_KEY=None,
            POSTGRES_PASSWORD=None,
        )
        assert settings.BETA_OPERATOR_UI_ENABLED is False

    def test_kill_switch_all_external_beta_true_by_default(self):
        """KILL_SWITCH_ALL_EXTERNAL_BETA is true by default (locked)."""
        settings = Settings(
            APP_ENV="testing",
            SECRET_KEY=None,
            ENCRYPTION_KEY=None,
            POSTGRES_PASSWORD=None,
        )
        assert settings.KILL_SWITCH_ALL_EXTERNAL_BETA is True


class TestBetaKillSwitchBehavior:
    """Beta kill switch behavior tests using Settings instances."""

    def test_kill_switch_can_be_disabled_explicitly(self):
        """Kill switch can be disabled by explicit configuration."""
        settings = Settings(
            APP_ENV="testing",
            SECRET_KEY=None,
            ENCRYPTION_KEY=None,
            POSTGRES_PASSWORD=None,
            KILL_SWITCH_ALL_EXTERNAL_BETA=False,
        )
        assert settings.KILL_SWITCH_ALL_EXTERNAL_BETA is False

    def test_beta_can_be_enabled_explicitly(self):
        """Beta features can be enabled by explicit configuration."""
        settings = Settings(
            APP_ENV="testing",
            SECRET_KEY=None,
            ENCRYPTION_KEY=None,
            POSTGRES_PASSWORD=None,
            BETA_ENABLED=True,
            KILL_SWITCH_ALL_EXTERNAL_BETA=False,
        )
        assert settings.BETA_ENABLED is True
        assert settings.KILL_SWITCH_ALL_EXTERNAL_BETA is False
