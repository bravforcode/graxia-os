"""Google Workspace schemas — types for mock workspace operations."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass
class WorkspaceMockEmail:
    """A mock email stored in the workspace provider."""
    id: str = ""
    thread_id: str = ""
    to: str = ""
    from_: str = ""
    subject: str = ""
    body: str = ""
    status: str = "draft"  # draft | sent | approval_required
    sent_at: str | None = None
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid4())
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()


@dataclass
class WorkspaceMockDoc:
    """A mock Google Doc."""
    id: str = ""
    title: str = ""
    body: str = ""
    status: str = "draft"  # draft | published | shared_public
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now


@dataclass
class WorkspaceMockSheet:
    """A mock Google Sheet."""
    id: str = ""
    title: str = ""
    rows: list[list[str]] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid4())
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()


@dataclass
class WorkspaceMockDriveFile:
    """A mock Google Drive file."""
    id: str = ""
    name: str = ""
    mime_type: str = "application/octet-stream"
    size_bytes: int = 0
    parent_folder_id: str | None = None
    status: str = "private"  # private | shared | public
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid4())
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()


@dataclass
class WorkspaceMockCalendarEvent:
    """A mock Google Calendar event."""
    id: str = ""
    summary: str = ""
    description: str = ""
    start_time: str = ""
    end_time: str = ""
    attendees: list[str] = field(default_factory=list)
    status: str = "tentative"  # tentative | confirmed | approval_required
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid4())
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()


@dataclass
class WorkspaceActionResult:
    """Result of a workspace action."""
    success: bool = True
    action: str = ""
    item_id: str = ""
    message: str = ""
    data: dict[str, Any] | None = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action,
            "item_id": self.item_id,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp,
        }
