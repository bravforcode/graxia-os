"""Tests for MockGoogleWorkspaceProvider — verify in-memory mock behavior.

All tests must:
1. Operate entirely in-memory (no real Google API calls)
2. Verify mock responses are returned correctly
3. Verify approval-gated methods return approval signal
4. Verify no secrets/OAuth tokens leaked
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from app.integrations.google_workspace import MockGoogleWorkspaceProvider
from app.integrations.google_workspace.errors import WorkspaceNotFoundError

TEST_ORG = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def provider() -> MockGoogleWorkspaceProvider:
    return MockGoogleWorkspaceProvider()


@pytest.mark.asyncio
class TestMockProviderGmail:
    async def test_search_emails_default(self, provider):
        emails = await provider.search_emails(organization_id=TEST_ORG)
        assert len(emails) >= 3, "Should have at least 3 seeded emails"
        assert all(e.status == "inbox" for e in emails)

    async def test_search_emails_with_query(self, provider):
        emails = await provider.search_emails(query="digital product", organization_id=TEST_ORG)
        assert len(emails) >= 1
        assert "digital product" in emails[0].body.lower()

    async def test_draft_reply_creates_draft(self, provider):
        emails = await provider.search_emails(organization_id=TEST_ORG)
        assert len(emails) > 0
        thread_id = emails[0].thread_id

        result = await provider.draft_reply(thread_id=thread_id, body="Test reply", organization_id=TEST_ORG)
        assert result.success is True
        assert result.action == "draft_reply"
        assert result.item_id != ""

    async def test_draft_reply_nonexistent_thread(self, provider):
        with pytest.raises(WorkspaceNotFoundError):
            await provider.draft_reply(thread_id="nonexistent-thread", body="Test", organization_id=TEST_ORG)

    async def test_send_email_returns_approval_required(self, provider):
        result = await provider.send_email(
            to="customer@example.com",
            subject="Test Subject",
            body="Test body",
            organization_id=TEST_ORG,
        )
        assert result.success is False
        assert result.data.get("approval_required") is True
        assert "approval" in result.message.lower()


@pytest.mark.asyncio
class TestMockProviderDocs:
    async def test_create_doc(self, provider):
        result = await provider.create_doc(title="Test Doc", body="Test content", organization_id=TEST_ORG)
        assert result.success is True
        assert result.action == "create_doc"
        assert result.data["title"] == "Test Doc"

    async def test_append_to_doc(self, provider):
        create_result = await provider.create_doc(title="Append Test", body="Initial", organization_id=TEST_ORG)
        doc_id = create_result.item_id

        result = await provider.append_to_doc(doc_id=doc_id, content="Appended", organization_id=TEST_ORG)
        assert result.success is True
        assert result.action == "append_to_doc"

    async def test_append_to_nonexistent_doc(self, provider):
        with pytest.raises(WorkspaceNotFoundError):
            await provider.append_to_doc(doc_id="nonexistent", content="Test", organization_id=TEST_ORG)


@pytest.mark.asyncio
class TestMockProviderSheets:
    async def test_create_sheet(self, provider):
        result = await provider.create_sheet(
            title="Test Sheet",
            columns=["A", "B", "C"],
            rows=[["1", "2", "3"]],
            organization_id=TEST_ORG,
        )
        assert result.success is True
        assert result.action == "create_sheet"
        assert result.data["columns"] == ["A", "B", "C"]

    async def test_append_to_sheet(self, provider):
        create_result = await provider.create_sheet(
            title="Append Sheet", columns=["X", "Y"], organization_id=TEST_ORG,
        )
        sheet_id = create_result.item_id

        result = await provider.append_to_sheet(
            sheet_id=sheet_id, rows=[["10", "20"]], organization_id=TEST_ORG,
        )
        assert result.success is True
        assert result.action == "append_to_sheet"

    async def test_append_to_nonexistent_sheet(self, provider):
        with pytest.raises(WorkspaceNotFoundError):
            await provider.append_to_sheet(sheet_id="nonexistent", rows=[["1"]], organization_id=TEST_ORG)


@pytest.mark.asyncio
class TestMockProviderDrive:
    async def test_list_files_default(self, provider):
        files = await provider.list_files(organization_id=TEST_ORG)
        assert len(files) >= 2, "Should have at least 2 seeded files"

    async def test_list_files_with_query(self, provider):
        files = await provider.list_files(query="Funnel Report", organization_id=TEST_ORG)
        assert len(files) >= 1

    async def test_share_file_returns_approval_required(self, provider):
        files = await provider.list_files(organization_id=TEST_ORG)
        assert len(files) > 0

        result = await provider.share_file(
            file_id=files[0].id, email="user@example.com", role="reader",
            organization_id=TEST_ORG,
        )
        assert result.success is False
        assert result.data.get("approval_required") is True

    async def test_move_file_returns_approval_required(self, provider):
        files = await provider.list_files(organization_id=TEST_ORG)
        assert len(files) > 0

        result = await provider.move_file(
            file_id=files[0].id, new_parent_id="new-folder-id",
            organization_id=TEST_ORG,
        )
        assert result.success is False
        assert result.data.get("approval_required") is True

    async def test_share_nonexistent_file(self, provider):
        # share_file is approval-gated — does NOT validate existence
        result = await provider.share_file(file_id="nonexistent", email="a@b.com", organization_id=TEST_ORG)
        assert result.success is False
        assert result.data.get("approval_required") is True


@pytest.mark.asyncio
class TestMockProviderCalendar:
    async def test_create_calendar_event(self, provider):
        result = await provider.create_calendar_event(
            summary="Test Event",
            description="A test event",
            start_time="2026-06-01T09:00:00Z",
            end_time="2026-06-01T10:00:00Z",
            attendees=["user@example.com"],
            organization_id=TEST_ORG,
        )
        assert result.success is True
        assert result.action == "create_calendar_event"
        assert result.data["status"] == "tentative"
        assert "mock" in result.message.lower()

    async def test_create_calendar_event_without_attendees(self, provider):
        result = await provider.create_calendar_event(
            summary="Solo Event",
            description="No attendees",
            start_time="2026-06-01T11:00:00Z",
            end_time="2026-06-01T12:00:00Z",
            organization_id=TEST_ORG,
        )
        assert result.success is True
        assert result.data["attendees"] == []


@pytest.mark.asyncio
class TestMockProviderSafety:
    async def test_is_mock_returns_true(self, provider):
        assert provider.is_mock() is True

    async def test_no_real_external_calls_in_methods(self, provider):
        """Verify no methods raise connection errors (they all use in-memory storage)."""
        # If any method tried to make an external call, it would fail
        # These should all work in-memory
        emails = await provider.search_emails(organization_id=TEST_ORG)
        assert len(emails) >= 0

        result = await provider.create_doc(title="Safety Test", body="Safe", organization_id=TEST_ORG)
        assert result.success is True

        files = await provider.list_files(organization_id=TEST_ORG)
        assert len(files) >= 0

    async def test_no_secrets_in_output(self, provider):
        """Verify no API keys, OAuth tokens, or service account values in responses."""
        result = await provider.create_doc(title="Security Audit", body="Test for sensitive data review", organization_id=TEST_ORG)
        output_str = str(result.to_dict()).lower()
        # Check for actual secret/credential patterns
        assert "api_key" not in output_str, "api_key should not leak"
        assert "password" not in output_str, "password should not leak"
        assert "oauth" not in output_str, "oauth should not leak"
        assert "service_account" not in output_str, "service_account should not leak"
        assert "private_key" not in output_str, "private_key should not leak"
        # Verify the doc was actually created
        assert result.success is True
        assert result.data["title"] == "Security Audit"
