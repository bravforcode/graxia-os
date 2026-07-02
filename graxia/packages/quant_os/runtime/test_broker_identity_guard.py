"""Tests for broker identity guard."""

from .broker_identity_guard import BrokerIdentityGuard, BrokerProfile


def _make_guard(**overrides):
    defaults = dict(
        profile_id="test",
        expected_server="broker.example.com",
        account_mode="DEMO",
        account_currency="USD",
        account_login=12345,
    )
    defaults.update(overrides)
    return BrokerIdentityGuard(BrokerProfile(**defaults))


def test_broker_identity_guard_accepts_valid():
    guard = _make_guard()
    ok, violations = guard.validate("broker.example.com", 12345, "DEMO", "USD")
    assert ok
    assert violations == []
    assert not guard.is_violation()


def test_broker_identity_guard_rejects_server():
    guard = _make_guard()
    ok, violations = guard.validate("wrong.broker.com", 12345, "DEMO", "USD")
    assert not ok
    assert any("server_mismatch" in v for v in violations)


def test_broker_identity_guard_rejects_login():
    guard = _make_guard()
    ok, violations = guard.validate("broker.example.com", 99999, "DEMO", "USD")
    assert not ok
    assert any("login_mismatch" in v for v in violations)


def test_broker_identity_guard_rejects_mode():
    guard = _make_guard()
    ok, violations = guard.validate("broker.example.com", 12345, "LIVE", "USD")
    assert not ok
    assert any("account_mode_mismatch" in v for v in violations)


def test_broker_identity_guard_rejects_currency():
    guard = _make_guard()
    ok, violations = guard.validate("broker.example.com", 12345, "DEMO", "EUR")
    assert not ok
    assert any("currency_mismatch" in v for v in violations)


def test_broker_identity_guard_violations_reported():
    guard = _make_guard()
    guard.validate("wrong.server", 99999, "LIVE", "EUR")
    assert guard.is_violation()
    violations = guard.get_violations()
    assert len(violations) == 4
    assert guard.get_violations() == violations  # returns copy


def test_compute_fingerprint_has_timestamp():
    guard = _make_guard()
    fp = guard.compute_fingerprint("broker.example.com", 12345, "DEMO", "USD")
    assert fp.server_hash  # non-empty
    assert fp.login_hash  # non-empty
    assert fp.account_mode == "DEMO"
    assert fp.account_currency == "USD"
    assert fp.captured_at  # has timestamp
    assert "T" in fp.captured_at  # ISO format
