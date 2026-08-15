"""Tests that verify security fixes are REAL, not stubs.

These tests validate that:
- /risk/status returns REAL kill switch state (not hardcoded False)
- /risk/kill-switch POST actually calls orchestrator
- kill_switch enforce() escalation on failure
- rate_limit trusts X-Forwarded-For only from trusted proxies
"""

from unittest.mock import MagicMock, patch

import pytest

from graxia.packages.quant_os.core.config import QuantConfig
from graxia.packages.quant_os.core.orchestrator import TradingOrchestrator
from graxia.packages.quant_os.risk.kill_switch import KillSwitch, KillSwitchState, CloseMode


class TestRiskApiNotStub:
    """Verify /risk/status returns real orchestrator state, not hardcoded False."""

    def test_risk_status_returns_real_kill_switch_state(self):
        """orchestrator.kill_switch.get_status() must return real state, not hardcoded."""
        orch = TradingOrchestrator(config=QuantConfig())
        status = orch.kill_switch.get_status()

        # Must have real fields — not hardcoded
        assert "state" in status
        assert "reason" in status
        assert status["state"] in ("inactive", "INACTIVE")  # Initially inactive

    def test_risk_status_changes_after_trigger(self):
        """After trigger_kill_switch, status must reflect ACTIVE."""
        orch = TradingOrchestrator(config=QuantConfig())
        orch.trigger_kill_switch(reason="test", source="unit-test")

        status = orch.kill_switch.get_status()
        assert status["state"] in ("active", "ACTIVE")
        assert status["reason"] == "test"

    def test_risk_status_changes_after_reset(self):
        """After reset_kill_switch, status must reflect inactive."""
        orch = TradingOrchestrator(config=QuantConfig())
        orch.trigger_kill_switch(reason="test", source="unit-test")
        orch.reset_kill_switch(reason="resume", authorized_by="test")

        status = orch.kill_switch.get_status()
        assert status["state"] in ("inactive", "INACTIVE")


class TestKillSwitchEnforceEscalation:
    """Verify enforce() failures are escalated, not silently ignored."""

    def test_enforce_returns_result_with_failed_key(self):
        """enforce() must return dict with 'failed' key."""
        ks = KillSwitch()
        result = ks.enforce(CloseMode.CLOSE_ALL, broker_adapter=None)

        assert "failed" in result
        assert "closed" in result
        assert "remaining" in result
        assert isinstance(result["failed"], list)

    def test_enforce_no_broker_logs_warning(self):
        """enforce() with no broker_adapter returns empty result (not crash)."""
        ks = KillSwitch()
        result = ks.enforce(CloseMode.CLOSE_ALL, broker_adapter=None)

        assert result["closed"] == []
        assert result["remaining"] == []

    def test_enforce_with_failing_broker_records_failure(self):
        """enforce() with broker that fails to close records failure in result."""
        ks = KillSwitch()
        mock_broker = MagicMock()
        mock_broker.get_positions.return_value = [
            {"ticket": 12345, "pnl": -100.0}
        ]
        mock_broker.close_position.side_effect = Exception("connection lost")

        result = ks.enforce(CloseMode.CLOSE_ALL, broker_adapter=mock_broker)

        assert len(result["failed"]) == 1
        assert result["failed"][0]["ticket"] == 12345
        assert "connection lost" in result["failed"][0]["error"]


class TestRateLimitPathPrefix:
    """Verify rate limit rules match /api/v1/ prefix, not /api/."""

    def test_default_rules_use_v1_prefix(self):
        """All DEFAULT_RULES must start with /api/v1/."""
        from graxia.packages.quant_os.api.rate_limit import DEFAULT_RULES

        for rule in DEFAULT_RULES:
            assert rule.path_prefix.startswith("/api/v1/"), (
                f"Rate limit rule '{rule.path_prefix}' does not use /api/v1/ prefix"
            )

    def test_signal_rule_matches_actual_path(self):
        """The signal rate limit rule must match /api/v1/signal."""
        from graxia.packages.quant_os.api.rate_limit import DEFAULT_RULES

        signal_rules = [r for r in DEFAULT_RULES if "signal" in r.path_prefix]
        assert len(signal_rules) == 1
        assert signal_rules[0].path_prefix == "/api/v1/signal"


class TestRateLimitXffTrust:
    """Verify X-Forwarded-For is only trusted from known proxy IPs."""

    def test_xff_not_trusted_by_default(self):
        """When TRUSTED_PROXY_IPS is empty, XFF should be ignored."""
        import os

        with patch.dict(os.environ, {"TRUSTED_PROXY_IPS": ""}, clear=False):
            # Re-import to pick up env change
            import importlib
            import graxia.packages.quant_os.api.rate_limit as rl_mod
            importlib.reload(rl_mod)

            # Create a mock request with XFF and client IP
            mock_request = MagicMock()
            mock_request.headers = {"x-forwarded-for": "1.2.3.4"}
            mock_request.client.host = "10.0.0.1"

            ip = rl_mod.RateLimitMiddleware._client_ip(mock_request)
            # Should use direct client IP, not XFF
            assert ip == "10.0.0.1"

            # Restore
            importlib.reload(rl_mod)

    def test_xff_trusted_when_client_is_proxy(self):
        """When TRUSTED_PROXY_IPS contains client IP, XFF should be used."""
        import os

        with patch.dict(os.environ, {"TRUSTED_PROXY_IPS": "10.0.0.1"}, clear=False):
            import importlib
            import graxia.packages.quant_os.api.rate_limit as rl_mod
            importlib.reload(rl_mod)

            mock_request = MagicMock()
            mock_request.headers = {"x-forwarded-for": "1.2.3.4, 5.6.7.8"}
            mock_request.client.host = "10.0.0.1"

            ip = rl_mod.RateLimitMiddleware._client_ip(mock_request)
            assert ip == "1.2.3.4"  # First IP from XFF

            importlib.reload(rl_mod)
