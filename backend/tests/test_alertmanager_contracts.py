import hashlib
import hmac
import json

import pytest


@pytest.mark.asyncio
async def test_alertmanager_webhook_requires_internal_token(public_async_client, monkeypatch):
    monkeypatch.setattr(
        "app.middleware.auth.settings.ALERTMANAGER_WEBHOOK_TOKEN", "test-alert-token"
    )

    response = await public_async_client.post(
        "/api/v1/integrations/alerts/telegram",
        json={"alerts": []},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_alertmanager_webhook_accepts_bearer_token_and_formats_alert(
    public_async_client, monkeypatch
):
    sent_messages: list[str] = []

    async def fake_send_message(text: str, parse_mode=None, reply_markup=None):
        sent_messages.append(text)
        return True

    monkeypatch.setattr(
        "app.middleware.auth.settings.ALERTMANAGER_WEBHOOK_TOKEN", "test-alert-token"
    )
    monkeypatch.setattr("app.api.integrations.send_message", fake_send_message)

    response = await public_async_client.post(
        "/api/v1/integrations/alerts/telegram",
        headers={"Authorization": "Bearer test-alert-token"},
        json={
            "status": "firing",
            "alerts": [
                {
                    "labels": {"alertname": "BackupStale", "severity": "critical"},
                    "annotations": {
                        "summary": "Database backup is older than 25 hours",
                        "current_age": "26h",
                        "runbook": "https://runbooks.internal/backup-stale",
                    },
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "delivered", "alerts": 1}
    assert "BackupStale" in sent_messages[0]
    assert "runbook=https://runbooks.internal/backup-stale" in sent_messages[0]


@pytest.mark.asyncio
async def test_alertmanager_webhook_accepts_valid_hmac_signature(public_async_client, monkeypatch):
    """HMAC-SHA256 body signing is accepted when X-Alertmanager-Signature matches."""
    sent_messages: list[str] = []

    async def fake_send_message(text: str, parse_mode=None, reply_markup=None):
        sent_messages.append(text)
        return True

    secret = "test-hmac-secret-at-least-32-chars-long"
    monkeypatch.setattr("app.middleware.auth.settings.ALERTMANAGER_WEBHOOK_SECRET", secret)
    monkeypatch.setattr("app.middleware.auth.settings.ALERTMANAGER_WEBHOOK_TOKEN", "")
    monkeypatch.setattr("app.api.integrations.send_message", fake_send_message)

    payload = {"status": "resolved", "alerts": []}
    body = json.dumps(payload).encode()
    
    # Generate timestamp and signature according to webhook spec
    import time
    timestamp_str = str(int(time.time()))
    payload_to_sign = f"{timestamp_str}.".encode() + body
    sig = "sha256=" + hmac.new(secret.encode(), payload_to_sign, hashlib.sha256).hexdigest()

    response = await public_async_client.post(
        "/api/v1/integrations/alerts/telegram",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Alertmanager-Signature": sig,
            "X-Graxia-Timestamp": timestamp_str,
        },
    )

    assert response.status_code == 200
    assert response.json()["alerts"] == 0


@pytest.mark.asyncio
async def test_alertmanager_webhook_rejects_invalid_hmac_signature(
    public_async_client, monkeypatch
):
    """Tampered body or wrong secret must be rejected with 401."""
    secret = "correct-secret-at-least-32-chars-xxxx"
    monkeypatch.setattr("app.middleware.auth.settings.ALERTMANAGER_WEBHOOK_SECRET", secret)
    monkeypatch.setattr("app.middleware.auth.settings.ALERTMANAGER_WEBHOOK_TOKEN", "")

    response = await public_async_client.post(
        "/api/v1/integrations/alerts/telegram",
        json={"alerts": []},
        headers={"X-Alertmanager-Signature": "sha256=deadbeefdeadbeefdeadbeef"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_alertmanager_webhook_rejects_when_no_auth_configured(
    public_async_client, monkeypatch
):
    """No token and no secret means every request is rejected."""
    monkeypatch.setattr("app.middleware.auth.settings.ALERTMANAGER_WEBHOOK_SECRET", "")
    monkeypatch.setattr("app.middleware.auth.settings.ALERTMANAGER_WEBHOOK_TOKEN", "")

    response = await public_async_client.post(
        "/api/v1/integrations/alerts/telegram",
        json={"alerts": []},
    )

    assert response.status_code == 401
