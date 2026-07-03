from __future__ import annotations

from app.audit.security_events import fingerprint_token, redact_security_payload


def test_redact_security_payload_removes_secret_like_fields():
    payload = {
        "Authorization": "Bearer super-secret",
        "nested": {"delivery_token": "abc", "status": "blocked"},
        "ok": "value",
    }

    redacted = redact_security_payload(payload)
    assert redacted["Authorization"] == "[REDACTED]"
    assert redacted["nested"]["delivery_token"] == "[REDACTED]"
    assert redacted["nested"]["status"] == "blocked"
    assert redacted["ok"] == "value"


def test_fingerprint_token_is_stable_and_not_raw():
    fingerprint = fingerprint_token("delivery-secret-token")
    assert fingerprint
    assert fingerprint == fingerprint_token("delivery-secret-token")
    assert fingerprint != "delivery-secret-token"
