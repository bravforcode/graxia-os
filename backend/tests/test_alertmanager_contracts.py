import pytest


@pytest.mark.asyncio
async def test_alertmanager_webhook_requires_internal_token(public_async_client, monkeypatch):
    monkeypatch.setattr("app.middleware.auth.settings.ALERTMANAGER_WEBHOOK_TOKEN", "test-alert-token")

    response = await public_async_client.post(
        "/api/v1/integrations/alerts/telegram",
        json={"alerts": []},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_alertmanager_webhook_accepts_bearer_token_and_formats_alert(public_async_client, monkeypatch):
    sent_messages: list[str] = []

    async def fake_send_message(text: str, parse_mode=None, reply_markup=None):
        sent_messages.append(text)
        return True

    monkeypatch.setattr("app.middleware.auth.settings.ALERTMANAGER_WEBHOOK_TOKEN", "test-alert-token")
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
