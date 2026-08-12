"""Google Workspace error classes — safe errors with no raw details."""
from __future__ import annotations


class WorkspaceError(Exception):
    """Base workspace error — no raw details leaked to caller."""
    def __init__(self, message: str = "Workspace operation failed."):
        self.message = message
        super().__init__(self.message)


class WorkspaceNotFoundError(WorkspaceError):
    """Resource not found in workspace."""
    def __init__(self, resource_type: str = "resource"):
        super().__init__(f"{resource_type} not found.")


class WorkspacePermissionError(WorkspaceError):
    """Permission denied for workspace operation."""
    def __init__(self, action: str = "operation"):
        super().__init__(f"Permission denied for {action}.")


class WorkspaceApprovalRequiredError(WorkspaceError):
    """Operation requires human approval."""
    def __init__(self, action: str = "operation"):
        super().__init__(f"{action} requires human approval and has been queued.")


class WorkspaceMockOnlyError(WorkspaceError):
    """Operation is only available in mock mode."""
    def __init__(self, action: str = "operation"):
        super().__init__(f"{action} is not available in mock mode. Enable real Google Workspace integration.")
