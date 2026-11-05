from __future__ import annotations

from datetime import UTC, datetime, timedelta
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


@pytest.mark.asyncio
@pytest.mark.parametrize("write_scopes,allow_mutation", [(False, False), (False, True), (True, False)])
@pytest.mark.parametrize("cached_services", [False, True])
@pytest.mark.parametrize("operation", ["send_message", "mark_as_read", "create_calendar_event"])
async def test_mutations_require_both_flags_before_any_provider_call(
    monkeypatch, write_scopes, allow_mutation, cached_services, operation
):
    monkeypatch.setattr("app.core.google_workspace.settings.GOOGLE_ENABLE_WRITE_SCOPES", write_scopes)
    monkeypatch.setattr("app.core.google_workspace.settings.ALLOW_REAL_GOOGLE_MUTATION", allow_mutation)
    client = GoogleWorkspaceClient()
    initialize = Mock(return_value=False)
    monkeypatch.setattr(client, "_ensure_initialized", initialize)
    gmail_service = Mock()
    calendar_service = Mock()
    if cached_services:
        client.gmail_service = gmail_service
        client.calendar_service = calendar_service

    if operation == "send_message":
        result = await client.send_message("recipient@example.com", "Test", "Body")
        assert result is None
    elif operation == "mark_as_read":
        result = await client.mark_as_read("message-id")
        assert result is False
    else:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        result = await client.create_calendar_event("Test", start, start + timedelta(hours=1))
        assert result is None

    initialize.assert_not_called()
    assert gmail_service.mock_calls == []
    assert calendar_service.mock_calls == []


@pytest.mark.parametrize("write_scopes,allow_mutation", [(False, False), (False, True), (True, False), (True, True)])
def test_write_scopes_require_both_flags(monkeypatch, write_scopes, allow_mutation):
    monkeypatch.setattr("app.core.google_workspace.settings.GOOGLE_ENABLE_WRITE_SCOPES", write_scopes)
    monkeypatch.setattr("app.core.google_workspace.settings.ALLOW_REAL_GOOGLE_MUTATION", allow_mutation)
    client = GoogleWorkspaceClient()
    monkeypatch.setattr(client, "_has_real_credentials", lambda: True)
    credentials = Mock(valid=True, expired=False)
    credentials_factory = Mock(return_value=credentials)
    build_factory = Mock()
    monkeypatch.setattr("app.core.google_workspace.Credentials", credentials_factory)
    monkeypatch.setattr("app.core.google_workspace.build", build_factory)

    client._initialize_credentials()

    scopes = credentials_factory.call_args.kwargs["scopes"]
    assert "https://www.googleapis.com/auth/gmail.readonly" in scopes
    assert "https://www.googleapis.com/auth/calendar.readonly" in scopes
    for scope in ("gmail.send", "gmail.modify", "calendar.events"):
        assert (f"https://www.googleapis.com/auth/{scope}" in scopes) is (write_scopes and allow_mutation)
    credentials.refresh.assert_not_called()


@pytest.mark.asyncio
async def test_mutations_call_mocked_provider_when_both_flags_enabled(monkeypatch):
    monkeypatch.setattr("app.core.google_workspace.settings.GOOGLE_ENABLE_WRITE_SCOPES", True)
    monkeypatch.setattr("app.core.google_workspace.settings.ALLOW_REAL_GOOGLE_MUTATION", True)
    client = GoogleWorkspaceClient()
    client.gmail_service = Mock()
    messages = client.gmail_service.users.return_value.messages.return_value
    messages.send.return_value.execute.return_value = {"id": "sent-id"}
    client.calendar_service = Mock()
    events = client.calendar_service.events.return_value
    events.insert.return_value.execute.return_value = {"id": "event-id"}

    assert await client.send_message("recipient@example.com", "Test", "Body") == "sent-id"
    assert await client.mark_as_read("message-id") is True
    start = datetime(2026, 1, 1, tzinfo=UTC)
    assert await client.create_calendar_event("Test", start, start + timedelta(hours=1)) == "event-id"

    messages.send.return_value.execute.assert_called_once()
    messages.modify.return_value.execute.assert_called_once()
    events.insert.return_value.execute.assert_called_once()
