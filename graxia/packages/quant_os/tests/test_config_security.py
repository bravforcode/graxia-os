"""Regression tests for core/config.py security/refactor fixes.

Covers:
  - VULN-002: QuantConfig.__repr__/__str__ must never leak secret field values.
  - BUG-004:  Multiple simultaneous *_PCT / MAX_POSITIONS env overrides must all land on the
              resulting risk_policy (a naive incomplete DRY refactor drops all but the last one).
  - VULN-003: Secret fields must be sourced through SecretProvider, not raw os.getenv, so that
              SecretProvider is the single point of control/audit for secret resolution.
"""

import graxia.packages.quant_os.core.config as config_module
from graxia.packages.quant_os.core.config import QuantConfig

DUMMY_SECRETS = {
    "MT5_PASSWORD": "dummy-mt5-password-xyz",
    "JWT_SECRET_KEY": "dummy-jwt-secret-xyz",
    "WEBHOOK_HMAC_SECRET": "dummy-webhook-secret-xyz",
    "ADMIN_API_KEY": "dummy-admin-key-xyz",
    "TELEGRAM_BOT_TOKEN": "dummy-telegram-token-xyz",
}


def test_repr_and_str_do_not_leak_secrets(monkeypatch):
    """(a) repr()/str() of a QuantConfig with all 5 secrets set must not contain any of them."""
    for env_var, value in DUMMY_SECRETS.items():
        monkeypatch.setenv(env_var, value)

    config = QuantConfig()
    r = repr(config)
    s = str(config)

    for value in DUMMY_SECRETS.values():
        assert value not in r, f"repr() leaked a secret value: {value!r}"
        assert value not in s, f"str() leaked a secret value: {value!r}"

    # Sanity: the fields are still masked, not silently dropped from the repr.
    assert r.count("***") >= 5
    assert s == r


def test_multiple_risk_env_overrides_combine(monkeypatch):
    """(b) Setting 2+ of the 4 risk env overrides at once must apply ALL of them.

    Uses small under-hard-limit values so `_enforce_hard_limits()` never clamps them, isolating
    the behavior of the BUG-004 refactor (`dataclasses.replace` with a combined overrides dict)
    from HARD_LIMITS enforcement.
    """
    monkeypatch.setenv("RISK_PER_TRADE_PCT", "0.05")  # -> 5 bps
    monkeypatch.setenv("MAX_POSITIONS", "2")

    config = QuantConfig()

    assert config.risk_policy.risk_per_trade_bps == 5
    assert config.risk_policy.max_open_positions == 2


def test_all_four_risk_env_overrides_combine(monkeypatch):
    """Same as above but exercises all 4 overrides together to guard every field mapping."""
    monkeypatch.setenv("RISK_PER_TRADE_PCT", "0.05")  # -> 5 bps
    monkeypatch.setenv("MAX_DAILY_LOSS_PCT", "0.10")  # -> 10 bps
    monkeypatch.setenv("MAX_DRAWDOWN_PCT", "0.20")  # -> 20 bps (must map to max_total_drawdown_bps)
    monkeypatch.setenv("MAX_POSITIONS", "3")

    config = QuantConfig()

    assert config.risk_policy.risk_per_trade_bps == 5
    assert config.risk_policy.max_daily_loss_bps == 10
    assert config.risk_policy.max_total_drawdown_bps == 20
    assert config.risk_policy.max_open_positions == 3


def test_secret_provider_is_consulted_not_raw_getenv(monkeypatch):
    """(c) QuantConfig must source secrets via SecretProvider, not raw os.getenv.

    Stubs out core.config.SecretProvider with a fake that always returns a known value
    regardless of the env var, and confirms QuantConfig picks up the stub's value —
    proving SecretProvider (not os.getenv) is what actually supplies the field.
    """
    monkeypatch.setenv("MT5_PASSWORD", "raw-env-value-should-be-ignored")

    class StubSecretProvider:
        def add_reference(self, name, ref):
            pass

        def get_secret(self, name):
            return "stub-provider-value"

    monkeypatch.setattr(config_module, "SecretProvider", StubSecretProvider)

    config = QuantConfig()

    assert config.mt5_password == "stub-provider-value"
    assert config.mt5_password != "raw-env-value-should-be-ignored"


def test_unset_secret_still_defaults_to_empty_string(monkeypatch):
    """Preserves pre-existing behavior: an unset secret env var still yields the empty-string
    default rather than raising, even though it's now routed through SecretProvider.

    Explicitly delenv's the 5 secret env vars first: some *other* test modules in the full suite
    call `load_dotenv()` at import time (e.g. scripts pulled in transitively), which — because
    pytest imports all test modules during collection, before any test body runs — can leak this
    repo's real local `.env` secrets into os.environ for the rest of the process. That's pre-existing
    test-suite fragility unrelated to core/config.py; delenv here makes this test deterministic
    regardless of what ran before it.
    """
    for env_var in ("MT5_PASSWORD", "JWT_SECRET_KEY", "WEBHOOK_HMAC_SECRET", "ADMIN_API_KEY", "TELEGRAM_BOT_TOKEN"):
        monkeypatch.delenv(env_var, raising=False)

    config = QuantConfig()
    assert config.mt5_password == ""
    assert config.jwt_secret_key == ""
    assert config.webhook_hmac_secret == ""
    assert config.admin_api_key == ""
    assert config.telegram_bot_token == ""
