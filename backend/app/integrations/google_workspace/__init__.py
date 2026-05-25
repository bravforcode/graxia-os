"""Google Workspace integration — provider interfaces and mock implementation."""

from app.integrations.google_workspace.base import GoogleWorkspaceProvider
from app.integrations.google_workspace.mock_provider import MockGoogleWorkspaceProvider, mock_workspace_provider
from app.integrations.google_workspace.schemas import (
    WorkspaceMockEmail,
    WorkspaceMockDoc,
    WorkspaceMockSheet,
    WorkspaceMockDriveFile,
    WorkspaceMockCalendarEvent,
    WorkspaceActionResult,
)

__all__ = [
    "GoogleWorkspaceProvider",
    "MockGoogleWorkspaceProvider",
    "mock_workspace_provider",
    "WorkspaceMockEmail",
    "WorkspaceMockDoc",
    "WorkspaceMockSheet",
    "WorkspaceMockDriveFile",
    "WorkspaceMockCalendarEvent",
    "WorkspaceActionResult",
]
