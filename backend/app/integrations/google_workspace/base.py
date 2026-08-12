"""Google Workspace provider interface — abstract base for real and mock providers.

All methods return WorkspaceActionResult or lists thereof.
No real external calls are permitted in this wave.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.integrations.google_workspace.schemas import (
    WorkspaceMockEmail,
    WorkspaceMockDoc,
    WorkspaceMockSheet,
    WorkspaceMockDriveFile,
    WorkspaceMockCalendarEvent,
    WorkspaceActionResult,
)


class GoogleWorkspaceProvider(ABC):
    """Abstract interface for Google Workspace operations."""

    # ── Gmail ───────────────────────────────────────────────────────────────

    @abstractmethod
    async def search_emails(
        self, query: str, max_results: int = 10, organization_id: str = ""
    ) -> list[WorkspaceMockEmail]:
        """Search emails matching a query. Returns mock/safe results."""
        ...

    @abstractmethod
    async def draft_reply(
        self, thread_id: str, body: str, organization_id: str = ""
    ) -> WorkspaceActionResult:
        """Draft a reply to an email thread. Does NOT send."""
        ...

    @abstractmethod
    async def send_email(
        self, to: str, subject: str, body: str, organization_id: str = ""
    ) -> WorkspaceActionResult:
        """Send an email. In mock mode, returns approval_required or mock result."""
        ...

    # ── Docs ────────────────────────────────────────────────────────────────

    @abstractmethod
    async def create_doc(
        self, title: str, body: str, organization_id: str = ""
    ) -> WorkspaceActionResult:
        """Create a new Google Doc."""
        ...

    @abstractmethod
    async def append_to_doc(
        self, doc_id: str, content: str, organization_id: str = ""
    ) -> WorkspaceActionResult:
        """Append content to an existing Google Doc."""
        ...

    # ── Sheets ──────────────────────────────────────────────────────────────

    @abstractmethod
    async def create_sheet(
        self, title: str, columns: list[str], rows: list[list[str]] | None = None,
        organization_id: str = "",
    ) -> WorkspaceActionResult:
        """Create a new Google Sheet."""
        ...

    @abstractmethod
    async def append_to_sheet(
        self, sheet_id: str, rows: list[list[str]], organization_id: str = ""
    ) -> WorkspaceActionResult:
        """Append rows to an existing Google Sheet."""
        ...

    # ── Drive ───────────────────────────────────────────────────────────────

    @abstractmethod
    async def list_files(
        self, query: str = "", max_results: int = 20, organization_id: str = ""
    ) -> list[WorkspaceMockDriveFile]:
        """List Drive files matching a query."""
        ...

    @abstractmethod
    async def share_file(
        self, file_id: str, email: str, role: str = "reader",
        organization_id: str = "",
    ) -> WorkspaceActionResult:
        """Share a Drive file. In mock mode, returns approval_required."""
        ...

    @abstractmethod
    async def move_file(
        self, file_id: str, new_parent_id: str, organization_id: str = ""
    ) -> WorkspaceActionResult:
        """Move a Drive file to a new folder. In mock mode, returns approval_required."""
        ...

    # ── Calendar ────────────────────────────────────────────────────────────

    @abstractmethod
    async def create_calendar_event(
        self, summary: str, description: str, start_time: str, end_time: str,
        attendees: list[str] | None = None, organization_id: str = "",
    ) -> WorkspaceActionResult:
        """Create a calendar event. In mock mode, returns tentative or approval_required."""
        ...

    # ── Provider Info ───────────────────────────────────────────────────────

    @abstractmethod
    def is_mock(self) -> bool:
        """Return True if this is a mock provider (no real external calls)."""
        ...
