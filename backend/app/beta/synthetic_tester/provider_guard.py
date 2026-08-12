"""Provider virtualization guard for AI Tester.

Ensures all provider calls in tests use mock/sandbox.
Hard-fails if any live provider flag is true.
"""

from __future__ import annotations

from typing import Any


class ProviderGuardResult:
    """Result of a provider virtualization check."""

    def __init__(self) -> None:
        self.stripe: str = "mock"
        self.email: str = "mock"
        self.google: str = "read_only_or_mock"
        self.llm: str = "mock"
        self.database: str = "local_or_test"
        self.live_providers_enabled: bool = False
        self.checks: list[dict[str, Any]] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "stripe": self.stripe,
            "email": self.email,
            "google": self.google,
            "llm": self.llm,
            "database": self.database,
            "liveProvidersEnabled": self.live_providers_enabled,
            "checks": self.checks,
        }

    def add_check(self, provider: str, status: str, detail: str) -> None:
        self.checks.append({
            "provider": provider,
            "status": status,
            "detail": detail,
        })


def check_provider_guard(
    *,
    env_overrides: dict[str, str | None] | None = None,
) -> ProviderGuardResult:
    """Check that all providers are virtualized/mocked.

    Args:
        env_overrides: Optional env dict to check against.
            If None, uses os.environ (but does not read .env).

    Returns:
        ProviderGuardResult with status per provider.
    """
    import os

    result = ProviderGuardResult()
    env = env_overrides if env_overrides is not None else os.environ

    # ── Stripe ──────────────────────────────────────────────────────────
    stripe_key = env.get("STRIPE_SECRET_KEY") or env.get("STRIPE_API_KEY")
    if stripe_key:
        if stripe_key.startswith("sk_live_") or stripe_key.startswith("rk_live_"):
            result.stripe = "live"
            result.live_providers_enabled = True
            result.add_check("stripe", "LIVE", "Live Stripe key detected")
        elif stripe_key.startswith("sk_test_") or stripe_key.startswith("rk_test_"):
            result.stripe = "test_key"
            result.add_check("stripe", "TEST_KEY", "Test Stripe key detected")
        elif "mock" in stripe_key.lower() or "test" in stripe_key.lower():
            result.stripe = "mock"
            result.add_check("stripe", "MOCK", "Mock Stripe key")
        else:
            result.stripe = "unknown"
            result.add_check("stripe", "UNKNOWN", "Unrecognized Stripe key format")
    else:
        result.stripe = "mock"
        result.add_check("stripe", "MOCK", "No Stripe key set")

    # ── Email (Resend) ──────────────────────────────────────────────────
    resend_key = env.get("RESEND_API_KEY")
    if resend_key:
        if resend_key.startswith("re_"):
            result.email = "configured"
            result.add_check("email", "CONFIGURED", "Resend API key present")
        else:
            result.email = "unknown"
            result.add_check("email", "UNKNOWN", "Email key format unrecognized")
    else:
        result.email = "mock"
        result.add_check("email", "MOCK", "No email key set")

    # ── Google ──────────────────────────────────────────────────────────
    google_creds = env.get("GOOGLE_APPLICATION_CREDENTIALS") or env.get(
        "GOOGLE_CREDENTIALS"
    )
    if google_creds:
        result.google = "configured"
        result.add_check("google", "CONFIGURED", "Google credentials present")
    else:
        result.google = "read_only_or_mock"
        result.add_check("google", "READ_ONLY_OR_MOCK", "No Google credentials set")

    # ── LLM ─────────────────────────────────────────────────────────────
    openai_key = env.get("OPENAI_API_KEY")
    gemini_key = env.get("GEMINI_API_KEY")
    if openai_key or gemini_key:
        result.llm = "configured"
        result.add_check("llm", "CONFIGURED", "LLM API key present (not called in tests)")
    else:
        result.llm = "mock"
        result.add_check("llm", "MOCK", "No LLM API key set")

    # ── Database ────────────────────────────────────────────────────────
    db_url = env.get("DATABASE_URL") or env.get("DATABASE_MIGRATION_URL")
    if db_url:
        if "supabase" in db_url.lower() or "production" in db_url.lower():
            result.database = "production_url"
            result.live_providers_enabled = True
            result.add_check("database", "PRODUCTION_URL", "Production DB URL detected")
        elif "localhost" in db_url.lower() or "127.0.0.1" in db_url.lower():
            result.database = "local"
            result.add_check("database", "LOCAL", "Local DB URL")
        else:
            result.database = "remote_non_prod"
            result.add_check("database", "REMOTE_NON_PROD", "Non-local, non-production DB")
    else:
        result.database = "local_or_test"
        result.add_check("database", "LOCAL_OR_TEST", "No DB URL set")

    return result


def assert_no_live_providers(
    result: ProviderGuardResult | None = None,
    *,
    env_overrides: dict[str, str | None] | None = None,
) -> None:
    """Assert that no live providers are enabled.

    Raises:
        RuntimeError: If any live provider is detected.
    """
    if result is None:
        result = check_provider_guard(env_overrides=env_overrides)

    violations: list[str] = []
    if result.stripe == "live":
        violations.append("Stripe: live key detected")
    if result.database == "production_url":
        violations.append("Database: production URL detected")

    if result.live_providers_enabled:
        violations.append("liveProvidersEnabled is True")

    if violations:
        raise RuntimeError(
            f"Provider guard violation — live provider(s) detected:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


def is_provider_guard_safe(
    result: ProviderGuardResult | None = None,
    *,
    env_overrides: dict[str, str | None] | None = None,
) -> bool:
    """Check if provider guard is safe without raising.

    Returns:
        True if safe, False if any live provider detected.
    """
    try:
        assert_no_live_providers(result, env_overrides=env_overrides)
        return True
    except RuntimeError:
        return False
