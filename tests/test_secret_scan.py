import json

from scripts.secret_scan import _is_sensitive_name, _scan_text


def test_scan_text_returns_only_redacted_metadata():
    stripe_value = "sk_test_1234567890abcdef"
    findings = _scan_text(
        f"API_KEY={stripe_value}\n-----BEGIN RSA PRIVATE KEY-----\n",
        scope="working-tree",
        path=".env",
        reference=None,
    )

    assert {finding["rule"] for finding in findings} == {
        "stripe-key",
        "generic-secret-assignment",
        "private-key",
    }
    assert stripe_value not in json.dumps(findings)
    assert all(set(finding) == {"scope", "path", "reference", "rule", "line"} for finding in findings)


def test_sensitive_ignored_name_detection_is_narrow():
    assert _is_sensitive_name("config/.env.production")
    assert _is_sensitive_name("certificates/service.pem")
    assert _is_sensitive_name("backup/provider-credentials.json.bak")
    assert not _is_sensitive_name("src/secrets_catalog.py")
