"""Phase BE-P0 integration tests — credential incident remediation and broker identity lock."""
from graxia.packages.quant_os.runtime.secret_scan import SecretScanner
from graxia.packages.quant_os.runtime.broker_identity_guard import BrokerIdentityGuard, BrokerProfile
from graxia.packages.quant_os.runtime.secret_provider import SecretProvider
from graxia.packages.quant_os.runtime.redaction import Redactor


def test_secret_scanner_exists():
    """SecretScanner must exist."""
    scanner = SecretScanner(".")
    assert scanner is not None


def test_broker_identity_guard_exists():
    """BrokerIdentityGuard must exist."""
    profile = BrokerProfile(
        profile_id="test",
        expected_server="test-server",
        account_mode="DEMO",
        account_currency="USD",
        account_login=12345
    )
    guard = BrokerIdentityGuard(profile)
    assert guard is not None


def test_broker_identity_guard_accepts_valid():
    """BrokerIdentityGuard must accept valid profile."""
    profile = BrokerProfile(
        profile_id="test",
        expected_server="MetaQuotes-Demo",
        account_mode="DEMO",
        account_currency="USD",
        account_login=108629412
    )
    guard = BrokerIdentityGuard(profile)
    ok, violations = guard.validate(
        actual_server="MetaQuotes-Demo",
        actual_login=108629412,
        actual_mode="DEMO",
        actual_currency="USD"
    )
    assert ok is True


def test_broker_identity_guard_rejects_mismatch():
    """BrokerIdentityGuard must reject mismatched profile."""
    profile = BrokerProfile(
        profile_id="test",
        expected_server="Pepperstone-Demo",
        account_mode="DEMO",
        account_currency="USD",
        account_login=12345
    )
    guard = BrokerIdentityGuard(profile)
    ok, violations = guard.validate(
        actual_server="MetaQuotes-Demo",
        actual_login=108629412,
        actual_mode="DEMO",
        actual_currency="USD"
    )
    assert ok is False
    assert len(violations) > 0


def test_secret_provider_exists():
    """SecretProvider must exist."""
    provider = SecretProvider()
    assert provider is not None


def test_redactor_exists():
    """Redactor must exist."""
    redactor = Redactor()
    result = redactor.redact("account=108629412 password=secret123")
    assert "108629412" not in result
    assert "secret123" not in result


def test_redactor_preserves_structure():
    """Redactor must preserve structure."""
    redactor = Redactor()
    result = redactor.redact("MetaQuotes-Demo server")
    assert "BROKER_REDACTED" in result
    assert "server" in result
