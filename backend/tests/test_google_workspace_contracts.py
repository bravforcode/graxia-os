from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from app.core.google_workspace import GoogleWorkspaceClient


def test_google_workspace_client_skips_initialization_when_credentials_are_placeholders(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.core.google_workspace.settings.GOOGLE_CLIENT_ID", "your_google_client_id"
    )
    monkeypatch.setattr(
        "app.core.google_workspace.settings.GOOGLE_CLIENT_SECRET",
        "your_google_client_secret",
    )
    monkeypatch.setattr(
        "app.core.google_workspace.settings.GOOGLE_REFRESH_TOKEN",
        "your_google_refresh_token",
    )
    monkeypatch.setattr(
        "app.core.google_workspace.settings.GOOGLE_WORKSPACE_EMAIL",
        "your_google_workspace_email",
    )

    credentials_factory = Mock()
    build_factory = Mock()
    monkeypatch.setattr("app.core.google_workspace.Credentials", credentials_factory)
    monkeypatch.setattr("app.core.google_workspace.build", build_factory)

    client = GoogleWorkspaceClient()

    assert client.credentials is None
    assert client.gmail_service is None
    assert client.calendar_service is None
    assert client._initialization_error is None
    credentials_factory.assert_not_called()
    build_factory.assert_not_called()


@pytest.mark.asyncio
async def test_google_workspace_client_initializes_lazily_on_first_real_use(monkeypatch):
    monkeypatch.setattr("app.core.google_workspace.settings.GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setattr(
        "app.core.google_workspace.GoogleWorkspaceClient._has_real_credentials", lambda self: True
    )
    monkeypatch.setattr("app.core.google_workspace.settings.GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr("app.core.google_workspace.settings.GOOGLE_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setattr(
        "app.core.google_workspace.settings.GOOGLE_WORKSPACE_EMAIL",
        "operator@example.com",
    )

    refresh = Mock()

    class FakeCredentials:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.valid = False
            self.expired = True

        def refresh(self, _request):
            refresh()
            self.valid = True
            self.expired = False

    list_execute = Mock(return_value={"messages": [{"id": "gmail-message-1"}]})
    gmail_service = SimpleNamespace(
        users=lambda: SimpleNamespace(
            messages=lambda: SimpleNamespace(
                list=lambda **_kwargs: SimpleNamespace(execute=list_execute)
            )
        )
    )
    calendar_service = SimpleNamespace()
    build_calls: list[str] = []

    def fake_build(service_name, _version, credentials):
        build_calls.append(service_name)
        assert credentials.valid is True
        if service_name == "gmail":
            return gmail_service
        if service_name == "calendar":
            return calendar_service
        raise AssertionError(f"Unexpected service requested: {service_name}")

    monkeypatch.setattr("app.core.google_workspace.Credentials", FakeCredentials)
    monkeypatch.setattr("app.core.google_workspace.build", fake_build)

    client = GoogleWorkspaceClient()

    assert client.gmail_service is None
    messages = await client.list_messages(max_results=1, query="in:inbox")

    assert messages == [{"id": "gmail-message-1"}]
    assert refresh.call_count == 1
    assert build_calls == ["gmail", "calendar"]
    list_execute.assert_called_once()
