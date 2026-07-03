"""Tests for provider virtualization guard."""
from __future__ import annotations

import pytest
from app.beta.synthetic_tester.provider_guard import (
    ProviderGuardResult,
    check_provider_guard,
    assert_no_live_providers,
    is_provider_guard_safe,
)


class TestProviderGuard:
    def test_empty_env_is_safe(self):
        result = check_provider_guard(env_overrides={})
        assert result.stripe == "mock"
        assert result.email == "mock"
        assert result.live_providers_enabled is False

    def test_mock_keys_are_safe(self):
        env = {
            "STRIPE_SECRET_KEY": "sk_test_mock_key_for_testing",
            "RESEND_API_KEY": "re_mock_test_key",
        }
        result = check_provider_guard(env_overrides=env)
        assert result.stripe == "test_key"
        assert result.email == "configured"
        assert result.live_providers_enabled is False

    def test_live_stripe_detected(self):
        env = {"STRIPE_SECRET_KEY": "sk_live_real_key_9876543210"}
        result = check_provider_guard(env_overrides=env)
        assert result.stripe == "live"
        assert result.live_providers_enabled is True

    def test_live_database_url_detected(self):
        env = {"DATABASE_URL": "postgresql+asyncpg://user:pass@supabase.co:6543/db"}
        result = check_provider_guard(env_overrides=env)
        assert result.database == "production_url"
        assert result.live_providers_enabled is True

    def test_local_database_url_safe(self):
        env = {"DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db"}
        result = check_provider_guard(env_overrides=env)
        assert result.database == "local"
        assert result.live_providers_enabled is False

    def test_assert_no_live_providers_passes_with_safe_env(self):
        assert_no_live_providers(env_overrides={})  # should not raise

    def test_assert_no_live_providers_raises_with_live_stripe(self):
        env = {"STRIPE_SECRET_KEY": "sk_live_bad_key"}
        with pytest.raises(RuntimeError, match="live provider"):
            assert_no_live_providers(env_overrides=env)

    def test_assert_no_live_providers_raises_with_prod_db(self):
        env = {"DATABASE_URL": "postgresql+asyncpg://user:pass@supabase.co:6543/prod"}
        with pytest.raises(RuntimeError, match="live provider"):
            assert_no_live_providers(env_overrides=env)

    def test_is_provider_guard_safe_true(self):
        assert is_provider_guard_safe(env_overrides={}) is True

    def test_is_provider_guard_safe_false(self):
        env = {"STRIPE_SECRET_KEY": "sk_live_evil"}
        assert is_provider_guard_safe(env_overrides=env) is False

    def test_result_to_dict(self):
        result = check_provider_guard(env_overrides={})
        d = result.to_dict()
        assert d["liveProvidersEnabled"] is False
        assert d["stripe"] == "mock"
        assert "checks" in d

    def test_add_check(self):
        result = ProviderGuardResult()
        result.add_check("stripe", "MOCK", "Mock key")
        assert len(result.checks) == 1
        assert result.checks[0]["provider"] == "stripe"

    def test_llm_not_called_in_tests(self):
        env = {"OPENAI_API_KEY": "sk-test-key123"}
        result = check_provider_guard(env_overrides=env)
        assert result.llm == "configured"

    def test_google_creds_read_only(self):
        env = {}
        result = check_provider_guard(env_overrides=env)
        assert result.google == "read_only_or_mock"

    def test_no_database_url_set(self):
        env = {}
        result = check_provider_guard(env_overrides=env)
        assert result.database == "local_or_test"
